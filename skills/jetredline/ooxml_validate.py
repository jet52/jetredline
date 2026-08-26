#!/usr/bin/env python3
"""OOXML validation for JetRedline.

Checks a .docx — or an already-unpacked .docx directory — for common OOXML
issues that cause Word to report "unreadable content."

Usage:
    python ooxml_validate.py <file.docx>
    python ooxml_validate.py <unpacked_dir>

A .docx is unpacked into a temporary directory that is removed on the way
out; nothing is written beside the document. Passing one used to fail with
"is not a directory", which made the post-apply_edits check — the one place
you would actually want this — undocumented and unreachable.

Exits 0 if clean. Exits 1 with diagnostic JSON on stdout if issues found.
"""

import json
import shutil
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

import defusedxml.minidom as minidom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_xml(path):
    """Parse an XML file with defusedxml. Returns (doc, True) or (None, False)."""
    try:
        doc = minidom.parse(str(path))
        return doc, True
    except Exception:
        return None, False


def get_elements_by_tag(doc, tag):
    return doc.getElementsByTagName(tag)


# ---------------------------------------------------------------------------
# Check 1: Unique w:id values across annotation types
# ---------------------------------------------------------------------------

ANNOTATION_TAGS = [
    "w:bookmarkStart", "w:bookmarkEnd",
    "w:commentRangeStart", "w:commentRangeEnd", "w:commentReference",
    "w:ins", "w:del", "w:rPrChange", "w:pPrChange", "w:sectPrChange",
    "w:tblPrChange", "w:trPrChange", "w:tcPrChange", "w:tblGridChange",
]


def check_unique_ids(unpacked_dir):
    """Check that all w:id values are unique across annotation types."""
    issues = []
    doc_path = unpacked_dir / "word" / "document.xml"
    doc, ok = parse_xml(doc_path)
    if not ok:
        return issues

    seen = {}  # id_value -> list of tags
    for tag in ANNOTATION_TAGS:
        for el in get_elements_by_tag(doc, tag):
            val = el.getAttribute("w:id")
            if not val:
                continue
            seen.setdefault(val, []).append(tag)

    for id_val, tags in seen.items():
        if len(tags) > 1:
            # Filter: bookmarkStart+bookmarkEnd sharing an ID is normal
            unique_types = set()
            for t in tags:
                if t in ("w:bookmarkStart", "w:bookmarkEnd"):
                    unique_types.add("bookmark")
                elif t in ("w:commentRangeStart", "w:commentRangeEnd", "w:commentReference"):
                    unique_types.add("comment")
                else:
                    unique_types.add("change")
            if len(unique_types) > 1:
                issues.append({
                    "check": "unique_ids",
                    "id": id_val,
                    "tags": tags,
                    "message": f"ID {id_val} shared across annotation types: {', '.join(tags)}"
                })

    return issues


# ---------------------------------------------------------------------------
# Check 2: Comment range/reference consistency
# ---------------------------------------------------------------------------

def check_comment_consistency(unpacked_dir):
    """Check that every commentRangeStart has matching End and Reference."""
    issues = []
    doc_path = unpacked_dir / "word" / "document.xml"
    doc, ok = parse_xml(doc_path)
    if not ok:
        return issues

    starts = set()
    ends = set()
    refs = set()

    for el in get_elements_by_tag(doc, "w:commentRangeStart"):
        val = el.getAttribute("w:id")
        if val:
            starts.add(val)
    for el in get_elements_by_tag(doc, "w:commentRangeEnd"):
        val = el.getAttribute("w:id")
        if val:
            ends.add(val)
    for el in get_elements_by_tag(doc, "w:commentReference"):
        val = el.getAttribute("w:id")
        if val:
            refs.add(val)

    for cid in starts - ends:
        issues.append({
            "check": "comment_consistency",
            "id": cid,
            "message": f"commentRangeStart {cid} has no matching commentRangeEnd"
        })
    for cid in starts - refs:
        issues.append({
            "check": "comment_consistency",
            "id": cid,
            "message": f"commentRangeStart {cid} has no matching commentReference"
        })
    for cid in ends - starts:
        issues.append({
            "check": "comment_consistency",
            "id": cid,
            "message": f"commentRangeEnd {cid} has no matching commentRangeStart"
        })
    for cid in refs - starts:
        issues.append({
            "check": "comment_consistency",
            "id": cid,
            "message": f"commentReference {cid} has no matching commentRangeStart"
        })

    return issues


