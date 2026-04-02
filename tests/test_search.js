#!/usr/bin/env node
/**
 * End-to-end search tests for the Contabulate SQLite database.
 * Tests the same queries the browser UI would make.
 * 
 * Requires: npm install sql.js (or uses the bundled version)
 * Usage: node tests/test_search.js
 */

const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, '..', 'docs', 'data', 'contabulate.db');

let passed = 0;
let failed = 0;

function test(name, condition, detail = '') {
  if (condition) {
    console.log(`  PASS: ${name}`);
    passed++;
  } else {
    console.log(`  FAIL: ${name} — ${detail}`);
    failed++;
  }
}

async function main() {
  // Load sql.js
  let initSqlJs;
  try {
    initSqlJs = require('sql.js');
  } catch (e) {
    console.log('Installing sql.js...');
    require('child_process').execSync('npm install sql.js', { stdio: 'inherit' });
    initSqlJs = require('sql.js');
  }

  const SQL = await initSqlJs();
  
  if (!fs.existsSync(DB_PATH)) {
    console.error(`Database not found: ${DB_PATH}`);
    console.error('Run build_db.py first.');
    process.exit(1);
  }

  const buffer = fs.readFileSync(DB_PATH);
  const db = new SQL.Database(buffer);

  // === Exact term search ===
  console.log('\n=== Exact Term Search ===');
  
  const whaleResults = db.exec("SELECT segment_id, count FROM tokens WHERE token = 'whale'");
  const whalePostings = whaleResults[0] ? whaleResults[0].values : [];
  test("'whale' returns postings", whalePostings.length > 50, `got ${whalePostings.length}`);
  
  const totalWhale = whalePostings.reduce((sum, r) => sum + r[1], 0);
  test("'whale' total count > 100", totalWhale > 100, `total=${totalWhale}`);
  
  const noResults = db.exec("SELECT segment_id, count FROM tokens WHERE token = 'xyzzyplugh'");
  test("Nonexistent word returns empty", noResults.length === 0 || noResults[0].values.length === 0);

  // === Bigram search ===
  console.log('\n=== Bigram Search ===');
  
  const wwResults = db.exec("SELECT segment_id, count FROM bigrams WHERE bigram = 'white whale'");
  const wwPostings = wwResults[0] ? wwResults[0].values : [];
  test("'white whale' bigram found", wwPostings.length > 0, `got ${wwPostings.length}`);

  const mobyResults = db.exec("SELECT segment_id, count FROM bigrams WHERE bigram = 'moby dick'");
  const mobyPostings = mobyResults[0] ? mobyResults[0].values : [];
  test("'moby dick' bigram found", mobyPostings.length > 0, `got ${mobyPostings.length}`);

  // === Trigram search ===
  console.log('\n=== Trigram Search ===');
  
  const triResults = db.exec("SELECT segment_id, count FROM trigrams WHERE trigram = 'the white whale'");
  const triPostings = triResults[0] ? triResults[0].values : [];
  test("'the white whale' trigram found", triPostings.length > 0, `got ${triPostings.length}`);

  // === Regex-like search (prefix) ===
  console.log('\n=== Prefix Search (LIKE) ===');
  
  const prefixResults = db.exec("SELECT DISTINCT token FROM tokens WHERE token LIKE 'whale%'");
  const prefixTokens = prefixResults[0] ? prefixResults[0].values.map(r => r[0]) : [];
  test("'whale%' finds multiple forms", prefixTokens.length > 1, `tokens: ${prefixTokens.join(', ')}`);
  test("'whale%' includes 'whale'", prefixTokens.includes('whale'), `tokens: ${prefixTokens}`);
  test("'whale%' includes 'whales'", prefixTokens.includes('whales'), `tokens: ${prefixTokens}`);

  // === Works (chapters) ===
  console.log('\n=== Works ===');
  
  const works = db.exec("SELECT work_id, title, abbr, total_words FROM works ORDER BY work_id");
  const workRows = works[0] ? works[0].values : [];
  test("Has chapters", workRows.length > 100, `count=${workRows.length}`);
  
  const ch1 = workRows.find(r => r[2] === 'Ch1');
  test("Chapter 1 'Loomings' exists", ch1 && ch1[1] === 'Loomings', `got: ${ch1}`);

  // === Lines with text ===
  console.log('\n=== Lines (Full Text) ===');
  
  const lineCount = db.exec("SELECT COUNT(*) FROM lines");
  const nLines = lineCount[0].values[0][0];
  test("Has lines", nLines > 2000, `count=${nLines}`);
  
  // Search for lines containing 'whale' via token join
  const whaleLines = db.exec(`
    SELECT l.canonical_id, l.text 
    FROM lines l JOIN tokens t ON l.line_id = t.segment_id 
    WHERE t.token = 'whale' 
    LIMIT 5
  `);
  const whaleLinesArr = whaleLines[0] ? whaleLines[0].values : [];
  test("Can find lines containing 'whale'", whaleLinesArr.length > 0, `got ${whaleLinesArr.length}`);
  
  if (whaleLinesArr.length > 0) {
    const firstLine = whaleLinesArr[0][1].toLowerCase();
    test("First whale line actually contains 'whale'", firstLine.includes('whale'), 
         `text: ${firstLine.substring(0, 80)}`);
  }

  // === Aggregation queries (what the UI does) ===
  console.log('\n=== Aggregation (UI-style queries) ===');
  
  // Per-work token count (like the "Works" granularity)
  const workAgg = db.exec(`
    SELECT w.title, SUM(t.count) as hits
    FROM works w JOIN segments s ON w.work_id = s.work_id
    JOIN tokens t ON s.segment_id = t.segment_id
    WHERE t.token = 'whale'
    GROUP BY w.work_id
    ORDER BY hits DESC
    LIMIT 5
  `);
  const topChapters = workAgg[0] ? workAgg[0].values : [];
  test("Can aggregate whale hits per chapter", topChapters.length > 0, `top: ${topChapters[0]}`);

  // === NFC normalization ===
  console.log('\n=== Unicode Normalization ===');
  
  // All tokens should be NFC and lowercase
  const nonLower = db.exec("SELECT token FROM tokens WHERE token != lower(token) LIMIT 5");
  const nonLowerTokens = nonLower[0] ? nonLower[0].values : [];
  test("All tokens are lowercase", nonLowerTokens.length === 0, 
       `non-lower: ${nonLowerTokens.map(r => r[0]).join(', ')}`);

  // === Performance ===
  console.log('\n=== Performance ===');
  
  const start = performance.now();
  for (let i = 0; i < 100; i++) {
    db.exec("SELECT segment_id, count FROM tokens WHERE token = 'whale'");
  }
  const elapsed = performance.now() - start;
  test(`100x exact lookup < 200ms`, elapsed < 200, `took ${elapsed.toFixed(1)}ms`);

  const start2 = performance.now();
  db.exec("SELECT DISTINCT token FROM tokens WHERE token LIKE 'wh%'");
  const elapsed2 = performance.now() - start2;
  test(`Prefix search < 50ms`, elapsed2 < 50, `took ${elapsed2.toFixed(1)}ms`);

  // === Summary ===
  db.close();
  
  console.log(`\n${'='.repeat(40)}`);
  console.log(`${passed} passed, ${failed} failed out of ${passed + failed} tests`);
  
  if (failed > 0) {
    process.exit(1);
  } else {
    console.log('All tests passed! ✅');
  }
}

main().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
