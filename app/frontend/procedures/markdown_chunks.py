"""Split long Markdown reports at section and paragraph boundaries for display."""

import re


_HEADING = re.compile(r"^#{1,6}\s")


def split_markdown_report(source, target_chars=6000):
    """Return small renderable pieces without splitting normal Markdown sections."""
    if not source:
        return []

    sections = []
    section = []
    in_fence = False
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if _HEADING.match(line) and section and not in_fence:
            sections.append("".join(section))
            section = []
        section.append(line)
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
    if section:
        sections.append("".join(section))

    pieces = []
    for section_text in sections:
        if len(section_text) <= target_chars:
            pieces.append(section_text)
            continue
        # An unusually long section can still block the UI; split its prose
        # between paragraphs, keeping fenced code blocks intact.
        blocks = []
        block = []
        in_fence = False
        for line in section_text.splitlines(keepends=True):
            block.append(line)
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
            if not line.strip() and not in_fence:
                blocks.append("".join(block))
                block = []
        if block:
            blocks.append("".join(block))
        current = ""
        for block in blocks:
            if current and len(current) + len(block) > target_chars:
                pieces.append(current)
                current = ""
            current += block
        if current:
            pieces.append(current)

    chunks = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > target_chars:
            chunks.append(current)
            current = ""
        current += piece
    if current:
        chunks.append(current)
    return chunks
