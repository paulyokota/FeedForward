#!/usr/bin/env node
/**
 * Coda Storage Optimization Script
 *
 * Creates SQLite database with FTS5 for search/analysis
 * and compresses raw JSON files for archival.
 *
 * Run: node scripts/coda_storage_optimize.js
 */

const fs = require("fs").promises;
const path = require("path");
const zlib = require("zlib");
const { promisify } = require("util");

const gzip = promisify(zlib.gzip);

const CONFIG = {
  RAW_DIR: "data/coda_raw",
  PAGES_DIR: "data/coda_raw/pages_json",
  ARCHIVE_DIR: "data/coda_raw/archive",
  DB_FILE: "data/coda_raw/coda_content.db",
  MANIFEST_FILE: "data/coda_raw/json_extraction_manifest.json",
};

async function compressJsonFiles() {
  console.log("\n📦 Compressing raw JSON files...");

  await fs.mkdir(CONFIG.ARCHIVE_DIR, { recursive: true });

  const filesToCompress = ["fui-critical.json", "fui-allcanvas.json"];
  let totalOriginal = 0;
  let totalCompressed = 0;

  for (const filename of filesToCompress) {
    const srcPath = path.join(CONFIG.RAW_DIR, filename);
    const destPath = path.join(CONFIG.ARCHIVE_DIR, `${filename}.gz`);

    try {
      const content = await fs.readFile(srcPath);
      const compressed = await gzip(content, { level: 9 });

      await fs.writeFile(destPath, compressed);

      const originalSize = content.length;
      const compressedSize = compressed.length;
      const ratio = ((1 - compressedSize / originalSize) * 100).toFixed(1);

      totalOriginal += originalSize;
      totalCompressed += compressedSize;

      console.log(
        `  ✓ ${filename}: ${(originalSize / 1024 / 1024).toFixed(1)}MB → ${(compressedSize / 1024 / 1024).toFixed(1)}MB (${ratio}% reduction)`,
      );
    } catch (e) {
      console.log(`  ⚠ ${filename}: ${e.message}`);
    }
  }

  console.log(
    `  Total: ${(totalOriginal / 1024 / 1024).toFixed(1)}MB → ${(totalCompressed / 1024 / 1024).toFixed(1)}MB`,
  );

  return { totalOriginal, totalCompressed };
}

async function createSearchDatabase() {
  console.log("\n🗄️  Creating SQLite database with FTS5...");

  // Use better-sqlite3 if available, otherwise create SQL file for manual import
  let Database;
  try {
    Database = require("better-sqlite3");
  } catch (e) {
    console.log("  ⚠ better-sqlite3 not installed. Creating SQL file instead.");
    return await createSqlFile();
  }

  const db = new Database(CONFIG.DB_FILE);

  // Create tables
  db.exec(`
    -- Main pages table
    CREATE TABLE IF NOT EXISTS pages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      canvas_id TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL,
      file_path TEXT,
      char_count INTEGER,
      extracted_at TEXT
    );

    -- FTS5 virtual table for full-text search
    CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
      title,
      content,
      content='pages',
      content_rowid='id'
    );

    -- Triggers to keep FTS in sync
    CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
      INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
    END;

    CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
      INSERT INTO pages_fts(pages_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
    END;

    CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
      INSERT INTO pages_fts(pages_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
      INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
    END;
  `);

  // Load manifest
  let manifest;
  try {
    const manifestRaw = await fs.readFile(CONFIG.MANIFEST_FILE, "utf8");
    manifest = JSON.parse(manifestRaw);
  } catch (e) {
    console.log("  ✗ Could not load manifest file");
    return;
  }

  // Insert pages
  const insert = db.prepare(`
    INSERT OR REPLACE INTO pages (canvas_id, title, content, file_path, char_count, extracted_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `);

  const insertMany = db.transaction((pages) => {
    for (const page of pages) {
      insert.run(
        page.id,
        page.name,
        page.content,
        page.file,
        page.size,
        manifest.extraction.timestamp,
      );
    }
  });

  // Read content from markdown files
  const pagesWithContent = [];
  for (const page of manifest.pages) {
    try {
      const filePath = path.join(CONFIG.PAGES_DIR, page.file);
      const content = await fs.readFile(filePath, "utf8");

      // Extract just the content after the frontmatter
      const contentStart = content.indexOf("---\n", 4);
      const cleanContent =
        contentStart > 0 ? content.slice(contentStart + 4).trim() : content;

      pagesWithContent.push({
        ...page,
        content: cleanContent,
      });
    } catch (e) {
      // Skip files that can't be read
    }
  }

  insertMany(pagesWithContent);

  const count = db.prepare("SELECT COUNT(*) as count FROM pages").get();
  console.log(`  ✓ Indexed ${count.count} pages`);

  // Create metadata table
  db.exec(`
    CREATE TABLE IF NOT EXISTS metadata (
      key TEXT PRIMARY KEY,
      value TEXT
    );
  `);

  db.prepare("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)").run(
    "created_at",
    new Date().toISOString(),
  );
  db.prepare("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)").run(
    "source",
    "coda_json_extract",
  );
  db.prepare("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)").run(
    "page_count",
    String(count.count),
  );

  db.close();

  const dbStats = await fs.stat(CONFIG.DB_FILE);
  console.log(
    `  ✓ Database size: ${(dbStats.size / 1024 / 1024).toFixed(1)}MB`,
  );

  return { pageCount: count.count, dbSize: dbStats.size };
}

