#!/usr/bin/env python3
"""Batch edit helper for JetRedline.

Applies a JSON array of edits (tracked deletions + insertions + comments)
directly to a .docx file, producing a new .docx with tracked changes.

Operates on the ZIP archive directly — no unpack/pack pipeline, no dependency
on the docx plugin.  Serializes all XML as UTF-8 with standalone="yes" and
preserves original ZIP entry metadata, producing files Word opens cleanly.

Requires only defusedxml beyond the standard library.

Usage:
    python apply_edits.py --input <original.docx> --edits <edits.json> \
        --output <output.docx> [--author "Claude"]

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
import html
import json
import random
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import defusedxml.minidom


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

_PEOPLE_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w15:people'
    ' xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
    '</w15:people>'
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


# ---------------------------------------------------------------------------
# ZIP I/O — read from original, write preserving metadata
# ---------------------------------------------------------------------------

def serialize_dom_utf8(dom):
    """Serialize DOM to UTF-8 bytes with standalone='yes' declaration.

    minidom.toxml(encoding="UTF-8") produces:
        <?xml version="1.0" encoding="UTF-8"?>
    Word requires standalone="yes", so we patch the declaration.
    """
    raw = dom.toxml(encoding="UTF-8")
    raw = raw.replace(
        b'<?xml version="1.0" encoding="UTF-8"?>',
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        1,
    )
    return raw


def _windows_zipinfo(name):
    """Create a ZipInfo with Windows-compatible metadata for new entries."""
    info = zipfile.ZipInfo(name)
    info.create_system = 0   # MS-DOS
    info.create_version = 45
    info.extract_version = 20
    info.external_attr = 0
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build_output_zip(input_path, output_path, modified, added):
    """Build output .docx by copying original entries, replacing modified ones.

    Args:
        input_path: Path to original .docx
        output_path: Path for output .docx
        modified: {entry_name: bytes} for entries to replace in-place
        added: {entry_name: bytes} for new entries not in original
    """
    with zipfile.ZipFile(input_path, 'r') as zin:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in modified:
                    # Preserve original ZipInfo metadata (create_system,
                    # external_attr, etc.) — only replace content
                    new_info = zipfile.ZipInfo(item.filename)
                    new_info.create_system = item.create_system
                    new_info.create_version = item.create_version
                    new_info.extract_version = item.extract_version
                    new_info.flag_bits = item.flag_bits
                    new_info.external_attr = item.external_attr
                    new_info.compress_type = zipfile.ZIP_DEFLATED
                    zout.writestr(new_info, modified[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

            # Add new entries (comment files, people.xml if absent)
            existing = {item.filename for item in zin.infolist()}
            for name, data in added.items():
                if name not in existing:
                    zout.writestr(_windows_zipinfo(name), data)


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

def ensure_people_xml(existing_bytes, author):
    """Create or update people.xml DOM with the author entry.

    Args:
        existing_bytes: bytes of existing people.xml from ZIP, or None
        author: author name string

    Returns:
        (dom, modified) — the people.xml DOM and whether it was changed
    """
    escaped = _escape_xml(author)

    if existing_bytes:
        pdom = defusedxml.minidom.parseString(existing_bytes)
        for tag in ("w15:person", "w:person"):
            for p in pdom.getElementsByTagName(tag):
                a = (
                    p.getAttribute("w15:author")
                    or p.getAttribute("w:author")
                )
                if a == author:
                    return pdom, False  # Already present
        # Author not found — append
        root = pdom.documentElement
        person_xml = (
            f'<w15:person w15:author="{escaped}">'
            f'<w15:presenceInfo w15:providerId="None"'
            f' w15:userId="{escaped}"/>'
            f'</w15:person>'
        )
        for node in parse_fragment(pdom, person_xml):
            root.appendChild(node)
        return pdom, True
    else:
        pdom = defusedxml.minidom.parseString(_PEOPLE_TEMPLATE)
        root = pdom.documentElement
        person_xml = (
            f'<w15:person w15:author="{escaped}">'
            f'<w15:presenceInfo w15:providerId="None"'
            f' w15:userId="{escaped}"/>'
            f'</w15:person>'
        )
        for node in parse_fragment(pdom, person_xml):
            root.appendChild(node)
        return pdom, True


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

    Uses normalized matching (NBSP→space, NFC, HTML entity decoding)
    to handle mismatches between edit JSON and extracted XML text.
    If para_num is provided, tries that paragraph first, then scans all.
    """
    body = dom.getElementsByTagName("w:body")
    if not body:
        return None
    paragraphs = list(body[0].getElementsByTagName("w:p"))
    norm_text = _normalize_for_search(text)

    if para_num is not None and 1 <= para_num <= len(paragraphs):
        p = paragraphs[para_num - 1]
        if norm_text in _normalize_for_search(get_paragraph_text(p)):
            return p

    for p in paragraphs:
        if norm_text in _normalize_for_search(get_paragraph_text(p)):
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


