import os
import ast
import re
import keyword
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Registered baseline code for comparison
REGISTERED_CODE = r'''import os, re, urllib.parse, urllib.request
from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)

def get_vid(q):
    try:
        enc = urllib.parse.quote(q)
        url = f"https://www.youtube.com/results?search_query={enc}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=5).read().decode()
        ids = re.findall(r"\"videoId\":\"([^\"]+)\"", data)
        return ids[0] if ids else None
    except Exception:
        return None

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/agent", methods=["POST"])
def ai_agent_router():
    d = request.get_json(silent=True)
    if not d or ("command" not in d and "text_command" not in d):
        abort(400)

    cmd_raw = d.get("command") or d.get("text_command")
    cmd = cmd_raw.strip().lower()

    if "youtube" in cmd:
        q = cmd
        patterns = [
            "open youtube and search",
            "open youtube and play",
            "open youtube",
            "and play",
            "play",
            "on youtube"
        ]
        for p in patterns:
            q = q.replace(p, "")
        q = q.strip()
        vid = get_vid(q)
        if vid:
            target = f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1"
            msg = f"Playing {q}"

    elif any(k in cmd for k in ["gmail", "email", "mail", "message"]):
        to, body = "", ""
        clean_cmd = re.sub(
            r'^(please\s+)?(open\s+)?(gmail|email|mail|message)\s*',
            '',
            cmd
        ).strip()

        clean_cmd = re.sub(r'\b(com(and|mand)?)\b', 'com', clean_cmd)

        parts = re.split(r'\b(type|write|saying|message|content|with body)\b', clean_cmd)
        recip_part = parts[0].strip()

        recip_part = re.sub(r'^(update\s+to|to|send\s+to|and\s+update\s+to)\s*', '', recip_part).strip()

        if len(parts) > 1:
            body = parts[-1].strip()

        if recip_part:
            c = recip_part.replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
            c = re.sub(r'[^a-zA-Z0-9@._%-]', '', c)
            to = c if "@" in c else f"{c}@gmail.com"

        base = "https://mail.google.com/mail/u/0/?view=cm&fs=1"
        params = urllib.parse.urlencode({"to": to, "body": body})
        target = f"{base}&{params}"
        msg = f"Drafting email to {to}"

    return jsonify({
        "success": True,
        "message": msg,
        "url": target
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))'''

BLOCK_KEYWORDS = {"def", "if", "elif", "else", "for", "while", "try", "except", "finally", "with", "class"}


def extract_python_keywords(line_text: str):
    """Extracts all reserved Python keywords from a line of code."""
    # Split by non-alphanumeric tokens to isolate words
    tokens = re.findall(r'\b[a-zA-Z_]\w*\b', line_text)
    return [t for t in tokens if keyword.iskeyword(t)]


def check_keyword_indentation_rules(code_string: str, user_line_count: int):
    """Checks Python syntax and keyword block indentation up to typed line count."""
    errors = []
    lines = code_string.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    try:
        ast.parse(code_string)
    except IndentationError as e:
        if e.lineno and e.lineno <= user_line_count:
            return [{
                "line_no": e.lineno,
                "type": "IndentationError",
                "message": f"Indentation Error on line {e.lineno}: {e.msg}"
            }]
    except SyntaxError as e:
        if "unexpected EOF" not in e.msg and e.lineno and e.lineno <= user_line_count:
            return [{
                "line_no": e.lineno,
                "type": "SyntaxError",
                "message": f"Syntax Error on line {e.lineno}: {e.msg}"
            }]

    for i in range(min(len(lines), user_line_count)):
        line_text = lines[i]
        stripped = line_text.strip()
        words = stripped.split()

        if words and words[0] in BLOCK_KEYWORDS:
            kw = words[0]
            if stripped.endswith(":"):
                if i + 1 < len(lines) and i + 1 < user_line_count:
                    next_line = lines[i + 1]
                    if next_line.strip() and not next_line.strip().startswith("#"):
                        current_indent = len(line_text) - len(line_text.lstrip(' '))
                        next_indent = len(next_line) - len(next_line.lstrip(' '))

                        if next_indent <= current_indent:
                            errors.append({
                                "line_no": i + 2,
                                "keyword": kw,
                                "type": "KeywordIndentationMismatch",
                                "message": f"Expected an indented block after keyword '{kw}' on line {i + 1}."
                            })

    return errors


def analyze_differences(registered: str, submitted: str):
    reg_lines = registered.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()
    sub_lines = submitted.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    if not any(sub_lines):
        return {"match": False, "errors": [{"type": "empty", "message": "Submitted code is empty."}]}

    user_line_count = len(sub_lines)

    # 1. First run Python indentation rules on submitted lines
    rule_errors = check_keyword_indentation_rules(submitted, user_line_count)
    if rule_errors:
        return {"match": False, "typed_lines": user_line_count, "errors": rule_errors}

    errors = []
    lines_to_check = min(len(reg_lines), user_line_count)

    for line_idx in range(1, lines_to_check + 1):
        reg_line = reg_lines[line_idx - 1]
        sub_line = sub_lines[line_idx - 1]

        reg_keywords = extract_python_keywords(reg_line)
        sub_keywords = extract_python_keywords(sub_line)

        # A. Check for Keyword Mismatches against template code
        if reg_keywords != sub_keywords:
            missing_kw = set(reg_keywords) - set(sub_keywords)
            extra_kw = set(sub_keywords) - set(reg_keywords)

            msg_parts = []
            if missing_kw:
                msg_parts.append(f"Missing keyword(s): {', '.join(missing_kw)}")
            if extra_kw:
                msg_parts.append(f"Unexpected keyword(s): {', '.join(extra_kw)}")

            errors.append({
                "line_no": line_idx,
                "type": "KeywordMismatchError",
                "expected_keywords": reg_keywords,
                "found_keywords": sub_keywords,
                "message": f"Line {line_idx}: Keyword mismatch. {' '.join(msg_parts)}"
            })

        # B. Check Indentation for Block Keywords
        reg_words = reg_line.strip().split()
        if reg_words and reg_words[0] in BLOCK_KEYWORDS:
            expected_indent = len(reg_line) - len(reg_line.lstrip(' '))
            found_indent = len(sub_line) - len(sub_line.lstrip(' '))

            if expected_indent != found_indent:
                diff_spaces = expected_indent - found_indent
                indent_msg = (
                    f"Line {line_idx}: Keyword '{reg_words[0]}' block needs {diff_spaces} more leading space(s)."
                    if diff_spaces > 0
                    else f"Line {line_idx}: Keyword '{reg_words[0]}' block has {abs(diff_spaces)} extra leading space(s)."
                )

                errors.append({
                    "line_no": line_idx,
                    "type": "KeywordIndentationDiff",
                    "keyword": reg_words[0],
                    "expected_spaces": expected_indent,
                    "found_spaces": found_indent,
                    "message": indent_msg
                })

    return {
        "match": len(errors) == 0,
        "typed_lines": user_line_count,
        "errors": errors
    }


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/compare", methods=["POST"])
def compare():
    data = request.get_json(silent=True) or {}
    result = analyze_differences(REGISTERED_CODE, data.get("input_code", ""))
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
