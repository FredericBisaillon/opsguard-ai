import re
from dataclasses import dataclass

MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
NUMBERED_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*[.)]\s+(.{1,120})$")
SENTENCE_RE = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    character_count: int
    section_title: str | None
    start_char: int | None
    end_char: int | None


@dataclass(frozen=True)
class TextBlock:
    text: str
    section_title: str | None
    start_char: int
    end_char: int


@dataclass(frozen=True)
class TextPiece:
    text: str
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> list[TextChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")

    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative.")

    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")

    normalized_text = _normalize_text(text)
    if not normalized_text.strip():
        return []

    blocks = _parse_blocks(normalized_text)
    if not blocks:
        stripped_text = normalized_text.strip()
        start_char = normalized_text.find(stripped_text)
        blocks = [
            TextBlock(
                text=stripped_text,
                section_title=None,
                start_char=start_char,
                end_char=start_char + len(stripped_text),
            )
        ]

    chunk_candidates = _build_chunk_candidates(
        blocks=blocks,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )

    return [
        TextChunk(
            chunk_index=index,
            content=content,
            character_count=len(content),
            section_title=section_title,
            start_char=start_char,
            end_char=end_char,
        )
        for index, (content, section_title, start_char, end_char) in enumerate(
            chunk_candidates
        )
    ]


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = []
    for line in normalized.split("\n"):
        compacted_line = re.sub(r"[ \t]+", " ", line.strip())
        normalized_lines.append(compacted_line)

    normalized = "\n".join(normalized_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized)


def _parse_blocks(text: str) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    current_section: str | None = None
    current_lines: list[str] = []
    block_start: int | None = None
    block_end: int | None = None
    position = 0

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        stripped_line = line.strip()
        line_start = position
        line_end = line_start + len(line)
        position += len(raw_line)

        if not stripped_line:
            _append_block(
                blocks=blocks,
                current_lines=current_lines,
                section_title=current_section,
                start_char=block_start,
                end_char=block_end,
            )
            current_lines = []
            block_start = None
            block_end = None
            continue

        section_title = _section_title_from_heading(stripped_line)
        if section_title is not None:
            _append_block(
                blocks=blocks,
                current_lines=current_lines,
                section_title=current_section,
                start_char=block_start,
                end_char=block_end,
            )
            current_lines = []
            block_start = None
            block_end = None
            current_section = section_title
            continue

        if block_start is None:
            block_start = line_start

        current_lines.append(stripped_line)
        block_end = line_end

    _append_block(
        blocks=blocks,
        current_lines=current_lines,
        section_title=current_section,
        start_char=block_start,
        end_char=block_end,
    )

    return blocks


def _append_block(
    blocks: list[TextBlock],
    current_lines: list[str],
    section_title: str | None,
    start_char: int | None,
    end_char: int | None,
) -> None:
    if not current_lines or start_char is None or end_char is None:
        return

    block_text = "\n".join(current_lines).strip()
    if not block_text:
        return

    blocks.append(
        TextBlock(
            text=block_text,
            section_title=section_title,
            start_char=start_char,
            end_char=end_char,
        )
    )


def _section_title_from_heading(line: str) -> str | None:
    markdown_match = MARKDOWN_HEADING_RE.match(line)
    if markdown_match:
        return _clean_section_title(markdown_match.group(1))

    numbered_match = NUMBERED_HEADING_RE.match(line)
    if numbered_match and _looks_like_heading(line):
        return _clean_section_title(line)

    if _looks_like_uppercase_heading(line):
        return _clean_section_title(line)

    return None


def _clean_section_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().strip("#")).strip()