def _normalize_for_search(text):
    """Normalize text for fuzzy matching.

    Handles mismatches between edit JSON text and extracted XML text:
    - HTML entities (&#x2019; → ') — Claude may carry these from raw XML
    - NFC normalization — compose combining sequences
    - Non-breaking spaces (U+00A0, U+202F) → regular space

    The normalization is 1:1 for NBSP→space, so character offsets remain
    valid for mapping back to the original un-normalized text.
    """
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ")    # NBSP → space
    text = text.replace("\u202f", " ")  # narrow NBSP → space
    return text


# ---------------------------------------------------------------------------
# CommentWriter — self-contained comment injection (in-memory)
# ---------------------------------------------------------------------------

class CommentWriter:
    """Writes Word-compatible comments to in-memory .docx XML structures.

    Manages all 4 comment metadata files (comments.xml, commentsExtended.xml,
    commentsIds.xml, commentsExtensible.xml), relationships, content types,
    and document.xml range markers.  Operates on DOMs and byte buffers —
    no filesystem access.
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

    def __init__(self, zip_entries, rels_dom, ct_dom, author, timestamp):
        """Initialize comment writer with in-memory ZIP data.

        Args:
            zip_entries: {zip_name: bytes} of existing ZIP entries
            rels_dom: DOM for word/_rels/document.xml.rels (modified in place)
            ct_dom: DOM for [Content_Types].xml (modified in place)
            author: author name for comments
            timestamp: ISO timestamp string
        """
        self._zip_entries = zip_entries
        self._rels_dom = rels_dom
        self._ct_dom = ct_dom
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

        Writes comment metadata to the 4 comment XML DOMs and inserts
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

    def get_entries(self):
        """Return {zip_name: bytes} for all comment metadata files."""
        if not self._dirty:
            return {}
        entries = {}
        for name, cdom in (
            ("word/comments.xml", self._comments_dom),
            ("word/commentsExtended.xml", self._extended_dom),
            ("word/commentsIds.xml", self._ids_dom),
            ("word/commentsExtensible.xml", self._extensible_dom),
        ):
            if cdom is not None:
                entries[name] = serialize_dom_utf8(cdom)
        return entries

    # -- Internal helpers --------------------------------------------------

    def _ensure_setup(self):
        """Load or create all comment XML DOMs; update rels + content types."""
        if self._setup_done:
            return
        self._comments_dom = self._load_or_create(
            "word/comments.xml", _COMMENTS_TEMPLATE
        )
        self._extended_dom = self._load_or_create(
            "word/commentsExtended.xml", _COMMENTS_EXT_TEMPLATE
        )
        self._ids_dom = self._load_or_create(
            "word/commentsIds.xml", _COMMENTS_IDS_TEMPLATE
        )
        self._extensible_dom = self._load_or_create(
            "word/commentsExtensible.xml", _COMMENTS_EXTENSIBLE_TEMPLATE
        )
        self._ensure_relationships()
        self._ensure_content_types()
        self._setup_done = True

    def _load_or_create(self, zip_name, template):
        """Load existing XML from ZIP entry or create from template."""
        if zip_name in self._zip_entries:
            return defusedxml.minidom.parseString(self._zip_entries[zip_name])
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
        """Insert commentRangeStart/End + commentReference into document DOM."""
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
        """Add relationship entries for comment + people files."""
        root = self._rels_dom.documentElement
        root_ns = root.namespaceURI or ""

        existing = set()
        max_rid = 0
        for rel in self._rels_dom.getElementsByTagName("Relationship"):
            existing.add(rel.getAttribute("Type"))
            rid = rel.getAttribute("Id")
            if rid.startswith("rId"):
                try:
                    max_rid = max(max_rid, int(rid[3:]))
                except ValueError:
                    pass

        for target, rel_type in self._RELATIONSHIPS.items():
            if rel_type not in existing:
                max_rid += 1
                elem = self._rels_dom.createElementNS(root_ns, "Relationship")
                elem.setAttribute("Id", f"rId{max_rid}")
                elem.setAttribute("Type", rel_type)
                elem.setAttribute("Target", target)
                root.appendChild(elem)

    def _ensure_content_types(self):
        """Add Override entries for comment + people files."""
        root = self._ct_dom.documentElement
        root_ns = root.namespaceURI or ""

        existing = set()
        for override in self._ct_dom.getElementsByTagName("Override"):
            existing.add(override.getAttribute("PartName"))

        for part_name, content_type in self._CONTENT_TYPES.items():
            if part_name not in existing:
                elem = self._ct_dom.createElementNS(root_ns, "Override")
                elem.setAttribute("PartName", part_name)
                elem.setAttribute("ContentType", content_type)
                root.appendChild(elem)


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

    # Try exact match first, then normalized match for NBSP/entity mismatches
    match_start = full_text.find(old_text)
    if match_start != -1:
        match_end = match_start + len(old_text)
    else:
        norm_full = _normalize_for_search(full_text)
        norm_old = _normalize_for_search(old_text)
        match_start = norm_full.find(norm_old)
        if match_start == -1:
            return {
                "edit_index": edit_index,
                "status": "error",
                "message": f"Text not found in paragraph runs: {old_text[:80]}..."
            }
        match_end = match_start + len(norm_old)

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

    # Find the run containing the anchor text (with normalized matching)
    anchor_run = None
    if anchor_text:
        norm_anchor = _normalize_for_search(anchor_text)
        for run in para.getElementsByTagName("w:r"):
            if norm_anchor in _normalize_for_search(get_run_text(run)):
                anchor_run = run
                break

    if anchor_run:
        start_elem = anchor_run
        end_elem = anchor_run
    else:
        # Anchor spans multiple runs or not found — attach to whole
        # paragraph.  Use the first and last child elements so that
        # markers stay *inside* the w:p (a bare w:r in w:body is
        # invalid OOXML and causes Word to reject the file).
        children = [
            c for c in para.childNodes
            if c.nodeType == c.ELEMENT_NODE
        ]
        if children:
            start_elem = children[0]
            end_elem = children[-1]
        else:
            start_elem = para
            end_elem = para

    try:
        comment_writer.add_comment(
            comment_id=next_id(),
            text=comment_text,
            dom=dom,
            start_elem=start_elem,
            end_elem=end_elem,
        )
    except Exception as e:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Failed to add comment: {e}",
        }

    return {"edit_index": edit_index, "status": "ok"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _die(message):
    """Print error JSON and exit."""
    print(json.dumps({"status": "error", "message": message}))
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(
        description="Apply batch edits to a .docx file as tracked changes"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to original .docx file",
    )
    parser.add_argument(
        "--edits", required=True,
        help="Path to edits JSON file",
    )
    parser.add_argument(
        "--author", default="Claude",
        help="Author name for tracked changes",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output .docx path",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        _die(f"Input file not found: {args.input}")

    edits_path = Path(args.edits)
    if not edits_path.is_file():
        _die(f"Edits file not found: {args.edits}")

    try:
        edits = json.loads(edits_path.read_text())
    except json.JSONDecodeError as e:
        _die(f"Invalid JSON in edits file: {e}")

    if not isinstance(edits, list):
        _die("Edits must be a JSON array")

    # ------------------------------------------------------------------
    # Read all ZIP entries into memory
    # ------------------------------------------------------------------
    try:
        with zipfile.ZipFile(input_path, 'r') as zf:
            zip_entries = {name: zf.read(name) for name in zf.namelist()}
    except zipfile.BadZipFile as e:
        _die(f"Not a valid .docx file: {e}")

    if "word/document.xml" not in zip_entries:
        _die("word/document.xml not found in input file")

    # ------------------------------------------------------------------
    # Parse DOMs for files we may modify
    # ------------------------------------------------------------------
    doc_dom = defusedxml.minidom.parseString(
        zip_entries["word/document.xml"]
    )

    rels_key = "word/_rels/document.xml.rels"
    if rels_key in zip_entries:
        rels_dom = defusedxml.minidom.parseString(zip_entries[rels_key])
    else:
        rels_dom = defusedxml.minidom.parseString(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns='
            '"http://schemas.openxmlformats.org/package/2006/relationships"/>'
        )

    ct_key = "[Content_Types].xml"
    ct_dom = defusedxml.minidom.parseString(zip_entries[ct_key])

    next_id = make_id_generator(doc_dom)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------
    # Set up people.xml and comment writer
    # ------------------------------------------------------------------
    people_dom, people_modified = ensure_people_xml(
        zip_entries.get("word/people.xml"), args.author
    )
    comment_writer = CommentWriter(
        zip_entries, rels_dom, ct_dom, args.author, timestamp
    )

    # ------------------------------------------------------------------
    # Apply edits
    # ------------------------------------------------------------------
    results = []
    errors = []

    for i, edit in enumerate(edits):
        edit_type = edit.get("type", "replace")

        if edit_type == "replace":
            result = apply_replace(
                doc_dom, edit, i, args.author, timestamp, next_id,
                comment_writer,
            )
        elif edit_type == "comment":
            result = apply_comment(doc_dom, edit, i, next_id, comment_writer)
        else:
            result = {
                "edit_index": i,
                "status": "error",
                "message": f"Unknown edit type: {edit_type}",
            }

        results.append(result)
        if result["status"] == "error":
            errors.append(result)

    # ------------------------------------------------------------------
    # Build output ZIP
    # ------------------------------------------------------------------
    # Always-modified entries
    modified = {
        "word/document.xml": serialize_dom_utf8(doc_dom),
    }

    # People.xml (may be new or updated)
    if people_modified:
        people_bytes = serialize_dom_utf8(people_dom)
        if "word/people.xml" in zip_entries:
            modified["word/people.xml"] = people_bytes
        # else: handled as 'added' below

    # Comment entries (rels + ct are modified in place by CommentWriter)
    added = {}
    if comment_writer._dirty:
        modified[rels_key] = serialize_dom_utf8(rels_dom)
        modified[ct_key] = serialize_dom_utf8(ct_dom)
        for name, data in comment_writer.get_entries().items():
            if name in zip_entries:
                modified[name] = data
            else:
                added[name] = data

    # People.xml as new entry if it didn't exist
    if people_modified and "word/people.xml" not in zip_entries:
        added["word/people.xml"] = serialize_dom_utf8(people_dom)

    build_output_zip(input_path, args.output, modified, added)

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

    print(json.dumps(summary, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
