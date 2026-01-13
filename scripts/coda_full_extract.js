#!/usr/bin/env node
/**
 * Coda Full Document Extraction Script
 *
 * Run independently: node scripts/coda_full_extract.js
 *
 * Features:
 * - Discovers all pages recursively from navigation
 * - Extracts content from each page with scrolling for lazy-load
 * - Saves to data/coda_raw/pages/ with manifest
 * - Resumable - skips already-extracted pages
 * - Progress logging to console and file
 */

const { chromium } = require("playwright");
const fs = require("fs").promises;
const path = require("path");

// ============ CONFIGURATION ============
const CONFIG = {
  CODA_URL: "https://coda.io/d/Tailwind-Research-Ops_dc4RRJ_VLtW",
  CODA_DOC_ID: "c4RRJ_VLtW",
  OUTPUT_DIR: "data/coda_raw/pages",
  MANIFEST_FILE: "data/coda_raw/extraction_manifest.json",
  LOG_FILE: "data/coda_raw/extraction.log",
  USER_DATA_DIR: ".playwright-profile",

  // Timing
  LOGIN_TIMEOUT_MS: 180000, // 3 minutes for login
  PAGE_TIMEOUT_MS: 45000, // 45s per page navigation
  CONTENT_SETTLE_MS: 2000, // Wait for content to load

  // Viewport (larger = more content visible)
  VIEWPORT: { width: 1920, height: 1080 },

  // Content threshold
  MIN_CONTENT_LENGTH: 50,
};

// ============ LOGGING ============
let logStream = null;

