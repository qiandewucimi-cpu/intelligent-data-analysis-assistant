"""Export the AI business report (Markdown text) into a downloadable Word document.

The GLM-generated report is Markdown. We keep the conversion lightweight but cover
the elements the model actually emits: headings, bold inline text, bullet/numbered
lists, simple pipe tables and plain paragraphs. Anything we do not recognise is
written out as a normal paragraph so no content is ever lost.
"""

from __future__ import annotations

import io
import re

from docx import Document
from docx.shared import Pt


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def _add_runs_with_bold(paragraph, text: str) -> None:
    """Adds text to a paragraph, turning **bold** / __bold__ markers into bold runs."""

    cursor = 0
    for match in _BOLD_RE.finditer(text):
        if match.start() > cursor:
            paragraph.add_run(_strip_inline_markers(text[cursor : match.start()]))
        bold_text = match.group(1) if match.group(1) is not None else match.group(2)
        run = paragraph.add_run(_strip_inline_markers(bold_text))
        run.bold = True
        cursor = match.end()
    if cursor < len(text):
        paragraph.add_run(_strip_inline_markers(text[cursor:]))


def _strip_inline_markers(text: str) -> str:
    """Removes leftover inline Markdown markers that we do not render specially."""

    text = text.replace("`", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)  # stray single emphasis asterisks
    return text


def markdown_to_docx_bytes(markdown_text: str, title: str = "AI 分析报告") -> bytes:
    """Converts the Markdown report into a .docx file and returns its bytes."""

    document = Document()
    if title:
        document.add_heading(title, level=0)

    lines = (markdown_text or "").replace("\r\n", "\n").split("\n")
    index = 0
    in_code_block = False
    total = len(lines)

    while index < total:
        line = lines[index]
        stripped = line.strip()

        # Fenced code blocks: keep the inner text verbatim as monospace-ish paragraphs.
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            index += 1
            continue
        if in_code_block:
            paragraph = document.add_paragraph(line)
            for run in paragraph.runs:
                run.font.name = "Consolas"
                run.font.size = Pt(10)
            index += 1
            continue

        if not stripped:
            index += 1
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            heading = document.add_heading(level=level)
            _add_runs_with_bold(heading, heading_match.group(2).strip())
            index += 1
            continue

        # Pipe table: a header row, a separator row, then data rows.
        if _is_table_row(line) and index + 1 < total and _TABLE_SEP_RE.match(lines[index + 1]):
            header_cells = _split_table_row(line)
            body_rows = []
            cursor = index + 2
            while cursor < total and _is_table_row(lines[cursor]):
                body_rows.append(_split_table_row(lines[cursor]))
                cursor += 1
            _add_table(document, header_cells, body_rows)
            index = cursor
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            paragraph = document.add_paragraph(style="List Bullet")
            _add_runs_with_bold(paragraph, bullet_match.group(1).strip())
            index += 1
            continue

        ordered_match = _ORDERED_RE.match(line)
        if ordered_match:
            paragraph = document.add_paragraph(style="List Number")
            _add_runs_with_bold(paragraph, ordered_match.group(1).strip())
            index += 1
            continue

        paragraph = document.add_paragraph()
        _add_runs_with_bold(paragraph, stripped)
        index += 1

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_table(document, header_cells: list[str], body_rows: list[list[str]]) -> None:
    column_count = len(header_cells)
    if column_count == 0:
        return

    table = document.add_table(rows=1, cols=column_count)
    table.style = "Light Grid Accent 1"

    header_row = table.rows[0].cells
    for col_index, cell_text in enumerate(header_cells):
        paragraph = header_row[col_index].paragraphs[0]
        _add_runs_with_bold(paragraph, cell_text)
        for run in paragraph.runs:
            run.bold = True

    for row in body_rows:
        cells = table.add_row().cells
        for col_index in range(column_count):
            value = row[col_index] if col_index < len(row) else ""
            paragraph = cells[col_index].paragraphs[0]
            _add_runs_with_bold(paragraph, value)
