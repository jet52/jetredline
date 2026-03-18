#!/usr/bin/env python3
"""Batch edit helper for JetRedline.

Applies a JSON array of edits (tracked deletions + insertions + comments) to an
unpacked .docx directory using direct XML manipulation, then runs ooxml_fixup.py
and ooxml_validate.py.

Fully self-contained: requires only defusedxml beyond the standard library.
No dependency on the docx plugin's Document API or comment.py.

Usage:
    python apply_edits.py --input <unpacked_dir> --edits <edits.json> \
        [--author "Claude"] [--output <output.docx>] \
        [--pack-script <pack.py>]

Edits JSON format:
    [
        {
            "type": "replace",
            "para": 3,
            "old": "exact text to delete",
            "new": "replacement text",
            "comment": "optional explanation"
        },
        {
            "type": "comment",
            "para": 5,
            "anchor": "text to attach comment to",
            "comment": "the comment text"
        }
    ]

For "replace" edits:
    - "para" is the 1-indexed paragraph number (¶) for disambiguation.
      If omitted, searches all paragraphs.
    - "old" is the exact text to find and mark as deleted.
    - "new" is the replacement text to insert.
    - "comment" is an optional explanation attached to the change.

For "comment" edits:
    - "para" is the paragraph number.
    - "anchor" is the text the comment attaches to.
    - "comment" is the comment text.

Exit codes:
    0  — success
    1  — one or more edits failed to apply (error JSON on stdout)
    2  — argument/setup error
"""

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import defusedxml.minidom

SKILL_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Comment XML templates (minimal namespace declarations)
# ---------------------------------------------------------------------------

_COMMENTS_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:comments'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
    ' xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
    ' mc:Ignorable="w14 w15">'
    '</w:comments>'
)

_COMMENTS_EXT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w15:commentsEx'
    ' xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
    ' mc:Ignorable="w15">'
    '</w15:commentsEx>'
)

_COMMENTS_IDS_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w16cid:commentsIds'
    ' xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
    ' mc:Ignorable="w16cid">'
    '</w16cid:commentsIds>'
)

_COMMENTS_EXTENSIBLE_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w16cex:commentsExtensible'
    ' xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
    ' mc:Ignorable="w16cex">'
    '</w16cex:commentsExtensible>'
)


# ---------------------------------------------------------------------------
# DOM utilities (inlined from docx plugin's XMLEditor)
# ---------------------------------------------------------------------------

def _get_root_namespaces(dom):
    """Extract xmlns declarations from the document root element."""
    root = dom.documentElement
    parts = []
    if root and root.attributes:
        for i in range(root.attributes.length):
            attr = root.attributes.item(i)
            if attr.name.startswith("xmlns"):
                parts.append(f'{attr.name}="{attr.value}"')
    return " ".join(parts)


def parse_fragment(dom, xml_content):
    """Parse an XML fragment in the document's namespace context.

    Returns list of element nodes imported into the document.
    """
    ns_decl = _get_root_namespaces(dom)
    wrapper = f"<root {ns_decl}>{xml_content}</root>"
    frag_doc = defusedxml.minidom.parseString(wrapper)
    nodes = [
        dom.importNode(child, deep=True)
        for child in frag_doc.documentElement.childNodes
        if child.nodeType == child.ELEMENT_NODE
    ]
    assert nodes, f"Fragment must contain at least one element: {xml_content[:80]}"
    return nodes


def dom_insert_before(dom, ref_elem, xml_content):
    """Insert parsed XML content before ref_elem. Returns inserted elements."""
    parent = ref_elem.parentNode
    nodes = parse_fragment(dom, xml_content)
    for node in nodes:
        parent.insertBefore(node, ref_elem)
    return nodes


def dom_insert_after(dom, ref_elem, xml_content):
    """Insert parsed XML content after ref_elem. Returns inserted elements."""
    parent = ref_elem.parentNode
    nxt = ref_elem.nextSibling
    nodes = parse_fragment(dom, xml_content)
    for node in nodes:
        if nxt:
            parent.insertBefore(node, nxt)
        else:
            parent.appendChild(node)
    return nodes


