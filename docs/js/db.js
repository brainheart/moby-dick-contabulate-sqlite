(function () {
  'use strict';

  const SQL_JS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.12.0/';
  const DB_PATH = 'data/contabulate.db';

  let initPromise = null;
  let db = null;
  let worksCache = null;
  let segmentsCache = null;

  function setLoadingState(message, isError) {
    const root = document.getElementById('dbLoading');
    if (!root) return;
    const textEl = document.getElementById('dbLoadingText') || root;
    textEl.textContent = message || '';
    root.classList.toggle('is-hidden', !message);
    root.classList.toggle('warning', !!isError);
  }

  function requireDb() {
    if (!db) throw new Error('Database is not initialized');
    return db;
  }

  function tableNameForN(n) {
    if (n === 2) return { table: 'bigrams', key: 'bigram' };
    if (n === 3) return { table: 'trigrams', key: 'trigram' };
    return { table: 'tokens', key: 'token' };
  }

  function rowsFromStatement(sql, params) {
    const database = requireDb();
    const stmt = database.prepare(sql);
    try {
      stmt.bind(params || []);
      const rows = [];
      while (stmt.step()) rows.push(stmt.getAsObject());
      return rows;
    } finally {
      stmt.free();
    }
  }

  function createRegexpFunction(database) {
    const cache = new Map();
    database.create_function('REGEXP', function (pattern, value) {
      const source = String(pattern == null ? '' : pattern);
      const input = String(value == null ? '' : value);
      let re = cache.get(source);
      if (!re) {
        re = new RegExp(source, 'i');
        cache.set(source, re);
      }
      return re.test(input) ? 1 : 0;
    });
  }

  async function init() {
    if (initPromise) return initPromise;
    initPromise = (async () => {
      setLoadingState('Loading database...');
      if (typeof initSqlJs !== 'function') {
        throw new Error('sql.js failed to load');
      }
      const SQL = await initSqlJs({
        locateFile: (file) => SQL_JS_CDN + file
      });
      const response = await fetch(DB_PATH);
      if (!response.ok) {
        throw new Error(`Failed to load ${DB_PATH}: ${response.status}`);
      }
      const bytes = new Uint8Array(await response.arrayBuffer());
      db = new SQL.Database(bytes);
      createRegexpFunction(db);
      setLoadingState('');
      return api;
    })().catch((error) => {
      console.error(error);
      setLoadingState(`Failed to load search database: ${error.message}`, true);
      throw error;
    });
    return initPromise;
  }

  async function getWorks() {
    await init();
    if (worksCache) return worksCache;
    worksCache = rowsFromStatement(
      `SELECT
         work_id AS play_id,
         location,
         title,
         abbr,
         genre,
         year AS first_performance_year,
         num_sections AS num_acts,
         num_segments AS num_scenes,
         0 AS num_speeches,
         total_words,
         total_lines
       FROM works
       ORDER BY work_id`
    );
    return worksCache;
  }

  async function getSegments() {
    await init();
    if (segmentsCache) return segmentsCache;
    segmentsCache = rowsFromStatement(
      `SELECT
         segment_id AS scene_id,
         canonical_id,
         location,
         work_id AS play_id,
         work_title AS play_title,
         work_abbr AS play_abbr,
         genre,
         section AS act,
         position AS scene,
         heading,
         total_words,
         unique_words,
         0 AS num_speeches,
         1 AS num_lines,
         0 AS characters_present_count,
         section_label AS act_label,
         position_label AS scene_label
       FROM segments
       ORDER BY segment_id`
    );
    return segmentsCache;
  }

  async function getLinesByIds(ids) {
    await init();
    if (!Array.isArray(ids) || ids.length === 0) return [];

    const uniqueIds = Array.from(new Set(ids.map((id) => Number(id)).filter(Number.isInteger)));
    if (!uniqueIds.length) return [];

    const out = [];
    for (let i = 0; i < uniqueIds.length; i += 500) {
      const batch = uniqueIds.slice(i, i + 500);
      const placeholders = batch.map(() => '?').join(', ');
      const rows = rowsFromStatement(
        `SELECT
           line_id,
           work_id AS play_id,
           canonical_id,
           location,
           section AS act,
           section_label AS act_label,
           position AS scene,
           printf('¶%d', position) AS scene_label,
           line_num,
           speaker,
           text
         FROM lines
         WHERE line_id IN (${placeholders})
         ORDER BY location`,
        batch
      );
      out.push(...rows);
    }
    return out;
  }

  async function getLines() {
    await init();
    return rowsFromStatement(
      `SELECT
         line_id,
         work_id AS play_id,
         canonical_id,
         location,
         section AS act,
         section_label AS act_label,
         position AS scene,
         printf('¶%d', position) AS scene_label,
         line_num,
         speaker,
         text
       FROM lines
       ORDER BY location`
    );
  }

  async function getTokenPostings(term, n) {
    await init();
    const normalized = window.normalizeTerm ? window.normalizeTerm(term) : String(term || '').trim().toLowerCase();
    if (!normalized) return [];
    const { table, key } = tableNameForN(n);
    const rows = rowsFromStatement(
      `SELECT segment_id, count
       FROM ${table}
       WHERE ${key} = ?
       ORDER BY segment_id`,
      [normalized]
    );
    return rows.map((row) => [Number(row.segment_id), Number(row.count)]);
  }

  async function searchTokensRegex(pattern, n) {
    await init();
    const source = String(pattern || '').trim();
    if (!source) return [];
    const { table, key } = tableNameForN(n);
    const rows = rowsFromStatement(
      `SELECT segment_id, SUM(count) AS count
       FROM ${table}
       WHERE ${key} REGEXP ?
       GROUP BY segment_id
       ORDER BY segment_id`,
      [source]
    );
    return rows.map((row) => [Number(row.segment_id), Number(row.count)]);
  }

  async function getWorkNgramStats(workId, n) {
    await init();
    const { table, key } = tableNameForN(n);
    const rows = rowsFromStatement(
      `SELECT
         idx.${key} AS ngram,
         SUM(CASE WHEN s.work_id = ? THEN idx.count ELSE 0 END) AS tf,
         COUNT(DISTINCT s.work_id) AS df
       FROM ${table} idx
       JOIN segments s ON s.segment_id = idx.segment_id
       GROUP BY idx.${key}
       HAVING tf > 0`,
      [workId]
    );
    return rows.map((row) => ({
      ngram: row.ngram,
      count: Number(row.tf),
      df: Number(row.df)
    }));
  }

  const api = {
    init,
    getWorks,
    getSegments,
    getLines,
    getLinesByIds,
    getTokenPostings,
    searchTokensRegex,
    getWorkNgramStats
  };

  window.contabulateDb = api;
})();