function log(msg) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${msg}`;
  console.log(line);
  if (logStream) {
    logStream.write(line + "\n");
  }
}

// ============ MAIN EXTRACTION ============
async function main() {
  const startTime = Date.now();

  // Setup
  await fs.mkdir(CONFIG.OUTPUT_DIR, { recursive: true });
  await fs.mkdir(path.dirname(CONFIG.LOG_FILE), { recursive: true });
  const logFileHandle = await fs.open(CONFIG.LOG_FILE, "a");
  logStream = logFileHandle.createWriteStream();

  log("=".repeat(60));
  log("CODA FULL EXTRACTION - STARTING");
  log(`Document: ${CONFIG.CODA_URL}`);
  log(`Output: ${CONFIG.OUTPUT_DIR}/`);
  log("=".repeat(60));

  // Load existing manifest to resume
  let manifest = await loadManifest();
  const extractedUrls = new Set(manifest.pages?.map((p) => p.url) || []);
  log(`Resuming: ${extractedUrls.size} pages already extracted`);

  // Launch browser
  log("Launching browser...");
  const context = await chromium.launchPersistentContext(
    path.join(process.cwd(), CONFIG.USER_DATA_DIR),
    { headless: false, viewport: CONFIG.VIEWPORT },
  );
  const page = context.pages()[0] || (await context.newPage());

  try {
    // Navigate and wait for login
    log("Navigating to Coda...");
    await page.goto(CONFIG.CODA_URL, {
      waitUntil: "networkidle",
      timeout: 60000,
    });
    await waitForLogin(page);

    // Discover all pages
    log("\nDISCOVERING PAGES...");
    const allPages = await discoverAllPages(page, extractedUrls);
    log(`Found ${allPages.length} new pages to extract`);

    // Extract each page
    const results = [...(manifest.pages || [])];
    let successCount = 0;
    let skipCount = 0;
    let errorCount = 0;

    for (let i = 0; i < allPages.length; i++) {
      const pageInfo = allPages[i];
      const progress = `[${i + 1}/${allPages.length}]`;

      // Skip if already extracted
      if (extractedUrls.has(pageInfo.url)) {
        skipCount++;
        continue;
      }

      log(`\n${progress} Extracting: ${pageInfo.title.substring(0, 50)}...`);

      try {
        // Navigate
        await page.goto(pageInfo.url, {
          waitUntil: "networkidle",
          timeout: CONFIG.PAGE_TIMEOUT_MS,
        });

        // Scroll to load lazy content
        await scrollPage(page);
        await page.waitForTimeout(CONFIG.CONTENT_SETTLE_MS);

        // Extract content
        const content = await extractPageContent(page, pageInfo);

        // Discover new links from this page
        const newLinks = await discoverLinksOnPage(page, extractedUrls);
        if (newLinks.length > 0) {
          log(`  📎 Found ${newLinks.length} new subpage links`);
          for (const nl of newLinks) {
            if (!extractedUrls.has(nl.url)) {
              extractedUrls.add(nl.url);
              allPages.push(nl);
            }
          }
        }

        // Save if has content
        if (content.markdown.length >= CONFIG.MIN_CONTENT_LENGTH) {
          const saved = await savePageContent(content, pageInfo);
          results.push({
            ...pageInfo,
            ...saved,
            sections: content.stats.totalSections,
            size: content.markdown.length,
          });
          extractedUrls.add(pageInfo.url);
          successCount++;
          log(
            `  ✓ Saved: ${content.stats.totalSections} sections, ${(content.markdown.length / 1024).toFixed(1)}KB`,
          );
        } else {
          log(
            `  ⚠ Skipped: minimal content (${content.markdown.length} chars)`,
          );
          skipCount++;
        }

        // Save manifest periodically
        if (successCount % 10 === 0) {
          await saveManifest(results, allPages.length);
        }
      } catch (err) {
        errorCount++;
        log(`  ✗ Error: ${err.message}`);
      }
    }

    // Final manifest save
    await saveManifest(results, results.length + skipCount + errorCount);

    // Summary
    const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
    log("\n" + "=".repeat(60));
    log("EXTRACTION COMPLETE");
    log(`Pages extracted: ${results.length}`);
    log(`Skipped: ${skipCount}`);
    log(`Errors: ${errorCount}`);
    log(
      `Total size: ${(results.reduce((s, p) => s + (p.size || 0), 0) / 1024).toFixed(1)}KB`,
    );
    log(`Time: ${elapsed} minutes`);
    log(`Output: ${CONFIG.OUTPUT_DIR}/`);
    log(`Manifest: ${CONFIG.MANIFEST_FILE}`);
    log("=".repeat(60));
  } finally {
    await context.close();
    logStream.end();
    await logFileHandle.close();
  }
}

// ============ HELPERS ============

async function loadManifest() {
  try {
    const data = await fs.readFile(CONFIG.MANIFEST_FILE, "utf8");
    return JSON.parse(data);
  } catch {
    return { extraction: {}, content: {}, pages: [] };
  }
}

async function saveManifest(pages, totalDiscovered) {
  const manifest = {
    extraction: {
      timestamp: new Date().toISOString(),
      doc_id: CONFIG.CODA_DOC_ID,
      doc_url: CONFIG.CODA_URL,
      doc_name: "Tailwind Research Ops",
      methods: ["playwright"],
    },
    content: {
      pages: {
        total: totalDiscovered,
        extracted: pages.length,
        with_content: pages.filter((p) => p.sections > 0).length,
      },
    },
    pages,
  };
  await fs.writeFile(CONFIG.MANIFEST_FILE, JSON.stringify(manifest, null, 2));
}

async function waitForLogin(page) {
  const maxWait = CONFIG.LOGIN_TIMEOUT_MS;
  const checkInterval = 2000;
  let elapsed = 0;
  let prompted = false;

  while (elapsed < maxWait) {
    try {
      const url = page.url();

      if (url.includes("accounts.google.com")) {
        if (!prompted) {
          log("\n⏳ Google auth in progress - complete login in browser...");
          prompted = true;
        }
        await page.waitForTimeout(checkInterval);
        elapsed += checkInterval;
        continue;
      }

      const content = await page.content();
      const isLoginPage =
        url.includes("login") ||
        url.includes("signin") ||
        content.includes("Sign in with Google");

      if (!isLoginPage) {
        const hasContent =
          content.includes("canvas") || content.length > 100000;
        if (hasContent) {
          log("✓ Login successful - document loaded");
          return true;
        }
      }

      if (!prompted && elapsed === 0) {
        log("\n⏳ Waiting for login (3 min max)...");
        log("   Complete login in the browser window.");
        prompted = true;
      }
    } catch (e) {
      // Page navigating
    }

    await page.waitForTimeout(checkInterval);
    elapsed += checkInterval;
  }

  log("⚠ Login timeout - proceeding anyway");
  return false;
}

async function scrollPage(page) {
  await page.evaluate(async () => {
    const delay = (ms) => new Promise((r) => setTimeout(r, ms));
    const height = document.body.scrollHeight;
    const step = window.innerHeight * 0.8;
    let pos = 0;

    while (pos < height) {
      window.scrollTo(0, pos);
      await delay(150);
      pos += step;
    }
    window.scrollTo(0, 0);
  });
}

async function discoverAllPages(page, seenUrls) {
  log("  Expanding navigation...");

  // Expand collapsed sections
  for (let round = 0; round < 3; round++) {
    const expandSelectors = [
      '[aria-expanded="false"]',
      '[class*="collapsed"]',
      '[class*="expand"]',
    ];
    for (const sel of expandSelectors) {
      const buttons = await page.$$(sel);
      for (const btn of buttons.slice(0, 50)) {
        try {
          if (await btn.isVisible()) {
            await btn.click();
            await page.waitForTimeout(100);
          }
        } catch {}
      }
    }
  }

  log("  Scanning for page links...");
  const links = await page.evaluate((docId) => {
    const results = [];
    const seen = new Set();

    document.querySelectorAll("a[href]").forEach((link) => {
      const href = link.href;
      const text = link.textContent.trim();

      if (
        href &&
        href.includes("coda.io") &&
        href.includes(docId) &&
        !href.includes("/signin") &&
        !href.includes("/login") &&
        text &&
        text.length > 0 &&
        text.length < 150 &&
        !seen.has(href)
      ) {
        seen.add(href);
        results.push({
          title: text.replace(/\s+/g, " ").substring(0, 100),
          url: href,
          depth: 0,
        });
      }
    });
    return results;
  }, CONFIG.CODA_DOC_ID);

  // Add main page if not present
  if (!links.some((l) => l.url === CONFIG.CODA_URL)) {
    links.unshift({ title: "Main Page", url: CONFIG.CODA_URL, depth: 0 });
  }

  // Filter out already-seen URLs
  return links.filter((l) => !seenUrls.has(l.url));
}

async function discoverLinksOnPage(page, seenUrls) {
  const links = await page.evaluate((docId) => {
    const results = [];
    document.querySelectorAll("a[href]").forEach((link) => {
      const href = link.href;
      const text = link.textContent.trim();
      if (
        href &&
        href.includes("coda.io") &&
        href.includes(docId) &&
        !href.includes("/signin") &&
        text &&
        text.length > 0 &&
        text.length < 150
      ) {
        results.push({
          title: text.replace(/\s+/g, " ").substring(0, 100),
          url: href,
          depth: 0,
        });
      }
    });
    return results;
  }, CONFIG.CODA_DOC_ID);

  return links.filter((l) => !seenUrls.has(l.url));
}

async function extractPageContent(page, pageInfo) {
  return await page.evaluate(
    (info) => {
      const sections = [];
      let markdown = "";
      const cleanText = (t) => t.replace(/\s+/g, " ").trim();

      // Find content area
      let content = null;
      for (const sel of [
        '[data-coda-ui-id="canvas"]',
        '[class*="canvas"]',
        "main",
        "article",
      ]) {
        const el = document.querySelector(sel);
        if (el && el.innerText?.length > 50) {
          content = el;
          break;
        }
      }
      if (!content) content = document.body;

      // Get title
      const titleEl = document.querySelector('h1, [class*="pageTitle"]');
      const title = titleEl
        ? cleanText(titleEl.innerText)
        : info.title || "Untitled";
      markdown += `# ${title}\n\n`;
      sections.push({ type: "title", text: title });

      // Walk elements
      const walker = document.createTreeWalker(
        content,
        NodeFilter.SHOW_ELEMENT,
        {
          acceptNode: (n) => {
            const tag = n.tagName.toLowerCase();
            if (
              ["script", "style", "nav", "noscript", "svg", "button"].includes(
                tag,
              )
            )
              return NodeFilter.FILTER_REJECT;
            const style = getComputedStyle(n);
            if (style.display === "none" || style.visibility === "hidden")
              return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
          },
        },
      );

      const seen = new Set();
      let node,
        lastList = false;

      while ((node = walker.nextNode())) {
        const tag = node.tagName.toLowerCase();
        const direct = Array.from(node.childNodes)
          .filter((n) => n.nodeType === 3)
          .map((n) => n.textContent)
          .join("")
          .trim();
        let text = cleanText(direct || node.innerText || "");

        if (!text || text.length < 3 || seen.has(text)) continue;
        if (
          /^(Sign in|Log in|Share|Comments?|View|Edit|Home|Menu|Search)$/i.test(
            text,
          )
        )
          continue;
        if (text === title && sections.length > 1) continue;
        seen.add(text);

        if (/^h[1-6]$/.test(tag)) {
          markdown += `\n${"#".repeat(+tag[1])} ${text}\n\n`;
          sections.push({ type: "heading", text });
          lastList = false;
        } else if (tag === "li") {
          markdown += `- ${text}\n`;
          sections.push({ type: "list-item", text });
          lastList = true;
        } else if (tag === "pre" || tag === "code") {
          if (text.length > 10) {
            markdown += `\n\`\`\`\n${text}\n\`\`\`\n\n`;
            sections.push({ type: "code", text });
          }
          lastList = false;
        } else if (tag === "blockquote") {
          markdown += `\n> ${text}\n\n`;
          sections.push({ type: "quote", text });
          lastList = false;
        } else if (
          (tag === "p" || tag === "div" || tag === "span") &&
          text.length > 20 &&
          direct.length > 10
        ) {
          if (lastList) markdown += "\n";
          markdown += `${text}\n\n`;
          sections.push({ type: "paragraph", text });
          lastList = false;
        }
      }

      return {
        markdown,
        sections,
        pageTitle: title,
        stats: {
          totalSections: sections.length,
          headings: sections.filter((s) => s.type === "heading").length,
          paragraphs: sections.filter((s) => s.type === "paragraph").length,
          listItems: sections.filter((s) => s.type === "list-item").length,
        },
      };
    },
    { title: pageInfo.title },
  );
}