def save_xml(dom, path):
    """Serialize DOM back to file, detecting encoding from existing declaration."""
    with open(path, "rb") as f:
        header = f.read(200).decode("utf-8", errors="ignore")
    encoding = "ascii" if 'encoding="ascii"' in header else "utf-8"
    Path(path).write_bytes(dom.toxml(encoding=encoding))


def save_xml_new(dom, path):
    """Serialize DOM to a new file (no existing encoding to detect)."""
    Path(path).write_bytes(dom.toxml(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tracked-change IDs and hex ID generation
# ---------------------------------------------------------------------------

_ID_TAGS = (
    "w:del", "w:ins", "w:commentRangeStart", "w:commentRangeEnd",
    "w:bookmarkStart", "w:bookmarkEnd", "w:commentReference",
    "w:rPrChange", "w:pPrChange", "w:sectPrChange",
    "w:tblPrChange", "w:trPrChange", "w:tcPrChange", "w:tblGridChange",
)


def make_id_generator(dom):
    """Return a callable that yields sequential unique w:id values."""
    max_id = 0
    for tag in _ID_TAGS:
        for elem in dom.getElementsByTagName(tag):
            try:
                max_id = max(max_id, int(elem.getAttribute("w:id")))
            except (ValueError, TypeError):
                pass

    def next_id():
        nonlocal max_id
        max_id += 1
        return max_id

    return next_id


def _generate_hex_id():
    """Generate a random 8-character uppercase hex ID."""
    return f"{random.randint(0, 0xFFFFFFFF):08X}"


# ---------------------------------------------------------------------------
# People.xml
# ---------------------------------------------------------------------------

def ensure_people_xml(unpacked_dir, author):
    """Create or update word/people.xml with the author entry."""
    path = unpacked_dir / "word" / "people.xml"
    escaped = _escape_xml(author)

    if path.exists():
        pdom = defusedxml.minidom.parse(str(path))
        for tag in ("w15:person", "w:person"):
            for p in pdom.getElementsByTagName(tag):
                a = p.getAttribute("w15:author") or p.getAttribute("w:author")
                if a == author:
                    return  # Already present
        # Append author
        root = pdom.documentElement
        person_xml = (
            f'<w15:person w15:author="{escaped}">'
            f'<w15:presenceInfo w15:providerId="None" w15:userId="{escaped}"/>'
            f'</w15:person>'
        )
        for node in parse_fragment(pdom, person_xml):
            root.appendChild(node)
        save_xml(pdom, path)
    else:
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w15:people xmlns:w15='
            '"http://schemas.microsoft.com/office/word/2012/wordml">\n'
            f'  <w15:person w15:author="{escaped}">\n'
            f'    <w15:presenceInfo w15:providerId="None"'
            f' w15:userId="{escaped}"/>\n'
            f'  </w15:person>\n'
            '</w15:people>'
        )


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def get_paragraph_text(para_elem):
    """Extract concatenated text from all w:t and w:delText elements."""
    texts = []
    for tag_name in ("w:t", "w:delText"):
        for t in para_elem.getElementsByTagName(tag_name):
            for child in t.childNodes:
                if child.nodeType == child.TEXT_NODE:
                    texts.append(child.data)
    return "".join(texts)


def get_run_text(run_elem):
    """Extract text from w:t elements in a single run."""
    texts = []
    for t in run_elem.getElementsByTagName("w:t"):
        for child in t.childNodes:
            if child.nodeType == child.TEXT_NODE:
                texts.append(child.data)
    return "".join(texts)


def find_paragraph_by_number(dom, para_num):
    """Find the para_num-th w:p element (1-indexed) in the document body."""
    body = dom.getElementsByTagName("w:body")
    if not body:
        return None
    paragraphs = body[0].getElementsByTagName("w:p")
    if para_num < 1 or para_num > len(paragraphs):
        return None
    return paragraphs[para_num - 1]


def find_paragraph_containing(dom, text, para_num=None):
    """Find a paragraph containing the given text.

    If para_num is provided, tries that paragraph first, then scans all.
    """
    body = dom.getElementsByTagName("w:body")
    if not body:
        return None
    paragraphs = list(body[0].getElementsByTagName("w:p"))

    if para_num is not None and 1 <= para_num <= len(paragraphs):
        p = paragraphs[para_num - 1]
        if text in get_paragraph_text(p):
            return p

    for p in paragraphs:
        if text in get_paragraph_text(p):
            return p
    return None


# ---------------------------------------------------------------------------
# XML escaping
# ---------------------------------------------------------------------------

def _escape_xml(text):
    """Escape text for XML content, preserving Unicode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# CommentWriter — self-contained comment injection
# ---------------------------------------------------------------------------

class CommentWriter:
    """Writes Word-compatible comments directly to unpacked .docx XML files.

    Manages all 4 comment metadata files (comments.xml, commentsExtended.xml,
    commentsIds.xml, commentsExtensible.xml), relationships, content types,
    and document.xml range markers.
    """

    _CONTENT_TYPES = {
        "/word/comments.xml":
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.comments+xml",
        "/word/commentsExtended.xml":
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.commentsExtended+xml",
        "/word/commentsIds.xml":
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.commentsIds+xml",
        "/word/commentsExtensible.xml":
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.commentsExtensible+xml",
        "/word/people.xml":
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.people+xml",
    }

    _RELATIONSHIPS = {
        "comments.xml":
            "http://schemas.openxmlformats.org/officeDocument"
            "/2006/relationships/comments",
        "commentsExtended.xml":
            "http://schemas.microsoft.com/office"
            "/2011/relationships/commentsExtended",
        "commentsIds.xml":
            "http://schemas.microsoft.com/office"
            "/2016/09/relationships/commentsIds",
        "commentsExtensible.xml":
            "http://schemas.microsoft.com/office"
            "/2018/08/relationships/commentsExtensible",
        "people.xml":
            "http://schemas.microsoft.com/office"
            "/2011/relationships/people",
    }

    def __init__(self, unpacked_dir, author, timestamp):
        self.unpacked_dir = Path(unpacked_dir)
        self.word_dir = self.unpacked_dir / "word"
        self.author = author
        self.timestamp = timestamp
        self.initials = (
            "".join(c for c in author if c.isupper()) or author[:1]
        )
        self._comments_dom = None
        self._extended_dom = None
        self._ids_dom = None
        self._extensible_dom = None
        self._setup_done = False
        self._dirty = False

    def add_comment(self, comment_id, text, dom, start_elem, end_elem):
        """Add a comment spanning from start_elem to end_elem.

        Writes comment metadata to the 4 comment XML files and inserts
        commentRangeStart/End/Reference markers into the document.xml DOM.

        Args:
            comment_id: Unique integer ID for this comment.
            text: The comment text.
            dom: The document.xml DOM (for inserting markers).
            start_elem: DOM element to place commentRangeStart before.
            end_elem: DOM element to place commentRangeEnd after.
        """
        self._ensure_setup()
        self._dirty = True

        para_id = _generate_hex_id()
        durable_id = _generate_hex_id()

        # Comment metadata files
        self._add_to_comments(comment_id, text, para_id)
        self._add_to_extended(para_id)
        self._add_to_ids(para_id, durable_id)
        self._add_to_extensible(durable_id)

        # Document.xml markers
        self._insert_markers(dom, comment_id, start_elem, end_elem)

    def save(self):
        """Write all modified comment files to disk."""
        if not self._dirty:
            return
        for filename, cdom in (
            ("comments.xml", self._comments_dom),
            ("commentsExtended.xml", self._extended_dom),
            ("commentsIds.xml", self._ids_dom),
            ("commentsExtensible.xml", self._extensible_dom),
        ):
            if cdom is not None:
                path = self.word_dir / filename
                if path.exists():
                    save_xml(cdom, path)
                else:
                    save_xml_new(cdom, path)

    # -- Internal helpers --------------------------------------------------

    def _ensure_setup(self):
        """Load or create all comment XML files; set up rels + content types."""
        if self._setup_done:
            return
        self._comments_dom = self._load_or_create(
            "comments.xml", _COMMENTS_TEMPLATE
        )
        self._extended_dom = self._load_or_create(
            "commentsExtended.xml", _COMMENTS_EXT_TEMPLATE
        )
        self._ids_dom = self._load_or_create(
            "commentsIds.xml", _COMMENTS_IDS_TEMPLATE
        )
        self._extensible_dom = self._load_or_create(
            "commentsExtensible.xml", _COMMENTS_EXTENSIBLE_TEMPLATE
        )
        self._ensure_relationships()
        self._ensure_content_types()
        self._setup_done = True

    def _load_or_create(self, filename, template):
        """Load existing XML file or create from template."""
        path = self.word_dir / filename
        if path.exists():
            return defusedxml.minidom.parse(str(path))
        return defusedxml.minidom.parseString(template)

    def _add_to_comments(self, comment_id, text, para_id):
        """Add w:comment entry to comments.xml."""
        escaped_text = _escape_xml(text)
        escaped_author = _escape_xml(self.author)
        escaped_initials = _escape_xml(self.initials)
        comment_xml = (
            f'<w:comment w:id="{comment_id}"'
            f' w:author="{escaped_author}"'
            f' w:date="{self.timestamp}"'
            f' w:initials="{escaped_initials}">'
            f'<w:p w14:paraId="{para_id}">'
            f'<w:pPr><w:pStyle w:val="CommentText"/></w:pPr>'
            f'<w:r><w:rPr>'
            f'<w:rStyle w:val="CommentReference"/>'
            f'</w:rPr><w:annotationRef/></w:r>'
            f'<w:r><w:t>{escaped_text}</w:t></w:r>'
            f'</w:p></w:comment>'
        )
        root = self._comments_dom.documentElement
        for node in parse_fragment(self._comments_dom, comment_xml):
            root.appendChild(node)

    def _add_to_extended(self, para_id):
        """Add w15:commentEx entry to commentsExtended.xml."""
        xml = (
            f'<w15:commentEx w15:paraId="{para_id}"'
            f' w15:paraIdParent="00000000" w15:done="0"/>'
        )
        root = self._extended_dom.documentElement
        for node in parse_fragment(self._extended_dom, xml):
            root.appendChild(node)

    def _add_to_ids(self, para_id, durable_id):
        """Add w16cid:commentId entry to commentsIds.xml."""
        xml = (
            f'<w16cid:commentId w16cid:paraId="{para_id}"'
            f' w16cid:durableId="{durable_id}"/>'
        )
        root = self._ids_dom.documentElement
        for node in parse_fragment(self._ids_dom, xml):
            root.appendChild(node)

    def _add_to_extensible(self, durable_id):
        """Add w16cex:commentExtensible entry to commentsExtensible.xml."""
        xml = (
            f'<w16cex:commentExtensible w16cex:durableId="{durable_id}"'
            f' w16cex:dateUtc="{self.timestamp}"/>'
        )
        root = self._extensible_dom.documentElement
        for node in parse_fragment(self._extensible_dom, xml):
            root.appendChild(node)

    def _insert_markers(self, dom, comment_id, start_elem, end_elem):
        """Insert commentRangeStart/End + commentReference into document.xml."""
        # Range start before the anchored content
        dom_insert_before(
            dom, start_elem,
            f'<w:commentRangeStart w:id="{comment_id}"/>',
        )
        # Range end after the anchored content
        end_nodes = dom_insert_after(
            dom, end_elem,
            f'<w:commentRangeEnd w:id="{comment_id}"/>',
        )
        # Comment reference run after the range end
        if end_nodes:
            dom_insert_after(
                dom, end_nodes[0],
                f'<w:r><w:rPr>'
                f'<w:rStyle w:val="CommentReference"/>'
                f'</w:rPr>'
                f'<w:commentReference w:id="{comment_id}"/></w:r>',
            )

    def _ensure_relationships(self):
        """Add relationship entries for comment files to document.xml.rels."""
        rels_path = self.word_dir / "_rels" / "document.xml.rels"
        if not rels_path.exists():
            return

        rels_dom = defusedxml.minidom.parse(str(rels_path))
        root = rels_dom.documentElement
        root_ns = root.namespaceURI or ""

        # Collect existing relationship types
        existing = set()
        max_rid = 0
        for rel in rels_dom.getElementsByTagName("Relationship"):
            existing.add(rel.getAttribute("Type"))
            rid = rel.getAttribute("Id")
            if rid.startswith("rId"):
                try:
                    max_rid = max(max_rid, int(rid[3:]))
                except ValueError:
                    pass

        modified = False
        for target, rel_type in self._RELATIONSHIPS.items():
            if rel_type not in existing:
                max_rid += 1
                elem = rels_dom.createElementNS(root_ns, "Relationship")
                elem.setAttribute("Id", f"rId{max_rid}")
                elem.setAttribute("Type", rel_type)
                elem.setAttribute("Target", target)
                root.appendChild(elem)
                modified = True

        if modified:
            save_xml(rels_dom, rels_path)

    def _ensure_content_types(self):
        """Add Override entries for comment files to [Content_Types].xml."""
        ct_path = self.unpacked_dir / "[Content_Types].xml"
        if not ct_path.exists():
            return

        ct_dom = defusedxml.minidom.parse(str(ct_path))
        root = ct_dom.documentElement
        root_ns = root.namespaceURI or ""

        existing = set()
        for override in ct_dom.getElementsByTagName("Override"):
            existing.add(override.getAttribute("PartName"))

        modified = False
        for part_name, content_type in self._CONTENT_TYPES.items():
            if part_name not in existing:
                elem = ct_dom.createElementNS(root_ns, "Override")
                elem.setAttribute("PartName", part_name)
                elem.setAttribute("ContentType", content_type)
                root.appendChild(elem)
                modified = True

        if modified:
            save_xml(ct_dom, ct_path)


# ---------------------------------------------------------------------------
# Tracked-change application
# ---------------------------------------------------------------------------

def apply_replace(dom, edit, edit_index, author, timestamp, next_id,
                  comment_writer):
    """Apply a replace edit: mark old text as deleted, insert new text.

    If the edit has a "comment" field and comment_writer is provided,
    the comment is applied inline.

    Returns a result dict.
    """
    old_text = edit["old"]
    new_text = edit["new"]
    para_num = edit.get("para")
    comment_text = edit.get("comment")

    para = find_paragraph_containing(dom, old_text, para_num)
    if para is None:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Could not find paragraph containing: {old_text[:80]}..."
        }

    # Collect runs (w:r elements, including inside tracked changes and hyperlinks)
    runs = []
    for child in para.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            if child.tagName == "w:r":
                runs.append(child)
            elif child.tagName in ("w:ins", "w:del"):
                for r in child.getElementsByTagName("w:r"):
                    runs.append(r)
            elif child.tagName == "w:hyperlink":
                for r in child.getElementsByTagName("w:r"):
                    runs.append(r)

    # Build text map: (run, run_text, start_offset, end_offset)
    text_map = []
    offset = 0
    for run in runs:
        rt = get_run_text(run)
        if rt:
            text_map.append((run, rt, offset, offset + len(rt)))
            offset += len(rt)

    full_text = "".join(item[1] for item in text_map)
    match_start = full_text.find(old_text)
    if match_start == -1:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Text not found in paragraph runs: {old_text[:80]}..."
        }
    match_end = match_start + len(old_text)

    # Identify affected runs with their overlap portions
    affected_runs = []
    for run, rt, r_start, r_end in text_map:
        if r_end <= match_start or r_start >= match_end:
            continue
        portion_start = max(0, match_start - r_start)
        portion_end = min(len(rt), match_end - r_start)
        affected_runs.append((run, rt, portion_start, portion_end))

    if not affected_runs:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"No runs overlap with matched text: {old_text[:80]}..."
        }

    escaped_author = _escape_xml(author)
    first_change_elem = None
    last_change_elem = None

    for run, rt, portion_start, portion_end in affected_runs:
        before_text = rt[:portion_start]
        matched_text = rt[portion_start:portion_end]
        after_text = rt[portion_end:]

        parent = run.parentNode

        # Don't double-wrap tracked changes
        if parent.tagName in ("w:del", "w:ins"):
            return {
                "edit_index": edit_index,
                "status": "skipped",
                "message": f"Run already has tracked changes, skipping: {old_text[:80]}..."
            }

        # Clone the run's formatting
        rPr_nodes = run.getElementsByTagName("w:rPr")
        rPr_xml = rPr_nodes[0].toxml() if rPr_nodes else ""

        # "Before" run: text preceding the match within this run
        if before_text:
            sp = ' xml:space="preserve"' if before_text != before_text.strip() else ""
            before_xml = (
                f'<w:r>{rPr_xml}'
                f'<w:t{sp}>{_escape_xml(before_text)}</w:t></w:r>'
            )
            dom_insert_before(dom, run, before_xml)

        # Deletion run: matched text wrapped in w:del
        del_id = next_id()
        sp_del = ' xml:space="preserve"' if matched_text != matched_text.strip() else ""
        del_xml = (
            f'<w:del w:id="{del_id}" w:author="{escaped_author}"'
            f' w:date="{timestamp}">'
            f'<w:r>{rPr_xml}'
            f'<w:delText{sp_del}>{_escape_xml(matched_text)}</w:delText>'
            f'</w:r></w:del>'
        )
        del_elems = dom_insert_before(dom, run, del_xml)

        if first_change_elem is None and del_elems:
            first_change_elem = del_elems[0]
        if del_elems:
            last_change_elem = del_elems[0]

        # "After" run: text following the match within this run
        if after_text:
            sp = ' xml:space="preserve"' if after_text != after_text.strip() else ""
            after_xml = (
                f'<w:r>{rPr_xml}'
                f'<w:t{sp}>{_escape_xml(after_text)}</w:t></w:r>'
            )
            dom_insert_before(dom, run, after_xml)

        # Remove the original run
        parent.removeChild(run)

    # Insert new text as a tracked insertion after the last deletion
    if last_change_elem is not None and new_text:
        ins_rPr_nodes = affected_runs[0][0].getElementsByTagName("w:rPr")
        ins_rPr_xml = ins_rPr_nodes[0].toxml() if ins_rPr_nodes else ""
        ins_id = next_id()
        sp_ins = ' xml:space="preserve"' if new_text != new_text.strip() else ""
        ins_xml = (
            f'<w:ins w:id="{ins_id}" w:author="{escaped_author}"'
            f' w:date="{timestamp}">'
            f'<w:r>{ins_rPr_xml}'
            f'<w:t{sp_ins}>{_escape_xml(new_text)}</w:t></w:r></w:ins>'
        )
        ins_elems = dom_insert_after(dom, last_change_elem, ins_xml)
        if ins_elems:
            last_change_elem = ins_elems[0]

    result = {"edit_index": edit_index, "status": "ok"}

    # Apply comment if requested
    if comment_text and comment_writer and first_change_elem:
        try:
            comment_writer.add_comment(
                comment_id=next_id(),
                text=comment_text,
                dom=dom,
                start_elem=first_change_elem,
                end_elem=last_change_elem,
            )
        except Exception as e:
            result["status"] = "partial"
            result["message"] = f"Edit applied but comment failed: {e}"

    return result


def apply_comment(dom, edit, edit_index, next_id, comment_writer):
    """Apply a comment-only edit."""
    anchor_text = edit.get("anchor", "")
    comment_text = edit["comment"]
    para_num = edit.get("para")

    para = find_paragraph_containing(dom, anchor_text, para_num)
    if para is None and para_num:
        para = find_paragraph_by_number(dom, para_num)
    if para is None:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": (
                f"Could not find paragraph for comment anchor: "
                f"{anchor_text[:80]}..."
            ),
        }

    # Find the run containing the anchor text
    anchor_run = None
    if anchor_text:
        for run in para.getElementsByTagName("w:r"):
            if anchor_text in get_run_text(run):
                anchor_run = run
                break

    target = anchor_run if anchor_run else para

    try:
        comment_writer.add_comment(
            comment_id=next_id(),
            text=comment_text,
            dom=dom,
            start_elem=target,
            end_elem=target,
        )
    except Exception as e:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Failed to add comment: {e}",
        }

    return {"edit_index": edit_index, "status": "ok"}


# ---------------------------------------------------------------------------
# Post-processing: fixup + validate + pack
# ---------------------------------------------------------------------------

def _find_python():
    """Find the best available Python interpreter."""
    venv_python = SKILL_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    tmp_python = Path("/tmp/jetredline-venv/bin/python")
    if tmp_python.exists():
        return str(tmp_python)
    return sys.executable


def run_fixup(unpacked_dir):
    """Run ooxml_fixup.py on the unpacked directory."""
    fixup_script = SKILL_DIR / "ooxml_fixup.py"
    result = subprocess.run(
        [_find_python(), str(fixup_script), str(unpacked_dir)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "ok", "raw": result.stdout}


def run_validate(unpacked_dir):
    """Run ooxml_validate.py on the unpacked directory."""
    validate_script = SKILL_DIR / "ooxml_validate.py"
    result = subprocess.run(
        [_find_python(), str(validate_script), str(unpacked_dir)],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "raw": result.stdout,
        }


def pack_output(unpacked_dir, output_path, pack_script=None):
    """Pack the unpacked directory back into a .docx file."""
    if pack_script is None:
        pack_script = _discover_pack_script()

    if pack_script is None:
        return {"status": "error", "message": "pack.py not found"}

    pack_path = Path(pack_script)
    python = _find_python()

    env = os.environ.copy()
    # PYTHONPATH: docx skill root (3 levels up from pack.py in both layouts)
    docx_root = pack_path.parent.parent.parent
    env["PYTHONPATH"] = str(docx_root) + ":" + env.get("PYTHONPATH", "")
    # LibreOffice on PATH
    if sys.platform == "darwin":
        lo = "/Applications/LibreOffice.app/Contents/MacOS"
        env["PATH"] = lo + ":" + env.get("PATH", "")

    result = subprocess.run(
        [python, str(pack_path), str(unpacked_dir), str(output_path),
         "--force"],
        capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr}
    return {"status": "ok"}


def _discover_pack_script():
    """Search known locations for pack.py."""
    candidates = []

    # Cowork layout
    cowork_pack = Path("/mnt/.skills/skills/docx/scripts/office/pack.py")
    if cowork_pack.exists():
        candidates.append(cowork_pack)

    # Claude Code plugin cache
    cache_base = (
        Path.home()
        / ".claude/plugins/cache/anthropic-agent-skills/document-skills"
    )
    if cache_base.is_dir():
        for sub in cache_base.iterdir():
            p = sub / "skills/docx/ooxml/scripts/pack.py"
            if p.exists():
                candidates.append(p)

    # Marketplaces
    mp = (
        Path.home()
        / ".claude/plugins/marketplaces/anthropic-agent-skills"
        / "skills/docx/scripts/office/pack.py"
    )
    if mp.exists():
        candidates.append(mp)

    return str(candidates[0]) if candidates else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Apply batch edits to an unpacked .docx as tracked changes"
    )
    parser.add_argument(
        "--input", required=True, help="Path to unpacked .docx directory"
    )
    parser.add_argument(
        "--edits", required=True, help="Path to edits JSON file"
    )
    parser.add_argument(
        "--author", default="Claude", help="Author name for tracked changes"
    )
    parser.add_argument("--output", help="Output .docx path")
    parser.add_argument("--pack-script", help="Path to pack.py")
    parser.add_argument(
        "--no-fixup", action="store_true", help="Skip ooxml_fixup.py"
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip ooxml_validate.py"
    )
    parser.add_argument(
        "--no-pack", action="store_true", help="Skip packing into .docx"
    )
    args = parser.parse_args()

    unpacked_dir = Path(args.input)
    if not unpacked_dir.is_dir():
        print(json.dumps({
            "status": "error",
            "message": f"Not a directory: {args.input}",
        }))
        sys.exit(2)

    edits_path = Path(args.edits)
    if not edits_path.exists():
        print(json.dumps({
            "status": "error",
            "message": f"Edits file not found: {args.edits}",
        }))
        sys.exit(2)

    try:
        edits = json.loads(edits_path.read_text())
    except json.JSONDecodeError as e:
        print(json.dumps({
            "status": "error",
            "message": f"Invalid JSON in edits file: {e}",
        }))
        sys.exit(2)

    if not isinstance(edits, list):
        print(json.dumps({
            "status": "error",
            "message": "Edits must be a JSON array",
        }))
        sys.exit(2)

    # Parse document.xml directly
    doc_xml_path = unpacked_dir / "word" / "document.xml"
    if not doc_xml_path.exists():
        print(json.dumps({
            "status": "error",
            "message": f"document.xml not found in {unpacked_dir}",
        }))
        sys.exit(2)

    dom = defusedxml.minidom.parse(str(doc_xml_path))
    next_id = make_id_generator(dom)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Set up people.xml and comment writer
    ensure_people_xml(unpacked_dir, args.author)
    comment_writer = CommentWriter(unpacked_dir, args.author, timestamp)

    # ------------------------------------------------------------------
    # Apply edits
    # ------------------------------------------------------------------
    results = []
    errors = []

    for i, edit in enumerate(edits):
        edit_type = edit.get("type", "replace")

        if edit_type == "replace":
            result = apply_replace(
                dom, edit, i, args.author, timestamp, next_id,
                comment_writer,
            )
        elif edit_type == "comment":
            result = apply_comment(dom, edit, i, next_id, comment_writer)
        else:
            result = {
                "edit_index": i,
                "status": "error",
                "message": f"Unknown edit type: {edit_type}",
            }

        results.append(result)
        if result["status"] == "error":
            errors.append(result)

    # Save document.xml and comment files
    save_xml(dom, doc_xml_path)
    comment_writer.save()

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------
    fixup_result = None
    if not args.no_fixup:
        fixup_result = run_fixup(unpacked_dir)

    validate_result = None
    if not args.no_validate:
        validate_result = run_validate(unpacked_dir)

    pack_result = None
    if args.output and not args.no_pack:
        pack_result = pack_output(
            unpacked_dir, args.output, args.pack_script
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    summary = {
        "status": "error" if errors else "ok",
        "edits_total": len(edits),
        "edits_applied": sum(
            1 for r in results if r["status"] == "ok"
        ),
        "edits_partial": sum(
            1 for r in results if r["status"] == "partial"
        ),
        "edits_skipped": sum(
            1 for r in results if r["status"] == "skipped"
        ),
        "edits_failed": sum(
            1 for r in results if r["status"] == "error"
        ),
        "edit_results": results,
    }

    if fixup_result:
        summary["fixup"] = fixup_result
    if validate_result:
        summary["validation"] = validate_result
    if pack_result:
        summary["pack"] = pack_result

    print(json.dumps(summary, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
