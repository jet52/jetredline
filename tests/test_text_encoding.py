"""Every text-mode file operation must name its encoding.

Without `encoding=`, CPython uses the platform default — cp1252 on Windows.
The skill's own files are full of curly quotes, em dashes, and `¶`, so a bare
`read_text()` raises `UnicodeDecodeError: 'charmap' codec can't decode byte
0x9d` on any real run there, and a bare `write_text()` fails the same way on
output. Reported from a Windows run of v4.13.0: `apply_edits.py` died on an
edits file whose comments quoted the draft.

This walks the AST rather than grepping, so a call whose `encoding=` sits on a
continuation line counts as correct and a `mode="rb"` open is correctly
ignored.
"""

import ast
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "jetredline"

# lib/ is vendored jetcite — canonical source lives in the jetcite repo and is
# checked there, not patched here.
SCRIPTS = sorted(SKILL_DIR.glob("*.py"))

TEXT_METHODS = {"read_text", "write_text"}


def _is_binary_open(node: ast.Call) -> bool:
    """True when open()'s mode makes it a binary call, which needs no encoding."""
    mode = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" in mode


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # `.open()` as an attribute is deliberately not checked: `p.open()`
        # on a Path needs an encoding, but `fitz.open()` and
        # `pdfplumber.open()` are library calls that would reject one, and
        # nothing in the AST tells them apart. read_text/write_text cover the
        # path that actually appears in this skill.
        if isinstance(node.func, ast.Attribute):
            if node.func.attr not in TEXT_METHODS:
                continue
            name = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            if _is_binary_open(node):
                continue
            name = "open"
        else:
            continue
        if not any(kw.arg == "encoding" for kw in node.keywords):
            found.append(f"{path.name}:{node.lineno} {name}()")
    return found


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_text_io_names_its_encoding(path):
    offenders = _offenders(path)
    assert not offenders, (
        "text-mode file I/O without encoding=\"utf-8\" (crashes on Windows):\n  "
        + "\n  ".join(offenders)
    )


def test_the_check_itself_catches_a_bare_call(tmp_path):
    """Guard the guard: a regex over lines would miss the continuation-line
    form and flag the binary one, so prove the AST walk does neither."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from pathlib import Path\n"
        "p = Path('x')\n"
        "a = p.read_text()\n"                       # offender, line 3
        "b = p.write_text('y',\n    encoding='utf-8')\n"   # fine, split call
        "c = open('f', 'rb').read()\n"              # fine, binary
        "d = open('f').read()\n",                   # offender, line 7
        encoding="utf-8",
    )
    assert _offenders(sample) == ["sample.py:3 read_text()", "sample.py:7 open()"]


# --- href separators --------------------------------------------------------


def test_every_relative_to_is_posix_normalized():
    """`str(path.relative_to(base))` emits backslashes on Windows, which land
    verbatim in the review page's hrefs. Chrome normalizes them in a `file:`
    URL; nothing else promises to, and over `http://` they are just wrong.
    Every relative_to() in the page builder must be followed by .as_posix().
    """
    src = (SKILL_DIR / "cite_review.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = {n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "relative_to"}
    posix = {n.value.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and n.attr == "as_posix"
             and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Attribute)
             and n.value.func.attr == "relative_to"}
    # A path interpolated into a message is a native path for the user to
    # read, and should stay native; only a stored link must be POSIX.
    display = {n.value.lineno for n in ast.walk(tree)
               if isinstance(n, ast.FormattedValue)
               and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Attribute)
               and n.value.func.attr == "relative_to"}
    assert not (calls - posix - display), (
        "relative_to() without .as_posix() at cite_review.py line(s) "
        + ", ".join(str(n) for n in sorted(calls - posix - display))
    )
