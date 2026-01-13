#!/usr/bin/env node
/**
 * Coda JSON-based Extraction Script
 *
 * Extracts content directly from Coda's internal JSON format.
 * Much faster and more complete than vision-based extraction.
 *
 * Run: node scripts/coda_json_extract.js
 */

const fs = require("fs").promises;
const path = require("path");

const CONFIG = {
  CRITICAL_FILE: "data/coda_raw/fui-critical.json",
  ALLCANVAS_FILE: "data/coda_raw/fui-allcanvas.json",
  OUTPUT_DIR: "data/coda_raw/pages_json",
  MANIFEST_FILE: "data/coda_raw/json_extraction_manifest.json",
  LOG_FILE: "data/coda_raw/json_extraction.log",
};

let logStream = null;

function log(msg) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${msg}`;
  console.log(line);
  if (logStream) {
    logStream.write(line + "\n");
  }
}

// Extract text content from Coda's internal object format
function extractTextFromObject(obj, depth = 0) {
  if (!obj || depth > 20) return "";

  let text = "";

  // Handle different object structures
  if (typeof obj === "string") {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => extractTextFromObject(item, depth + 1)).join("");
  }

  // Coda uses "text" property for text content
  if (obj.text !== undefined && obj.text !== "") {
    text += obj.text;
  }

  // Children array (main content structure in Coda)
  if (obj.children && Array.isArray(obj.children)) {
    text += obj.children
      .map((child) => extractTextFromObject(child, depth + 1))
      .join("");
  }

  // Add line break for line/paragraph types
  if (obj.type === "Line") {
    text += "\n";
  }

  // Handle headings with markdown
  if (obj.style && text.trim()) {
    if (obj.style === "H1") text = "# " + text;
    else if (obj.style === "H2") text = "## " + text;
    else if (obj.style === "H3") text = "### " + text;
  }

  // Handle bullet/numbered lists
  if (obj.lineLevel && obj.lineLevel > 0 && text.trim()) {
    const indent = "  ".repeat(obj.lineLevel - 1);
    text = indent + "- " + text;
  }

  // Handle embedded links/values
  if (obj.type === "InlineStructuredValue" && obj.value) {
    if (obj.value.url) {
      const linkText = obj.value.name || "Link";
      text += `[${linkText}](${obj.value.url})`;
    }
  }

  return text;
}

// Extract structured content from a canvas
function extractCanvasContent(canvasData) {
  const content = { text: "" };

  if (!canvasData) return content;

  const data = canvasData.data || {};

  // Coda stores content in data.children array
  if (data.children && Array.isArray(data.children)) {
    content.text = extractTextFromObject(data);
  }

  return content;
}

async function main() {
  const startTime = Date.now();

  // Setup
  await fs.mkdir(CONFIG.OUTPUT_DIR, { recursive: true });
  const logFileHandle = await fs.open(CONFIG.LOG_FILE, "a");
  logStream = logFileHandle.createWriteStream();

  log("=".repeat(60));
  log("CODA JSON EXTRACTION - Starting");
  log("=".repeat(60));

  // Load data files
  log("\nLoading JSON data files...");

  let critical, allcanvas;
  try {
    const criticalRaw = await fs.readFile(CONFIG.CRITICAL_FILE, "utf8");
    critical = JSON.parse(criticalRaw);
    log(
      `  ✓ Loaded fui-critical.json (${(criticalRaw.length / 1024 / 1024).toFixed(1)}MB)`,
    );
  } catch (e) {
    log(`  ✗ Failed to load fui-critical.json: ${e.message}`);
    log("  Run coda_embed_probe.js first to capture the data.");
    return;
  }

  try {
    const allcanvasRaw = await fs.readFile(CONFIG.ALLCANVAS_FILE, "utf8");
    allcanvas = JSON.parse(allcanvasRaw);
    log(
      `  ✓ Loaded fui-allcanvas.json (${(allcanvasRaw.length / 1024 / 1024).toFixed(1)}MB)`,
    );
  } catch (e) {
    log(`  ⚠ Failed to load fui-allcanvas.json: ${e.message}`);
    allcanvas = { objects: {} };
  }

  // Merge objects from both files
  const allObjects = {
    ...critical.objects,
    ...allcanvas.objects,
  };

  // Find all canvas pages
  const canvases = Object.entries(allObjects)
    .filter(([key, val]) => val?.schema?.type === "canvas")
    .map(([key, val]) => ({
      id: key,
      name: val?.schema?.name || "Untitled",
      schema: val?.schema,
      data: val?.data,
    }));

  log(`\nFound ${canvases.length} canvas pages to extract`);

  // Extract each canvas
  const results = [];
  let successCount = 0;
  let emptyCount = 0;

  for (let i = 0; i < canvases.length; i++) {
    const canvas = canvases[i];
    const progress = `[${i + 1}/${canvases.length}]`;

    // Extract content
    const content = extractCanvasContent({
      schema: canvas.schema,
      data: canvas.data,
    });

    // Clean up text
    const cleanText = content.text
      .replace(/\n{3,}/g, "\n\n")
      .replace(/\t+/g, "\t")
      .trim();

    if (cleanText.length > 10) {
      // Save as markdown
      const safeName = canvas.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .substring(0, 50);

      const filename = `${safeName}_${canvas.id.replace("canvas-", "")}.md`;
      const filepath = path.join(CONFIG.OUTPUT_DIR, filename);

      const mdContent = `# ${canvas.name}

**Canvas ID**: ${canvas.id}
**Extracted**: ${new Date().toISOString()}

---

${cleanText}
`;

      await fs.writeFile(filepath, mdContent);

      results.push({
        id: canvas.id,
        name: canvas.name,
        file: filename,
        size: cleanText.length,
      });

      successCount++;

      if (i % 100 === 0) {
        log(
          `${progress} Extracted: ${canvas.name.substring(0, 40)}... (${cleanText.length} chars)`,
        );
      }
    } else {
      emptyCount++;
    }
  }

  // Save manifest
  const manifest = {
    extraction: {
      timestamp: new Date().toISOString(),
      method: "json-direct",
      source_files: [CONFIG.CRITICAL_FILE, CONFIG.ALLCANVAS_FILE],
    },
    stats: {
      total_canvases: canvases.length,
      extracted: successCount,
      empty: emptyCount,
    },
    pages: results,
  };

  await fs.writeFile(CONFIG.MANIFEST_FILE, JSON.stringify(manifest, null, 2));

  // Summary
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  log("\n" + "=".repeat(60));
  log("EXTRACTION COMPLETE");
  log(`Total canvases: ${canvases.length}`);
  log(`Extracted: ${successCount}`);
  log(`Empty/skipped: ${emptyCount}`);
  log(
    `Total content: ${(results.reduce((s, p) => s + p.size, 0) / 1024).toFixed(1)}KB`,
  );
  log(`Time: ${elapsed} seconds`);
  log(`Output: ${CONFIG.OUTPUT_DIR}/`);
  log("=".repeat(60));

  logStream.end();
  await logFileHandle.close();
}

main().catch(console.error);
