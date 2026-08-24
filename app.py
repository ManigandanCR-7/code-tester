import os
import ast
import re
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


def normalize_code_line(line: str) -> str:
    """Removes all internal whitespace while preserving all characters, symbols, and keywords."""
    return re.sub(r'\s+', '', line.strip())


def get_character_diffs(expected_str: str, found_str: str):
    """Finds exact character mismatches ignoring inline whitespace."""
    diffs = []
    matcher = difflib.SequenceMatcher(None, expected_str, found_str)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            diffs.append(f"Expected '{expected_str[i1:i2]}', found '{found_str[j1:j2]}'")
        elif tag == 'delete':
            diffs.append(f"Missing character(s): '{expected_str[i1:i2]}'")
        elif tag == 'insert':
            diffs.append(f"Extra character(s): '{found_str[j1:j2]}'")
    return diffs


def analyze_differences(registered: str, submitted: str):
    reg_lines = registered.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()
    sub_lines = submitted.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    if not any(sub_lines):
        return {"match": False, "errors": [{"type": "empty", "message": "Submitted code is empty."}]}

    user_line_count = len(sub_lines)
    errors = []
    lines_to_check = min(len(reg_lines), user_line_count)

    for line_idx in range(1, lines_to_check + 1):
        reg_line = reg_lines[line_idx - 1]
        sub_line = sub_lines[line_idx - 1]

        # 1. Indentation Check (Leading spaces)
        expected_indent = len(reg_line) - len(reg_line.lstrip(' '))
        found_indent = len(sub_line) - len(sub_line.lstrip(' '))

        indent_error = None
        if expected_indent != found_indent:
            diff_spaces = expected_indent - found_indent
            if diff_spaces > 0:
                indent_msg = f"Line {line_idx}: Needs {diff_spaces} more leading space(s) (Expected {expected_indent}, found {found_indent})."
            else:
                indent_msg = f"Line {line_idx}: Has {abs(diff_spaces)} extra leading space(s) (Expected {expected_indent}, found {found_indent})."

            indent_error = {
                "expected_spaces": expected_indent,
                "found_spaces": found_indent,
                "message": indent_msg
            }

        # 2. Character & Keyword Check (Normalized without internal whitespace)
        norm_expected = normalize_code_line(reg_line)
        norm_found = normalize_code_line(sub_line)

        char_diffs = []
        if norm_expected != norm_found:
            char_diffs = get_character_diffs(norm_expected, norm_found)

        # Flag line errors if either Indentation or Character mismatch occurs
        if indent_error or char_diffs:
            errors.append({
                "line_no": line_idx,
                "indentation_error": indent_error,
                "character_mismatches": char_diffs,
                "expected_line": reg_line,
                "found_line": sub_line
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
