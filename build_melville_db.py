#!/usr/bin/env python3
"""Build a SQLite database for Melville's prose fiction corpus."""

import json
import os
import re
import sqlite3
from collections import Counter


CATALOG_PATH = "CATALOG.json"
OUT_DIR = os.path.join("docs", "data")
DB_PATH = os.path.join(OUT_DIR, "contabulate.db")

START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK"
END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK"

WORK_ABBRS = {
    "typee": "TYPE",
    "omoo": "OMOO",
    "mardi": "MARD",
    "redburn": "REDB",
    "white-jacket": "WJ",
    "moby-dick": "MD",
    "pierre": "PIER",
    "bartleby": "BART",
    "israel-potter": "IP",
    "confidence-man": "CM",
    "billy-budd": "BB",
}

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

WORD_NUMBERS = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "ELEVEN": 11,
    "TWELVE": 12,
    "THIRTEEN": 13,
    "FOURTEEN": 14,
    "FIFTEEN": 15,
    "SIXTEEN": 16,
    "SEVENTEEN": 17,
    "EIGHTEEN": 18,
    "NINETEEN": 19,
    "TWENTY": 20,
    "TWENTY-ONE": 21,
    "TWENTY-TWO": 22,
    "TWENTY-THREE": 23,
    "TWENTY-FOUR": 24,
    "TWENTY-FIVE": 25,
    "TWENTY-SIX": 26,
    "TWENTY-SEVEN": 27,
    "TWENTY-EIGHT": 28,
    "TWENTY-NINE": 29,
    "THIRTY": 30,
    "THIRTY-ONE": 31,
    "THIRTY-TWO": 32,
    "THIRTY-THREE": 33,
    "THIRTY-FOUR": 34,
}


def load_catalog():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def strip_gutenberg(text):
    start = text.find(START_MARKER)
    if start != -1:
        start = text.find("\n", start)
        start = len(text) if start == -1 else start + 1
    else:
        start = 0

    end = text.find(END_MARKER)
    if end == -1:
        end = len(text)

    return text[start:end].strip()


def roman_to_int(value):
    total = 0
    prev = 0
    for ch in reversed(value.upper()):
        current = ROMAN_VALUES.get(ch)
        if current is None:
            raise ValueError(f"Invalid Roman numeral: {value}")
        if current < prev:
            total -= current
        else:
            total += current
            prev = current
    return total


def chapter_number_from_token(token):
    token = token.strip().strip(".").upper()
    if token.isdigit():
        return int(token)
    if token in WORD_NUMBERS:
        return WORD_NUMBERS[token]
    if re.fullmatch(r"[IVXLCDM]+", token):
        return roman_to_int(token)
    raise ValueError(f"Unsupported chapter token: {token}")


def clean_paragraph(text):
    return re.sub(r"\s+", " ", text).strip()


def paragraphs_from_text(text):
    return [clean_paragraph(p) for p in re.split(r"\n\s*\n", text) if clean_paragraph(p)]


def tokenize(text):
    return re.findall(r"[a-zA-Z']+(?:-[a-zA-Z']+)*", text.lower())


def build_ngrams(tokens, n):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def next_nonempty(lines, start_idx):
    for idx in range(start_idx, len(lines)):
        if lines[idx].strip():
            return idx, lines[idx].strip()
    return None, None


def looks_like_title(line):
    if not line:
        return False
    if re.fullmatch(r"[IVXLCDM]+\.?", line):
        return False
    if re.match(r"^(CHAPTER|Chapter|BOOK|PART)\b", line):
        return False
    letters = re.findall(r"[A-Za-z]", line)
    if not letters:
        return False
    uppercase_letters = [ch for ch in letters if ch.isupper()]
    return len(uppercase_letters) / len(letters) >= 0.7


def normalize_starts(starts):
    one_positions = [idx for idx, item in enumerate(starts) if item[1] == 1]
    if one_positions:
        starts = starts[one_positions[-1]:]
    return starts