async function createSqlFile() {
  // Fallback: create SQL file that can be imported manually
  const sqlPath = path.join(CONFIG.RAW_DIR, "coda_content.sql");

  let sql = `-- Coda Content Database
-- Import with: sqlite3 coda_content.db < coda_content.sql

CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canvas_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  file_path TEXT,
  char_count INTEGER,
  extracted_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  title,
  content,
  content='pages',
  content_rowid='id'
);

`;

  // Load manifest
  let manifest;
  try {
    const manifestRaw = await fs.readFile(CONFIG.MANIFEST_FILE, "utf8");
    manifest = JSON.parse(manifestRaw);
  } catch (e) {
    console.log("  ✗ Could not load manifest file");
    return;
  }

  // Generate INSERT statements
  for (const page of manifest.pages) {
    try {
      const filePath = path.join(CONFIG.PAGES_DIR, page.file);
      const content = await fs.readFile(filePath, "utf8");

      const contentStart = content.indexOf("---\n", 4);
      const cleanContent =
        contentStart > 0 ? content.slice(contentStart + 4).trim() : content;

      // Escape single quotes
      const escapedTitle = page.name.replace(/'/g, "''");
      const escapedContent = cleanContent.replace(/'/g, "''");

      sql += `INSERT INTO pages (canvas_id, title, content, file_path, char_count, extracted_at) VALUES ('${page.id}', '${escapedTitle}', '${escapedContent}', '${page.file}', ${page.size}, '${manifest.extraction.timestamp}');\n`;
    } catch (e) {
      // Skip
    }
  }

  sql += `
-- Populate FTS index
INSERT INTO pages_fts(rowid, title, content) SELECT id, title, content FROM pages;
`;

  await fs.writeFile(sqlPath, sql);
  console.log(`  ✓ Created ${sqlPath}`);
  console.log(`  To import: sqlite3 ${CONFIG.DB_FILE} < ${sqlPath}`);

  return { sqlPath };
}

async function generateStats() {
  console.log("\n📊 Storage Summary...");

  const stats = {
    archive: { size: 0, files: 0 },
    pages: { size: 0, files: 0 },
    database: { size: 0 },
  };

  // Archive stats
  try {
    const archiveFiles = await fs.readdir(CONFIG.ARCHIVE_DIR);
    for (const file of archiveFiles) {
      const fileStat = await fs.stat(path.join(CONFIG.ARCHIVE_DIR, file));
      stats.archive.size += fileStat.size;
      stats.archive.files++;
    }
  } catch (e) {
    // Archive doesn't exist yet
  }

  // Pages stats
  try {
    const pageFiles = await fs.readdir(CONFIG.PAGES_DIR);
    for (const file of pageFiles) {
      if (file.endsWith(".md")) {
        const fileStat = await fs.stat(path.join(CONFIG.PAGES_DIR, file));
        stats.pages.size += fileStat.size;
        stats.pages.files++;
      }
    }
  } catch (e) {
    // Pages don't exist
  }

  // Database stats
  try {
    const dbStat = await fs.stat(CONFIG.DB_FILE);
    stats.database.size = dbStat.size;
  } catch (e) {
    // DB doesn't exist
  }

  console.log("\n  Storage breakdown:");
  console.log(
    `    Archive (compressed JSON): ${(stats.archive.size / 1024 / 1024).toFixed(1)}MB (${stats.archive.files} files)`,
  );
  console.log(
    `    Pages (markdown):          ${(stats.pages.size / 1024 / 1024).toFixed(1)}MB (${stats.pages.files} files)`,
  );
  console.log(
    `    Database (SQLite+FTS):     ${(stats.database.size / 1024 / 1024).toFixed(1)}MB`,
  );
  console.log(`    ─────────────────────────────────────`);
  console.log(
    `    Total optimized:           ${((stats.archive.size + stats.pages.size + stats.database.size) / 1024 / 1024).toFixed(1)}MB`,
  );

  return stats;
}

async function main() {
  console.log("=".repeat(60));
  console.log("CODA STORAGE OPTIMIZATION");
  console.log("=".repeat(60));

  await compressJsonFiles();
  await createSearchDatabase();
  await generateStats();

  console.log("\n" + "=".repeat(60));
  console.log("OPTIMIZATION COMPLETE");
  console.log("=".repeat(60));
  console.log("\nUsage:");
  console.log(
    "  Search: sqlite3 coda_content.db \"SELECT title FROM pages_fts WHERE pages_fts MATCH 'your query'\"",
  );
  console.log("  RAG: Use markdown files in pages_json/ for embedding");
  console.log(
    "  Archive: Compressed JSON in archive/ (decompress with gunzip if needed)",
  );
}

main().catch(console.error);
