import os
import difflib
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Updated registered code for the agent service
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


def get_char_diffs(expected: str, found: str):
    """Finds exact character position differences between expected and found strings."""
    diffs = []
    matcher = difflib.SequenceMatcher(None, expected, found)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            diffs.append(f"Expected '{expected[i1:i2]}', found '{found[j1:j2]}' at character index {j1}")
        elif tag == 'delete':
            diffs.append(f"Missing letter(s) '{expected[i1:i2]}' near index {j1}")
        elif tag == 'insert':
            diffs.append(f"Extra letter(s) '{found[j1:j2]}' at index {j1}")
    return diffs


def analyze_differences(registered: str, submitted: str):
    reg_lines = registered.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()
    sub_lines = submitted.replace('\xa0', ' ').replace('\r\n', '\n').splitlines()

    if not any(sub_lines):
        return {"match": False, "errors": [{"type": "empty", "message": "Submitted code is empty."}]}

    errors = []
    max_lines = max(len(reg_lines), len(sub_lines))

    for line_idx in range(1, max_lines + 1):
        if line_idx > len(sub_lines):
            errors.append({
                "line_no": line_idx,
                "type": "missing_line",
                "message": f"Line {line_idx} is missing from submitted code.",
                "expected": reg_lines[line_idx - 1]
            })
            continue

        if line_idx > len(reg_lines):
            errors.append({
                "line_no": line_idx,
                "type": "extra_line",
                "message": f"Line {line_idx} is an extra line not present in registered code.",
                "found": sub_lines[line_idx - 1]
            })
            continue

        expected_line = reg_lines[line_idx - 1]
        sub_line = sub_lines[line_idx - 1]

        if expected_line == sub_line:
            continue

        # Calculate exact leading indentation spaces
        expected_indent = len(expected_line) - len(expected_line.lstrip(' '))
        found_indent = len(sub_line) - len(sub_line.lstrip(' '))

        line_error = {
            "line_no": line_idx,
            "indentation": None,
            "character_mismatches": [],
            "expected_line": expected_line,
            "found_line": sub_line
        }

        # 1. Indentation Check
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

        # 2. Character Mismatch Check (stripping leading/trailing spaces)
        expected_content = expected_line.strip()
        found_content = sub_line.strip()

        if expected_content != found_content:
            line_error["character_mismatches"] = get_char_diffs(expected_content, found_content)

        # Only add to errors list if an actual indentation or character issue was found
        if line_error["indentation"] or line_error["character_mismatches"]:
            errors.append(line_error)

    return {"match": len(errors) == 0, "errors": errors}


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