def build_sections_from_starts(lines, starts):
    starts = normalize_starts(starts)
    sections = []
    for idx, item in enumerate(starts):
        if len(item) == 4:
            line_idx, number, label_prefix, inline_title = item
        else:
            line_idx, number, label_prefix = item
            inline_title = ""
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body_start = line_idx + 1
        title = inline_title.strip().rstrip(".")
        title_idx, title_line = next_nonempty(lines, body_start)
        if not title and title_idx is not None and title_idx < end_idx and looks_like_title(title_line):
            title = title_line.strip().rstrip(".")
            body_start = title_idx + 1
        body = "\n".join(lines[body_start:end_idx]).strip()
        paragraphs = paragraphs_from_text(body)
        if not paragraphs:
            continue
        label = f"{label_prefix} {number}"
        sections.append(
            {
                "number": number,
                "label": label,
                "title": title,
                "paragraphs": paragraphs,
            }
        )
    return sections


def parse_standard_chapters(text):
    lines = text.splitlines()
    starts = []
    patterns = [
        (re.compile(r"^CHAPTER\s+([IVXLCDM]+|\d+)\.\s*$"), "Chapter"),
        (re.compile(r"^CHAPTER\s+([IVXLCDM]+|\d+)\.\s+(.+?)\s*$"), "Chapter"),
        (re.compile(r"^Chapter\s+([IVXLCDM]+|\d+)\s*$"), "Chapter"),
        (re.compile(r"^Chapter\s+([IVXLCDM]+|\d+)\s+(.+?)\s*$"), "Chapter"),
    ]
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        for pattern, label_prefix in patterns:
            match = pattern.match(line)
            if not match:
                continue
            number = chapter_number_from_token(match.group(1))
            inline_title = match.group(2).strip() if match.lastindex and match.lastindex > 1 else ""
            starts.append((idx, number, label_prefix, inline_title))
            break
    return build_sections_from_starts(lines, starts)


def parse_typee_chapters(text):
    lines = text.splitlines()
    starts = []
    pattern = re.compile(r"^CHAPTER\s+([A-Z-]+)\s*$")
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = pattern.match(line)
        if not match:
            continue
        token = match.group(1)
        if token not in WORD_NUMBERS:
            continue
        starts.append((idx, WORD_NUMBERS[token], "Chapter", ""))
    return build_sections_from_starts(lines, starts)


def parse_pierre_books(text):
    lines = text.splitlines()
    starts = []
    pattern = re.compile(r"^BOOK\s+([IVXLCDM]+)\.\s*$")
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = pattern.match(line)
        if not match:
            continue
        number = roman_to_int(match.group(1))
        starts.append((idx, number, "Book", ""))
    return build_sections_from_starts(lines, starts)


def extract_billy_budd(text):
    start_match = re.search(r"(?m)^\s*BILLY BUDD, FORETOPMAN\s*$", text)
    if not start_match:
        raise ValueError("Could not find Billy Budd start marker")
    end_match = re.search(r"(?m)^\s*DANIEL ORME\s*$", text[start_match.end():])
    if not end_match:
        raise ValueError("Could not find Billy Budd end marker")
    return text[start_match.start():start_match.end() + end_match.start()].strip()


def parse_billy_budd(text):
    lines = text.splitlines()
    starts = []
    body_started = False
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line == "BILLY BUDD, FORETOPMAN":
            body_started = True
            continue
        if not body_started:
            continue
        if re.fullmatch(r"[IVXLCDM]+", line):
            number = roman_to_int(line)
            starts.append((idx, number, "Chapter", ""))
    return build_sections_from_starts(lines, starts)


def parse_work_sections(work):
    work_id = work["id"]
    if work_id == "mardi":
        combined = []
        section_offset = 0
        for path in work["files"]:
            body = strip_gutenberg(read_file(path))
            sections = parse_standard_chapters(body)
            if not sections:
                raise ValueError(f"No chapters found in {path}")
            for section in sections:
                section = dict(section)
                section["number"] += section_offset
                section["label"] = f"Chapter {section['number']}"
                combined.append(section)
            section_offset = combined[-1]["number"]
        return combined
    if work_id == "bartleby":
        body = strip_gutenberg(read_file(work["file"]))
        return [{"number": 1, "label": "Chapter 1", "title": "", "paragraphs": paragraphs_from_text(body)}]
    if work_id == "billy-budd":
        body = strip_gutenberg(read_file(work["file"]))
        extracted = extract_billy_budd(body)
        sections = parse_billy_budd(extracted)
        if not sections:
            raise ValueError("No Billy Budd chapters found")
        return sections
    if work_id == "typee":
        body = strip_gutenberg(read_file(work["file"]))
        sections = parse_typee_chapters(body)
        if not sections:
            raise ValueError("No Typee chapters found")
        return sections
    if work_id == "pierre":
        body = strip_gutenberg(read_file(work["file"]))
        sections = parse_pierre_books(body)
        if not sections:
            raise ValueError("No Pierre book sections found")
        return sections

    body = strip_gutenberg(read_file(work["file"]))
    sections = parse_standard_chapters(body)
    if not sections:
        return [{"number": 1, "label": "Chapter 1", "title": "", "paragraphs": paragraphs_from_text(body)}]
    return sections


