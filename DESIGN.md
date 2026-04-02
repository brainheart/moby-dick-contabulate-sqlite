# Contabulate SQLite + WASM Architecture

## Goal
Replace JSON data files with a single SQLite database loaded via sql.js (WASM).
Enables scaling to much larger corpora (all of Melville, all of Henry James, etc.)
while staying on free static hosting (GitHub Pages).

## Database Schema

```sql
-- Works (books/chapters) — replaces plays.json
CREATE TABLE works (
  work_id INTEGER PRIMARY KEY,
  location TEXT,
  title TEXT,
  abbr TEXT,
  genre TEXT,
  year INTEGER,
  num_sections INTEGER,   -- chapters/acts
  num_segments INTEGER,   -- paragraphs/verses/scenes
  total_words INTEGER,
  total_lines INTEGER
);

-- Segments (paragraphs/verses/scenes) — replaces chunks.json
CREATE TABLE segments (
  segment_id INTEGER PRIMARY KEY,
  canonical_id TEXT,
  location TEXT,
  work_id INTEGER REFERENCES works(work_id),
  work_title TEXT,
  work_abbr TEXT,
  genre TEXT,
  section INTEGER,        -- act/chapter
  position INTEGER,       -- scene/verse/paragraph number
  heading TEXT,
  total_words INTEGER,
  unique_words INTEGER,
  section_label TEXT,
  position_label TEXT
);

-- Lines (full text) — replaces all_lines.json
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

-- Token index (unigrams) — replaces tokens.json
CREATE TABLE tokens (
  token TEXT NOT NULL,
  segment_id INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (token, segment_id)
);
CREATE INDEX idx_tokens_token ON tokens(token);

-- Bigram index — replaces tokens2.json
CREATE TABLE bigrams (
  bigram TEXT NOT NULL,
  segment_id INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (bigram, segment_id)
);
CREATE INDEX idx_bigrams_bigram ON bigrams(bigram);

-- Trigram index — replaces tokens3.json
CREATE TABLE trigrams (
  trigram TEXT NOT NULL,
  segment_id INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (trigram, segment_id)
);
CREATE INDEX idx_trigrams_trigram ON trigrams(trigram);
```

## Query Examples

```sql
-- Exact term lookup (replaces tokens[word])
SELECT segment_id, count FROM tokens WHERE token = 'whale';

-- Regex term lookup
SELECT DISTINCT segment_id, count FROM tokens WHERE token REGEXP '^whale';

-- Get segment details for matched segments
SELECT s.*, t.count 
FROM segments s JOIN tokens t ON s.segment_id = t.segment_id
WHERE t.token = 'whale'
ORDER BY t.count DESC;

-- Line text search
SELECT l.*, group_concat(token) as matched_tokens
FROM lines l, tokens t 
WHERE t.token = 'whale' AND t.segment_id = l.line_id
ORDER BY l.location;
```

## Architecture

1. **Build step** (Python): Parse text → SQLite .db file
2. **Deploy**: .db file served as static asset from GitHub Pages
3. **Client**: sql.js loads .db via fetch(), queries run in-browser
4. **Caching**: Browser caches the .db file (Cache-Control from GH Pages)

## File Size Estimates

| Corpus | JSON (current) | SQLite (estimated) |
|--------|---------------|-------------------|
| Moby Dick (215K words) | ~11 MB | ~3-5 MB |
| All Melville (~2M words) | ~100+ MB | ~20-30 MB |
| All Henry James (~4M words) | impractical | ~40-60 MB |