# ---------------------------------------------------------------------------
# Check 3: Comment artifact cross-references
# ---------------------------------------------------------------------------

def check_comment_artifacts(unpacked_dir):
    """Check that w:comment entries have matching extended/ids/extensible entries
    and that no orphans exist in any direction."""
    issues = []

    comments_path = unpacked_dir / "word" / "comments.xml"
    if not comments_path.exists():
        return issues

    comments_doc, ok = parse_xml(comments_path)
    if not ok:
        return issues

    # Collect paraIds from comments.xml
    comment_para_ids = set()
    for comment_el in get_elements_by_tag(comments_doc, "w:comment"):
        for p_el in comment_el.getElementsByTagName("w:p"):
            para_id = (p_el.getAttribute("w14:paraId") or
                       p_el.getAttribute("w:paraId"))
            if para_id:
                comment_para_ids.add(para_id)

    # commentsExtended.xml
    ext_path = unpacked_dir / "word" / "commentsExtended.xml"
    ext_para_ids = set()
    if ext_path.exists():
        ext_doc, ok = parse_xml(ext_path)
        if ok:
            for el in get_elements_by_tag(ext_doc, "w15:commentEx"):
                para_id = el.getAttribute("w15:paraId")
                if para_id:
                    ext_para_ids.add(para_id)

    # commentsIds.xml
    ids_path = unpacked_dir / "word" / "commentsIds.xml"
    ids_para_ids = set()
    if ids_path.exists():
        ids_doc, ok = parse_xml(ids_path)
        if ok:
            for el in get_elements_by_tag(ids_doc, "w16cid:commentId"):
                para_id = el.getAttribute("w16cid:paraId")
                if para_id:
                    ids_para_ids.add(para_id)

    # Check for orphans in extended
    for pid in ext_para_ids - comment_para_ids:
        issues.append({
            "check": "comment_artifacts",
            "paraId": pid,
            "message": f"commentsExtended has paraId {pid} with no matching w:comment"
        })

    # Check for orphans in ids
    for pid in ids_para_ids - comment_para_ids:
        issues.append({
            "check": "comment_artifacts",
            "paraId": pid,
            "message": f"commentsIds has paraId {pid} with no matching w:comment"
        })

    # Check for comments missing from extended (if extended file exists)
    if ext_path.exists():
        for pid in comment_para_ids - ext_para_ids:
            issues.append({
                "check": "comment_artifacts",
                "paraId": pid,
                "message": f"w:comment paraId {pid} missing from commentsExtended"
            })

    # Check for comments missing from ids (if ids file exists)
    if ids_path.exists():
        for pid in comment_para_ids - ids_para_ids:
            issues.append({
                "check": "comment_artifacts",
                "paraId": pid,
                "message": f"w:comment paraId {pid} missing from commentsIds"
            })

    return issues


# ---------------------------------------------------------------------------
# Check 4: Duplicate entries in Content_Types and .rels
# ---------------------------------------------------------------------------