async function savePageContent(content, pageInfo) {
  const timestamp = new Date().toISOString();
  const pageId =
    content.pageTitle
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .substring(0, 50) || "page";

  // Ensure unique filename
  let filename = `page_${pageId}`;
  let counter = 1;
  while (
    await fs
      .access(path.join(CONFIG.OUTPUT_DIR, `${filename}.md`))
      .then(() => true)
      .catch(() => false)
  ) {
    filename = `page_${pageId}_${counter++}`;
  }

  const mdFile = path.join(CONFIG.OUTPUT_DIR, `${filename}.md`);
  const metaFile = path.join(CONFIG.OUTPUT_DIR, `${filename}.meta.json`);

  const mdContent = `# Coda Extraction: ${content.pageTitle}

**Source**: ${pageInfo.url}
**Extracted**: ${timestamp}
**Method**: Playwright standalone script
**Sections**: ${content.stats.totalSections}

---

${content.markdown}
`;

  const metadata = {
    source: {
      doc_id: CONFIG.CODA_DOC_ID,
      page_url: pageInfo.url,
      page_title: content.pageTitle,
    },
    extraction: { timestamp, stats: content.stats },
    output: { markdown_file: mdFile, size_bytes: Buffer.byteLength(mdContent) },
  };

  await fs.writeFile(mdFile, mdContent);
  await fs.writeFile(metaFile, JSON.stringify(metadata, null, 2));

  return { mdFile, metaFile };
}

// ============ RUN ============
main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
