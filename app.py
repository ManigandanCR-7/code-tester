import os
import ast
import difflib
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


def get_char_diffs(expected: str, found: str):
    """Finds exact character position differences between expected and found strings."""
    diffs = []
    matcher = difflib.SequenceMatcher(None, expected, found)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            diffs.append(f"Expected '{expected[i1:i2]}', found '{found[j1:j2]}' near index {j1}")
        elif tag == 'delete':
            diffs.append(f"Missing character(s) '{expected[i1:i2]}' near index {j1}")
        elif tag == 'insert':
            diffs.append(f"Extra character(s) '{found[j1:j2]}' at index {j1}")
    return diffs


def check_keyword_indentation_rules(code_string: str, user_line_count: int):
    """
    Checks block-keyword indentation rules dynamically up to the line count 
    currently typed in by the user.
    """
    errors = []
    lines = code_string.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    # 1. Parse AST dynamically (ignore EOF errors for partial snippet typing)
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
        # Ignore unexpected EOF when the user is mid-typing an incomplete snippet
        if "unexpected EOF" not in e.msg and e.lineno and e.lineno <= user_line_count:
            return [{
                "line_no": e.lineno,
                "type": "SyntaxError",
                "message": f"Syntax Error on line {e.lineno}: {e.msg}"
            }]

    # 2. Check line-by-line block keyword expectations within typed bounds
    for i in range(min(len(lines), user_line_count)):
        line_text = lines[i]
        stripped = line_text.strip()
        words = stripped.split()

        if words and words[0] in BLOCK_KEYWORDS:
            keyword = words[0]
            # Check if this keyword statement ends with a colon
            if stripped.endswith(":"):
                # If there's a subsequent line typed by the user, verify its indentation
                if i + 1 < len(lines) and i + 1 < user_line_count:
                    next_line = lines[i + 1]
                    if next_line.strip() and not next_line.strip().startswith("#"):
                        current_indent = len(line_text) - len(line_text.lstrip(' '))
                        next_indent = len(next_line) - len(next_line.lstrip(' '))

                        if next_indent <= current_indent:
                            errors.append({
                                "line_no": i + 2,
                                "keyword": keyword,
                                "type": "KeywordIndentationMismatch",
                                "message": f"Expected an indented block after '{keyword}' on line {i + 1}."
                            })

    return errors


def analyze_differences(registered: str, submitted: str):
    reg_lines = registered.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()
    sub_lines = submitted.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    if not any(sub_lines):
        return {"match": False, "errors": [{"type": "empty", "message": "Submitted code is empty."}]}

    user_line_count = len(sub_lines)

    # Step 1: Check Python keyword & syntax rules ONLY up to typed line count
    keyword_errors = check_keyword_indentation_rules(submitted, user_line_count)
    if keyword_errors:
        return {"match": False, "typed_lines": user_line_count, "errors": keyword_errors}

    # Step 2: Full line-by-line comparison (indentation + letters + symbols + keywords) up to user_line_count
    errors = []
    lines_to_check = min(len(reg_lines), user_line_count)

    for line_idx in range(1, lines_to_check + 1):
        expected_line = reg_lines[line_idx - 1]
        sub_line = sub_lines[line_idx - 1]

        if expected_line == sub_line:
            continue

        # Check Leading Indentation Mismatches
        expected_indent = len(expected_line) - len(expected_line.lstrip(' '))
        found_indent = len(sub_line) - len(sub_line.lstrip(' '))

        line_error = {
            "line_no": line_idx,
            "indentation": None,
            "character_mismatches": [],
            "expected_line": expected_line,
            "found_line": sub_line
        }

        if expected_indent != found_indent:
            diff_spaces = expected_indent - found_indent
            if diff_spaces > 0:
                indent_msg = f"Needs {diff_spaces} more leading space(s) (Expected {expected_indent}, found {found_indent})."
            else:
                indent_msg = f"Has {abs(diff_spaces)} extra leading space(s) (Expected {expected_indent}, found {found_indent})."

            line_error["indentation"] = {
                "expected_spaces": expected_indent,
                "found_spaces": found_indent,
                "message": indent_msg
            }

        # Check Character, Symbol, Keyword & Letter Mismatches
        expected_content = expected_line.strip()
        found_content = sub_line.strip()

        if expected_content != found_content:
            line_error["character_mismatches"] = get_char_diffs(expected_content, found_content)

        if line_error["indentation"] or line_error["character_mismatches"]:
            errors.append(line_error)

    # Handle extra lines if user typed beyond registered line length
    if user_line_count > len(reg_lines):
        for extra_idx in range(len(reg_lines) + 1, user_line_count + 1):
            errors.append({
                "line_no": extra_idx,
                "type": "extra_line",
                "message": f"Line {extra_idx} is an extra line not present in registered code.",
                "found": sub_lines[extra_idx - 1]
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