def check_duplicate_entries(unpacked_dir):
    """Check for duplicate entries in [Content_Types].xml and .rels files."""
    issues = []

    # [Content_Types].xml
    ct_path = unpacked_dir / "[Content_Types].xml"
    if ct_path.exists():
        doc, ok = parse_xml(ct_path)
        if ok:
            seen = set()
            for el in get_elements_by_tag(doc, "Override"):
                key = el.getAttribute("PartName")
                if key in seen:
                    issues.append({
                        "check": "duplicate_entries",
                        "file": "[Content_Types].xml",
                        "message": f"Duplicate Override for PartName={key}"
                    })
                else:
                    seen.add(key)
            seen = set()
            for el in get_elements_by_tag(doc, "Default"):
                key = el.getAttribute("Extension")
                if key in seen:
                    issues.append({
                        "check": "duplicate_entries",
                        "file": "[Content_Types].xml",
                        "message": f"Duplicate Default for Extension={key}"
                    })
                else:
                    seen.add(key)

    # .rels files
    for rels_path in unpacked_dir.rglob("*.rels"):
        doc, ok = parse_xml(rels_path)
        if not ok:
            continue
        seen = set()
        rel_name = str(rels_path.relative_to(unpacked_dir))
        for el in get_elements_by_tag(doc, "Relationship"):
            key = (el.getAttribute("Type"), el.getAttribute("Target"))
            if key in seen:
                issues.append({
                    "check": "duplicate_entries",
                    "file": rel_name,
                    "message": f"Duplicate Relationship Type={key[0]}, Target={key[1]}"
                })
            else:
                seen.add(key)

    return issues


# ---------------------------------------------------------------------------
# Check 5: xml:space="preserve" on w:t with whitespace
# ---------------------------------------------------------------------------

def check_xml_space(unpacked_dir):
    """Check that w:t elements with leading/trailing whitespace have xml:space='preserve'."""
    issues = []
    doc_path = unpacked_dir / "word" / "document.xml"
    doc, ok = parse_xml(doc_path)
    if not ok:
        return issues

    for wt in get_elements_by_tag(doc, "w:t"):
        text = ""
        for child in wt.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text += child.data
        if not text:
            continue
        if text != text.strip():
            if not wt.getAttribute("xml:space"):
                # Try to give useful context
                preview = text[:30].replace("\n", "\\n")
                issues.append({
                    "check": "xml_space",
                    "text_preview": preview,
                    "message": f"w:t with whitespace missing xml:space=\"preserve\": \"{preview}...\""
                })

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@contextmanager
def unpacked(target: Path):
    """Yield a directory of OOXML parts for ``target``.

    A directory is used as-is. A .docx is extracted to a temp directory that
    is removed on exit, so validating a document never leaves an unpacked
    tree beside it.
    """
    if target.is_dir():
        yield target
        return
    if not target.is_file():
        raise FileNotFoundError(f"{target} is neither a .docx nor a directory")
    if not zipfile.is_zipfile(target):
        raise ValueError(f"{target} is not a .docx (not a zip archive)")
    tmp = Path(tempfile.mkdtemp(prefix="ooxml-validate-"))
    try:
        with zipfile.ZipFile(target) as zf:
            # Refuse absolute or parent-traversing member names rather than
            # writing outside the temp directory.
            for name in zf.namelist():
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ValueError(f"{target}: unsafe archive member {name!r}")
            zf.extractall(tmp)
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def validate(unpacked_dir: Path) -> list:
    """Every check, against a directory of OOXML parts."""
    issues = []
    issues.extend(check_unique_ids(unpacked_dir))
    issues.extend(check_comment_consistency(unpacked_dir))
    issues.extend(check_comment_artifacts(unpacked_dir))
    issues.extend(check_duplicate_entries(unpacked_dir))
    issues.extend(check_xml_space(unpacked_dir))
    return issues


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.docx | unpacked_dir>", file=sys.stderr)
        sys.exit(1)

    target = Path(sys.argv[1])
    try:
        with unpacked(target) as unpacked_dir:
            all_issues = validate(unpacked_dir)
    except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if all_issues:
        result = {
            "status": "FAIL",
            "issue_count": len(all_issues),
            "issues": all_issues
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
    else:
        result = {"status": "PASS", "issue_count": 0}
        print(json.dumps(result, indent=2))
        sys.exit(0)


if __name__ == "__main__":
    main()
