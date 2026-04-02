#!/usr/bin/env python3
"""
Tests for the Contabulate SQLite database.
Run after build_db.py generates docs/data/contabulate.db

Usage: python3 tests/test_db.py
"""

import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data', 'contabulate.db')

def connect():
    if not os.path.exists(DB_PATH):
        print(f"FATAL: Database not found at {DB_PATH}")
        print("Run build_db.py first.")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        failed += 1


def test_schema(db):
    """Verify all expected tables and indexes exist."""
    print("\n=== Schema ===")
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    
    for expected in ['works', 'segments', 'lines', 'tokens', 'bigrams', 'trigrams']:
        test(f"Table '{expected}' exists", expected in tables, f"Found: {tables}")


def test_works(db):
    """Verify works (chapters) data."""
    print("\n=== Works ===")
    cur = db.execute("SELECT COUNT(*) FROM works")
    count = cur.fetchone()[0]
    test("Has works", count > 0, f"count={count}")
    test("Has multiple works", count >= 5, f"count={count}")
    
    # Check Moby Dick specific
    cur = db.execute("SELECT title FROM works WHERE title='Moby-Dick'")
    row = cur.fetchone()
    test("Moby-Dick exists", row is not None, f"got: {row}")
    
    # Total words
    cur = db.execute("SELECT SUM(total_words) FROM works")
    total = cur.fetchone()[0]
    test("Total words > 200K", total and total > 200000, f"total={total}")
    test("Total words > 1M", total and total > 1000000, f"total={total}")


def test_segments(db):
    """Verify segments (paragraphs) data."""
    print("\n=== Segments ===")
    cur = db.execute("SELECT COUNT(*) FROM segments")
    count = cur.fetchone()[0]
    test("Has segments", count > 0, f"count={count}")
    test("Has >2000 paragraphs", count > 2000, f"count={count}")
    
    # Check referential integrity
    cur = db.execute("""
        SELECT COUNT(*) FROM segments s
        WHERE NOT EXISTS (SELECT 1 FROM works w WHERE w.work_id = s.work_id)
    """)
    orphans = cur.fetchone()[0]
    test("No orphan segments", orphans == 0, f"orphans={orphans}")


def test_lines(db):
    """Verify lines (full text) data."""
    print("\n=== Lines ===")
    cur = db.execute("SELECT COUNT(*) FROM lines")
    count = cur.fetchone()[0]
    test("Has lines", count > 0, f"count={count}")
    
    # Check that lines have text
    cur = db.execute("SELECT COUNT(*) FROM lines WHERE text IS NULL OR text = ''")
    empty = cur.fetchone()[0]
    test("No empty lines", empty == 0, f"empty={empty}")
    
    # Check famous opening
    cur = db.execute("SELECT text FROM lines WHERE work_id = (SELECT work_id FROM works WHERE title='Moby-Dick') ORDER BY line_num LIMIT 1")
    row = cur.fetchone()
    test("Moby-Dick contains 'Ishmael'", 
         row and 'Ishmael' in row[0], 
         f"got: {row[0][:60] if row else 'None'}...")


def test_tokens(db):
    """Verify token index."""
    print("\n=== Tokens ===")
    cur = db.execute("SELECT COUNT(DISTINCT token) FROM tokens")
    unique = cur.fetchone()[0]
    test("Has unique tokens", unique > 0, f"unique={unique}")
    test("Has >10K unique words", unique > 10000, f"unique={unique}")
    
    # Search for 'whale'
    cur = db.execute("SELECT SUM(count) FROM tokens WHERE token = 'whale'")
    whale_count = cur.fetchone()[0]
    test("'whale' appears >100 times", whale_count and whale_count > 100, f"count={whale_count}")
    
    # Search for 'the' (most common)
    cur = db.execute("SELECT SUM(count) FROM tokens WHERE token = 'the'")
    the_count = cur.fetchone()[0]
    test("'the' appears >10000 times", the_count and the_count > 10000, f"count={the_count}")
    
    # Search for nonexistent word
    cur = db.execute("SELECT COUNT(*) FROM tokens WHERE token = 'xyzzyplugh'")
    none_count = cur.fetchone()[0]
    test("Nonexistent word returns 0", none_count == 0, f"count={none_count}")