def _looks_like_heading(line: str) -> bool:
    if len(line) > 120:
        return False

    if line.endswith((".", ",", ";", ":")):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z-]*", line)
    if not words:
        return False

    lowercase_words = sum(1 for word in words if word[:1].islower())
    return lowercase_words <= max(1, len(words) // 3)


def _looks_like_uppercase_heading(line: str) -> bool:
    if len(line) > 80 or len(line) < 3:
        return False

    if line.startswith(("-", "*", "+")) or line.endswith((".", ",", ";", ":")):
        return False

    letters = [character for character in line if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def _build_chunk_candidates(
    blocks: list[TextBlock],
    max_chars: int,
    overlap_chars: int,
) -> list[tuple[str, str | None, int | None, int | None]]:
    chunk_candidates: list[tuple[str, str | None, int | None, int | None]] = []
    current_blocks: list[TextBlock] = []
    current_section: str | None = None

    def flush_current_blocks() -> None:
        nonlocal current_blocks, current_section
        if not current_blocks:
            return

        content = _compose_content(
            current_section,
            [block.text for block in current_blocks],
        )
        chunk_candidates.append(
            (
                content,
                current_section,
                current_blocks[0].start_char,
                current_blocks[-1].end_char,
            )
        )
        current_blocks = []
        current_section = None

    for block in blocks:
        block_content = _compose_content(block.section_title, [block.text])
        if len(block_content) > max_chars:
            flush_current_blocks()
            chunk_candidates.extend(
                _split_large_block(
                    block=block,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            continue

        if current_blocks and current_section != block.section_title:
            flush_current_blocks()

        candidate_blocks = [*current_blocks, block]
        candidate_content = _compose_content(
            block.section_title,
            [candidate_block.text for candidate_block in candidate_blocks],
        )
        if current_blocks and len(candidate_content) > max_chars:
            flush_current_blocks()

        current_blocks.append(block)
        current_section = block.section_title

    flush_current_blocks()
    return chunk_candidates


def _split_large_block(
    block: TextBlock,
    max_chars: int,
    overlap_chars: int,
) -> list[tuple[str, str | None, int | None, int | None]]:
    prefix_length = len(_section_prefix(block.section_title))
    max_body_chars = max(1, max_chars - prefix_length)
    pieces = _split_text_piece(
        text=block.text,
        absolute_start=block.start_char,
        max_chars=max_body_chars,
        overlap_chars=min(overlap_chars, max(0, max_body_chars // 3)),
    )

    return [
        (
            _compose_content(block.section_title, [piece.text]),
            block.section_title,
            piece.start_char,
            piece.end_char,
        )
        for piece in pieces
    ]


def _section_prefix(section_title: str | None) -> str:
    if section_title is None:
        return ""

    return f"Section: {section_title}\n\n"


def _compose_content(section_title: str | None, block_texts: list[str]) -> str:
    body = "\n\n".join(
        block_text.strip() for block_text in block_texts if block_text.strip()
    )
    if section_title is None:
        return body

    if not body:
        return f"Section: {section_title}"

    return f"{_section_prefix(section_title)}{body}"


def _split_text_piece(
    text: str,
    absolute_start: int,
    max_chars: int,
    overlap_chars: int,
) -> list[TextPiece]:
    if len(text) <= max_chars:
        return [
            TextPiece(
                text=text,
                start_char=absolute_start,
                end_char=absolute_start + len(text),
            )
        ]

    units = _logical_units(text)
    pieces: list[TextPiece] = []
    current_units: list[TextPiece] = []
    separator = "\n" if "\n" in text else " "

    def current_text(units_to_join: list[TextPiece]) -> str:
        return separator.join(unit.text for unit in units_to_join)

    def flush_current_units() -> None:
        nonlocal current_units
        if not current_units:
            return

        pieces.append(
            TextPiece(
                text=current_text(current_units),
                start_char=absolute_start + current_units[0].start_char,
                end_char=absolute_start + current_units[-1].end_char,
            )
        )
        current_units = _overlap_units(current_units, overlap_chars, separator)

    for unit in units:
        if len(unit.text) > max_chars:
            flush_current_units()
            pieces.extend(
                _split_long_unit(
                    unit=unit,
                    absolute_start=absolute_start,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            current_units = []
            continue

        candidate_units = [*current_units, unit]
        if current_units and len(current_text(candidate_units)) > max_chars:
            flush_current_units()
            candidate_units = [*current_units, unit]

        current_units = candidate_units

    if current_units:
        pieces.append(
            TextPiece(
                text=current_text(current_units),
                start_char=absolute_start + current_units[0].start_char,
                end_char=absolute_start + current_units[-1].end_char,
            )
        )

    return pieces


def _logical_units(text: str) -> list[TextPiece]:
    if "\n" in text:
        return _line_units(text)

    sentence_units = []
    for match in SENTENCE_RE.finditer(text):
        matched_text = match.group(0)
        stripped_text = matched_text.strip()
        if not stripped_text:
            continue

        leading_trim = len(matched_text) - len(matched_text.lstrip())
        trailing_trim = len(matched_text) - len(matched_text.rstrip())
        sentence_units.append(
            TextPiece(
                text=stripped_text,
                start_char=match.start() + leading_trim,
                end_char=match.end() - trailing_trim,
            )
        )
    if sentence_units:
        return sentence_units

    return [TextPiece(text=text, start_char=0, end_char=len(text))]


def _line_units(text: str) -> list[TextPiece]:
    units: list[TextPiece] = []
    position = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n").strip()
        if line:
            line_start = position + raw_line.find(line)
            units.append(
                TextPiece(
                    text=line,
                    start_char=line_start,
                    end_char=line_start + len(line),
                )
            )
        position += len(raw_line)

    return units


def _overlap_units(
    units: list[TextPiece],
    overlap_chars: int,
    separator: str,
) -> list[TextPiece]:
    if overlap_chars <= 0:
        return []

    selected_units: list[TextPiece] = []
    selected_length = 0
    separator_length = len(separator)
    for unit in reversed(units):
        next_length = len(unit.text)
        if selected_units:
            next_length += separator_length

        if selected_units and selected_length + next_length > overlap_chars:
            break

        selected_units.insert(0, unit)
        selected_length += next_length

    return selected_units


def _split_long_unit(
    unit: TextPiece,
    absolute_start: int,
    max_chars: int,
    overlap_chars: int,
) -> list[TextPiece]:
    pieces: list[TextPiece] = []
    start = 0
    effective_overlap = min(overlap_chars, max(0, max_chars // 3))

    while start < len(unit.text):
        end = min(start + max_chars, len(unit.text))
        if end < len(unit.text):
            word_boundary = unit.text.rfind(" ", start + max_chars // 2, end)
            if word_boundary > start:
                end = word_boundary

        raw_piece_text = unit.text[start:end]
        piece_text = raw_piece_text.strip()
        if piece_text:
            leading_trim = len(raw_piece_text) - len(raw_piece_text.lstrip())
            trailing_trim = len(raw_piece_text) - len(raw_piece_text.rstrip())
            pieces.append(
                TextPiece(
                    text=piece_text,
                    start_char=absolute_start + unit.start_char + start + leading_trim,
                    end_char=absolute_start + unit.start_char + end - trailing_trim,
                )
            )

        if end >= len(unit.text):
            break

        next_start = max(start + 1, end - effective_overlap)
        while next_start < len(unit.text) and unit.text[next_start].isspace():
            next_start += 1
        start = next_start

    return pieces