def create_schema(conn):
    conn.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;

        DROP TABLE IF EXISTS trigrams;
        DROP TABLE IF EXISTS bigrams;
        DROP TABLE IF EXISTS tokens;
        DROP TABLE IF EXISTS lines;
        DROP TABLE IF EXISTS segments;
        DROP TABLE IF EXISTS works;

        CREATE TABLE works (
          work_id INTEGER PRIMARY KEY,
          location TEXT,
          title TEXT,
          abbr TEXT,
          genre TEXT,
          year INTEGER,
          num_sections INTEGER,
          num_segments INTEGER,
          total_words INTEGER,
          total_lines INTEGER
        );

        CREATE TABLE segments (
          segment_id INTEGER PRIMARY KEY,
          canonical_id TEXT,
          location TEXT,
          work_id INTEGER REFERENCES works(work_id),
          work_title TEXT,
          work_abbr TEXT,
          genre TEXT,
          section INTEGER,
          position INTEGER,
          heading TEXT,
          total_words INTEGER,
          unique_words INTEGER,
          section_label TEXT,
          position_label TEXT
        );

        CREATE TABLE lines (
          line_id INTEGER PRIMARY KEY,
          work_id INTEGER REFERENCES works(work_id),
          canonical_id TEXT,
          location TEXT,
          section INTEGER,
          position INTEGER,
          line_num INTEGER,
          speaker TEXT DEFAULT '',
          text TEXT,
          section_label TEXT
        );

        CREATE TABLE tokens (
          token TEXT NOT NULL,
          segment_id INTEGER NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (token, segment_id)
        );
        CREATE INDEX idx_tokens_segment_id ON tokens(segment_id);

        CREATE TABLE bigrams (
          bigram TEXT NOT NULL,
          segment_id INTEGER NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (bigram, segment_id)
        );
        CREATE INDEX idx_bigrams_segment_id ON bigrams(segment_id);

        CREATE TABLE trigrams (
          trigram TEXT NOT NULL,
          segment_id INTEGER NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (trigram, segment_id)
        );
        CREATE INDEX idx_trigrams_segment_id ON trigrams(segment_id);

        CREATE INDEX idx_segments_work_id ON segments(work_id);
        CREATE INDEX idx_segments_location ON segments(location);
        CREATE INDEX idx_lines_work_id ON lines(work_id);
        CREATE INDEX idx_lines_location ON lines(location);
        """
    )


def insert_rows(conn, catalog):
    total_words = 0
    total_segments = 0
    total_lines = 0
    unique_unigrams = set()
    unique_bigrams = set()
    unique_trigrams = set()

    work_rows = []
    segment_rows = []
    line_rows = []
    unigram_rows = []
    bigram_rows = []
    trigram_rows = []
    per_work_stats = []

    segment_id = 0

    for work_idx, work in enumerate(catalog, start=1):
        sections = parse_work_sections(work)
        if not sections:
            raise ValueError(f"No sections found for {work['title']}")

        work_abbr = WORK_ABBRS.get(work["id"], re.sub(r"[^A-Z]", "", work["title"].upper())[:6] or f"W{work_idx}")
        work_location = f"{work_idx:02d}.{work_abbr}"
        work_total_words = 0
        work_total_segments = 0

        for section in sections:
            section_num = section["number"]
            section_label = section["label"]
            heading_prefix = section["title"] or section_label

            for para_idx, para in enumerate(section["paragraphs"], start=1):
                segment_id += 1
                tokens = tokenize(para)
                token_counts = Counter(tokens)
                bigram_counts = Counter(build_ngrams(tokens, 2))
                trigram_counts = Counter(build_ngrams(tokens, 3))
                word_count = len(tokens)
                unique_count = len(token_counts)

                canonical_id = f"{work_abbr}.{section_num}.{para_idx}"
                location = f"{work_location}.{section_num:03d}.{para_idx:04d}"

                segment_rows.append(
                    (
                        segment_id,
                        canonical_id,
                        location,
                        work_idx,
                        work["title"],
                        work_abbr,
                        work["genre"],
                        section_num,
                        para_idx,
                        f"{heading_prefix}, \u00b6{para_idx}",
                        word_count,
                        unique_count,
                        section_label,
                        f"\u00b6{para_idx}",
                    )
                )
                line_rows.append(
                    (
                        segment_id,
                        work_idx,
                        canonical_id,
                        location,
                        section_num,
                        para_idx,
                        para_idx,
                        "",
                        para,
                        section_label,
                    )
                )

                unigram_rows.extend((token, segment_id, count) for token, count in token_counts.items())
                bigram_rows.extend((ngram, segment_id, count) for ngram, count in bigram_counts.items())
                trigram_rows.extend((ngram, segment_id, count) for ngram, count in trigram_counts.items())

                unique_unigrams.update(token_counts)
                unique_bigrams.update(bigram_counts)
                unique_trigrams.update(trigram_counts)

                work_total_words += word_count
                work_total_segments += 1
                total_words += word_count
                total_segments += 1
                total_lines += 1

        work_rows.append(
            (
                work_idx,
                work_location,
                work["title"],
                work_abbr,
                work["genre"],
                work["year"],
                len(sections),
                work_total_segments,
                work_total_words,
                work_total_segments,
            )
        )
        per_work_stats.append(
            {
                "title": work["title"],
                "year": work["year"],
                "chapters": len(sections),
                "paragraphs": work_total_segments,
                "words": work_total_words,
            }
        )

    conn.executemany(
        """
        INSERT INTO works (
          work_id, location, title, abbr, genre, year,
          num_sections, num_segments, total_words, total_lines
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        work_rows,
    )
    conn.executemany(
        """
        INSERT INTO segments (
          segment_id, canonical_id, location, work_id, work_title, work_abbr,
          genre, section, position, heading, total_words, unique_words,
          section_label, position_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        segment_rows,
    )
    conn.executemany(
        """
        INSERT INTO lines (
          line_id, work_id, canonical_id, location, section, position,
          line_num, speaker, text, section_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        line_rows,
    )
    conn.executemany("INSERT INTO tokens (token, segment_id, count) VALUES (?, ?, ?)", unigram_rows)
    conn.executemany("INSERT INTO bigrams (bigram, segment_id, count) VALUES (?, ?, ?)", bigram_rows)
    conn.executemany("INSERT INTO trigrams (trigram, segment_id, count) VALUES (?, ?, ?)", trigram_rows)
    conn.commit()
    conn.execute("ANALYZE")

    return {
        "works": len(work_rows),
        "segments": total_segments,
        "lines": total_lines,
        "words": total_words,
        "unique_unigrams": len(unique_unigrams),
        "unique_bigrams": len(unique_bigrams),
        "unique_trigrams": len(unique_trigrams),
        "db_size": os.path.getsize(DB_PATH),
        "per_work_stats": per_work_stats,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    catalog = load_catalog()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        stats = insert_rows(conn, catalog)
    finally:
        conn.close()

    print(f"Database: {DB_PATH}")
    for work in stats["per_work_stats"]:
        print(
            f"{work['title']} ({work['year']}): "
            f"{work['chapters']} chapters, "
            f"{work['paragraphs']} paragraphs, "
            f"{work['words']:,} words"
        )
    print(f"Works: {stats['works']}")
    print(f"Segments: {stats['segments']}")
    print(f"Lines: {stats['lines']}")
    print(f"Total words: {stats['words']:,}")
    print(f"Unique unigrams: {stats['unique_unigrams']:,}")
    print(f"Unique bigrams: {stats['unique_bigrams']:,}")
    print(f"Unique trigrams: {stats['unique_trigrams']:,}")
    print(f"File size: {stats['db_size']:,} bytes")


if __name__ == "__main__":
    main()
