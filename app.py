import re
import difflib
from flask import Flask, render_template, request, jsonify


app = Flask(__name__)


# ============================================================
# DEFAULT / REGISTERED CODE FOR EACH CODE EDITOR
# ============================================================

REGISTERED_CODES = {

    # --------------------------------------------------------
    # CODE EDITOR 1
    # Outer app/__init__.py
    # --------------------------------------------------------
    "editor1": r'''from flask import Flask, render_template
from app.youtube import youtube_bp


def create_app():

    app = Flask(__name__)

    app.register_blueprint(
        youtube_bp,
        url_prefix="/youtube"
    )

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/html")
    def html():
        return render_template("index.html")

    return app''',


    # --------------------------------------------------------
    # CODE EDITOR 2
    # app/youtube/__init__.py
    # --------------------------------------------------------
    "editor2": r'''from flask import Blueprint, request, jsonify

from app.youtube.player import create_youtube_url


youtube_bp = Blueprint(
    "youtube",
    __name__
)


@youtube_bp.route(
    "/play",
    methods=["POST"]
)
def play():

    data = request.get_json(
        silent=True
    ) or {}

    command = data.get(
        "command",
        ""
    ).strip()

    if not command:

        return jsonify({
            "success": False,
            "message": "Song name is required"
        }), 400

    url = create_youtube_url(
        command
    )

    if not url:

        return jsonify({
            "success": False,
            "message": "Could not find the song"
        }), 404

    return jsonify({
        "success": True,
        "type": "youtube",
        "query": command,
        "url": url
    })''',


    # --------------------------------------------------------
    # CODE EDITOR 3
    # app/youtube/player.py
    # --------------------------------------------------------
    "editor3": r'''import re
import urllib.parse
import urllib.request


def get_vid(query):

    try:
        encoded = urllib.parse.quote(query)

        url = (
            "https://www.youtube.com/results"
            "?search_query=" + encoded
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        data = urllib.request.urlopen(
            request,
            timeout=5
        ).read().decode("utf-8", errors="ignore")

        ids = re.findall(
            r'"videoId":"([^"]+)"',
            data
        )

        return ids[0] if ids else None

    except Exception:
        return None


def create_youtube_url(command):

    text = command.lower().strip()

    patterns = [
        r"play\s+song\s+(.+)",
        r"play\s+music\s+(.+)",
        r"play\s+(.+)",
        r"youtube\s+(.+)"
    ]

    query = command

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            query = match.group(1)
            break

    query = query.strip()

    video_id = get_vid(query)

    if not video_id:
        return None

    return (
        "https://www.youtube.com/embed/"
        + video_id
        + "?autoplay=1&mute=0"
    )''',


    # --------------------------------------------------------
    # CODE EDITOR 4
    # wsgi.py
    # --------------------------------------------------------
    "editor4": r'''from app import create_app

app = create_app()''',


    # --------------------------------------------------------
    # CODE EDITOR 5
    # templates/index.html
    # --------------------------------------------------------
    "editor5": r'''<!DOCTYPE html>
<html>

<head>
    <title>Nova AI</title>
</head>

<body>

    <h1>🤖 Nova AI</h1>

    <h2>✅ Backend Connected Successfully</h2>

    <p>Flask server is running.</p>

</body>

</html>'''
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_char_diffs(expected: str, found: str):
    """
    Finds exact character differences between
    expected and submitted strings.
    """

    diffs = []

    matcher = difflib.SequenceMatcher(
        None,
        expected,
        found
    )

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == "replace":

            diffs.append(
                f"Expected '{expected[i1:i2]}', "
                f"found '{found[j1:j2]}' "
                f"at character index {j1}"
            )

        elif tag == "delete":

            diffs.append(
                f"Missing character(s) "
                f"'{expected[i1:i2]}' "
                f"near index {j1}"
            )

        elif tag == "insert":

            diffs.append(
                f"Extra character(s) "
                f"'{found[j1:j2]}' "
                f"at index {j1}"
            )

    return diffs


def strip_all_whitespace(text: str):
    """
    Removes spaces and tabs so inner spacing
    can be ignored during comparison.
    """

    return re.sub(
        r"[ \t]+",
        "",
        text
    )


# ============================================================
# CODE COMPARISON
# ============================================================

def analyze_differences(
    registered: str,
    submitted: str
):

    reg_lines = (
        registered
        .replace("\xa0", " ")
        .replace("\r\n", "\n")
        .splitlines()
    )

    sub_lines = (
        submitted
        .replace("\xa0", " ")
        .replace("\r\n", "\n")
        .splitlines()
    )

    if not any(sub_lines):

        return {
            "match": False,
            "errors": [
                {
                    "type": "empty",
                    "message": "Submitted code is empty."
                }
            ]
        }

    errors = []

    for line_idx in range(
        1,
        len(sub_lines) + 1
    ):

        if line_idx > len(reg_lines):

            errors.append({
                "line_no": line_idx,
                "type": "extra_line",
                "message": (
                    f"Line {line_idx} is an extra line "
                    "not present in registered code."
                ),
                "found": sub_lines[line_idx - 1]
            })

            continue

        expected_line = reg_lines[
            line_idx - 1
        ]

        sub_line = sub_lines[
            line_idx - 1
        ]

        expected_indent = (
            len(expected_line)
            - len(expected_line.lstrip(" "))
        )

        found_indent = (
            len(sub_line)
            - len(sub_line.lstrip(" "))
        )

        expected_content = strip_all_whitespace(
            expected_line
        )

        found_content = strip_all_whitespace(
            sub_line
        )

        if (
            expected_indent == found_indent
            and expected_content == found_content
        ):
            continue

        line_error = {
            "line_no": line_idx,
            "indentation": None,
            "character_mismatches": [],
            "expected_line": expected_line,
            "found_line": sub_line
        }

        if expected_indent != found_indent:

            diff_spaces = (
                expected_indent
                - found_indent
            )

            if diff_spaces > 0:

                indent_msg = (
                    f"Needs {diff_spaces} more "
                    "leading space(s) "
                    f"(Expected {expected_indent}, "
                    f"found {found_indent})."
                )

            else:

                indent_msg = (
                    f"Has {abs(diff_spaces)} extra "
                    "leading space(s) "
                    f"(Expected {expected_indent}, "
                    f"found {found_indent})."
                )

            line_error["indentation"] = {
                "expected_spaces": expected_indent,
                "found_spaces": found_indent,
                "message": indent_msg
            }

        if expected_content != found_content:

            line_error["character_mismatches"] = (
                get_char_diffs(
                    expected_content,
                    found_content
                )
            )

        if (
            line_error["indentation"]
            or line_error["character_mismatches"]
        ):

            errors.append(line_error)

    return {
        "match": len(errors) == 0,
        "errors": errors
    }


# ============================================================
# FULL CODE FIX
# ============================================================

def fix_full_code(editor_id):

    """
    Completely replaces the selected editor's code
    with its registered/default code.
    """

    if editor_id not in REGISTERED_CODES:

        return {
            "success": False,
            "message": "Invalid editor ID.",
            "fixed_code": ""
        }

    fixed_code = REGISTERED_CODES[
        editor_id
    ]

    return {
        "success": True,
        "editor_id": editor_id,
        "fixed_code": fixed_code,
        "changed_count": 1,
        "message": (
            f"{editor_id} has been restored "
            "to the default code."
        )
    }


# ============================================================
# HOME PAGE
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# COMPARE
# ============================================================

@app.route(
    "/compare",
    methods=["POST"]
)
def compare():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    editor_id = data.get(
        "editor_id"
    )

    input_code = data.get(
        "input_code",
        ""
    )

    if editor_id not in REGISTERED_CODES:

        return jsonify({
            "match": False,
            "errors": [
                {
                    "type": "invalid_editor",
                    "message": "Invalid editor ID."
                }
            ]
        }), 400

    result = analyze_differences(
        REGISTERED_CODES[editor_id],
        input_code
    )

    result["editor_id"] = editor_id

    return jsonify(result)


# ============================================================
# FIX
# ============================================================

@app.route(
    "/fix",
    methods=["POST"]
)
def fix():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    editor_id = data.get(
        "editor_id"
    )

    if editor_id not in REGISTERED_CODES:

        return jsonify({
            "success": False,
            "message": "Invalid editor ID."
        }), 400

    result = fix_full_code(
        editor_id
    )

    return jsonify(result)


# ============================================================
# OLD FIX-INDENTATION ROUTE
# ============================================================

@app.route(
    "/fix-indentation",
    methods=["POST"]
)
def fix_indentation():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    editor_id = data.get(
        "editor_id"
    )

    if editor_id not in REGISTERED_CODES:

        return jsonify({
            "success": False,
            "message": "Invalid editor ID."
        }), 400

    # The new system intentionally performs
    # a complete replacement instead of
    # an indentation-only correction.

    result = fix_full_code(
        editor_id
    )

    return jsonify(result)


# ============================================================
# GET TEMPLATE
# ============================================================

@app.route(
    "/template",
    methods=["GET"]
)
def get_template():

    editor_id = request.args.get(
        "editor_id"
    )

    if editor_id:

        if editor_id not in REGISTERED_CODES:

            return jsonify({
                "success": False,
                "message": "Invalid editor ID."
            }), 400

        return jsonify({
            "success": True,
            "editor_id": editor_id,
            "template_code": REGISTERED_CODES[
                editor_id
            ]
        })

    # Return all five templates
    return jsonify({
        "success": True,
        "templates": REGISTERED_CODES
    })


# ============================================================
# GET ALL REGISTERED CODES
# ============================================================

@app.route(
    "/registered-codes",
    methods=["GET"]
)
def registered_codes():

    return jsonify({
        "success": True,
        "codes": REGISTERED_CODES
    })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            __import__("os").environ.get(
                "PORT",
                8000
            )
        )
    )