def test_bigrams(db):
    """Verify bigram index."""
    print("\n=== Bigrams ===")
    cur = db.execute("SELECT COUNT(DISTINCT bigram) FROM bigrams")
    unique = cur.fetchone()[0]
    test("Has bigrams", unique > 0, f"unique={unique}")
    
    # 'white whale' should exist
    cur = db.execute("SELECT SUM(count) FROM bigrams WHERE bigram = 'white whale'")
    ww_count = cur.fetchone()[0]
    test("'white whale' bigram exists", ww_count and ww_count > 0, f"count={ww_count}")


def test_trigrams(db):
    """Verify trigram index."""
    print("\n=== Trigrams ===")
    cur = db.execute("SELECT COUNT(DISTINCT trigram) FROM trigrams")
    unique = cur.fetchone()[0]
    test("Has trigrams", unique > 0, f"unique={unique}")


def test_query_performance(db):
    """Verify queries are fast (indexed)."""
    print("\n=== Performance ===")
    import time
    
    # Exact token lookup
    start = time.perf_counter()
    for _ in range(100):
        db.execute("SELECT segment_id, count FROM tokens WHERE token = 'whale'").fetchall()
    elapsed = time.perf_counter() - start
    test(f"100x token lookup < 0.5s", elapsed < 0.5, f"took {elapsed:.3f}s")
    
    # Regex-like lookup (LIKE prefix)
    start = time.perf_counter()
    db.execute("SELECT DISTINCT token FROM tokens WHERE token LIKE 'whale%'").fetchall()
    elapsed = time.perf_counter() - start
    test(f"Prefix search < 0.1s", elapsed < 0.1, f"took {elapsed:.3f}s")


def test_consistency(db):
    """Cross-check data consistency."""
    print("\n=== Consistency ===")
    
    # segments count should equal lines count (1:1 for Moby Dick)
    seg_count = db.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    line_count = db.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
    test("Segments == Lines (1:1 mapping)", seg_count == line_count, 
         f"segments={seg_count} lines={line_count}")
    
    # Every segment should have at least one token
    cur = db.execute("""
        SELECT COUNT(*) FROM segments s
        WHERE NOT EXISTS (SELECT 1 FROM tokens t WHERE t.segment_id = s.segment_id)
    """)
    no_tokens = cur.fetchone()[0]
    # Some segments might legitimately have 0 words (empty paragraphs)
    test("Almost all segments have tokens (>95%)", 
         no_tokens < seg_count * 0.05,
         f"segments without tokens: {no_tokens}/{seg_count}")
    
    # Sum of token counts per segment should roughly equal segment total_words
    cur = db.execute("""
        SELECT s.segment_id, s.total_words, COALESCE(SUM(t.count), 0) as token_sum
        FROM segments s LEFT JOIN tokens t ON s.segment_id = t.segment_id
        GROUP BY s.segment_id
        HAVING ABS(s.total_words - token_sum) > 2
        LIMIT 5
    """)
    mismatches = cur.fetchall()
    test("Token counts match segment word counts (±2)", 
         len(mismatches) == 0,
         f"mismatches: {mismatches[:3]}")


def main():
    global passed, failed
    
    print(f"Testing database: {DB_PATH}")
    db = connect()
    
    test_schema(db)
    test_works(db)
    test_segments(db)
    test_lines(db)
    test_tokens(db)
    test_bigrams(db)
    test_trigrams(db)
    test_query_performance(db)
    test_consistency(db)
    
    db.close()
    
    print(f"\n{'='*40}")
    print(f"{passed} passed, {failed} failed out of {passed + failed} tests")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("All tests passed! ✅")


if __name__ == "__main__":
    main()
