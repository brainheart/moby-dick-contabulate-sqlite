#!/usr/bin/env python3
"""Build a SQLite database for the Moby-Dick Contabulate prototype."""

import os
import re
import sqlite3
from collections import Counter


RAW_FILE = "moby-dick-raw.txt"
OUT_DIR = os.path.join("docs", "data")
DB_PATH = os.path.join(OUT_DIR, "contabulate.db")


def read_text():
    with open(RAW_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    start = text.find(start_marker)
    if start != -1:
        start = text.index("\n", start) + 1
    else:
        start = 0
    end = text.find(end_marker)
    if end == -1:
        end = len(text)
    body = text[start:end].strip()

    lines = body.split("\n")
    etymology_indices = [i for i, line in enumerate(lines) if line.strip() == "ETYMOLOGY."]
    if len(etymology_indices) >= 2:
        body = "\n".join(lines[etymology_indices[1]:])

    return body.strip()


def parse_chapters(text):
    """Return a list of (chapter_num, title, paragraphs)."""
    chapters = []
    lines = text.split("\n")
    chapter_starts = []

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = re.match(r"^CHAPTER\s+(\d+)\.\s*(.+?)\.?\s*$", line)
        if match:
            chapter_starts.append((i, int(match.group(1)), match.group(2).strip().rstrip(".")))
        elif line == "ETYMOLOGY.":
            chapter_starts.append((i, 0, "Etymology"))
        elif line.startswith("EXTRACTS"):
            chapter_starts.append((i, -1, "Extracts"))
        elif line == "Epilogue.":
            chapter_starts.append((i, 136, "Epilogue"))

    for idx, (start_line, chapter_num, title) in enumerate(chapter_starts):
        end_line = chapter_starts[idx + 1][0] if idx + 1 < len(chapter_starts) else len(lines)
        body = "\n".join(lines[start_line + 1:end_line]).strip()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        chapters.append((chapter_num, title, paragraphs))

    return chapters


def tokenize(text):
    return re.findall(r"[a-zA-Z']+(?:-[a-zA-Z']+)*", text.lower())


def build_ngrams(tokens, n):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def work_metadata(chapter_num, title, work_id):
    if chapter_num <= 0:
        abbr = title[:4].upper()
        genre = "Preliminary"
        location = f"00.{abbr}"
    elif chapter_num == 136 and title == "Epilogue":
        abbr = "Epil"
        genre = "Epilogue"
        location = "99.Epil"
    else:
        abbr = f"Ch{chapter_num}"
        genre = "Novel"
        location = f"{chapter_num:02d}.{abbr}"

    return {
        "work_id": work_id,
        "location": location,
        "title": title,
        "abbr": abbr,
        "genre": genre,
        "year": 1851 if genre == "Novel" else None,
    }


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


def insert_rows(conn, chapters):
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

    segment_id = 0

    for work_idx, (chapter_num, title, paragraphs) in enumerate(chapters, start=1):
        meta = work_metadata(chapter_num, title, work_idx)
        work_total_words = 0

        for para_idx, para in enumerate(paragraphs, start=1):
            segment_id += 1
            tokens = tokenize(para)
            token_counts = Counter(tokens)
            bigram_counts = Counter(build_ngrams(tokens, 2))
            trigram_counts = Counter(build_ngrams(tokens, 3))
            word_count = len(tokens)
            unique_count = len(token_counts)

            canonical_id = f"{meta['abbr']}.{para_idx}"
            location = f"{meta['location']}.{para_idx:04d}"

            segment_rows.append(
                (
                    segment_id,
                    canonical_id,
                    location,
                    work_idx,
                    title,
                    meta["abbr"],
                    meta["genre"],
                    1,
                    para_idx,
                    f"{title}, \u00b6{para_idx}",
                    word_count,
                    unique_count,
                    title,
                    f"\u00b6{para_idx}",
                )
            )
            line_rows.append(
                (
                    segment_id,
                    work_idx,
                    canonical_id,
                    location,
                    1,
                    para_idx,
                    para_idx,
                    "",
                    para,
                    title,
                )
            )

            unigram_rows.extend((token, segment_id, count) for token, count in token_counts.items())
            bigram_rows.extend((ngram, segment_id, count) for ngram, count in bigram_counts.items())
            trigram_rows.extend((ngram, segment_id, count) for ngram, count in trigram_counts.items())

            unique_unigrams.update(token_counts)
            unique_bigrams.update(bigram_counts)
            unique_trigrams.update(trigram_counts)

            work_total_words += word_count
            total_words += word_count
            total_segments += 1
            total_lines += 1

        work_rows.append(
            (
                work_idx,
                meta["location"],
                title,
                meta["abbr"],
                meta["genre"],
                meta["year"],
                1,
                len(paragraphs),
                work_total_words,
                len(paragraphs),
            )
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
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    text = read_text()
    chapters = parse_chapters(text)
    if not chapters:
        raise SystemExit("ERROR: No chapters found")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        stats = insert_rows(conn, chapters)
    finally:
        conn.close()

    print(f"Database: {DB_PATH}")
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
