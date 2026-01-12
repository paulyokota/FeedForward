#!/usr/bin/env node
/**
 * Coda Vision-Based Extraction Script
 *
 * Uses screenshots + GPT-4o Vision to extract content from Coda pages
 * that render content in canvas/virtualized DOM.
 *
 * Run: node scripts/coda_vision_extract.js
 */

const { chromium } = require("playwright");
const fs = require("fs").promises;
const path = require("path");

// ============ CONFIGURATION ============
const CONFIG = {
  CODA_URL: "https://coda.io/d/Tailwind-Research-Ops_dc4RRJ_VLtW",
  CODA_DOC_ID: "c4RRJ_VLtW",
  OUTPUT_DIR: "data/coda_raw/pages",
  SCREENSHOTS_DIR: "data/coda_raw/screenshots",
  MANIFEST_FILE: "data/coda_raw/extraction_manifest.json",
  LOG_FILE: "data/coda_raw/extraction.log",
  COST_FILE: "data/coda_raw/extraction_costs.json",
  USER_DATA_DIR: ".playwright-profile",

  // Timing
  LOGIN_TIMEOUT_MS: 180000,
  PAGE_TIMEOUT_MS: 45000,
  CONTENT_SETTLE_MS: 3000, // Longer wait for canvas to render

  // Viewport
  VIEWPORT: { width: 1920, height: 1080 },

  // OpenAI
  OPENAI_MODEL: "gpt-4o",

  // Cost tracking (per 1M tokens)
  COSTS: {
    INPUT_PER_1M: 2.5,
    OUTPUT_PER_1M: 10.0,
    IMAGE_TOKENS_HIGH: 1500, // ~tokens per 1920x1080 image
  },
};

// ============ COST TRACKING ============
let totalCost = {
  inputTokens: 0,
  outputTokens: 0,
  imageCount: 0,
  usdTotal: 0,
};

function updateCost(inputTokens, outputTokens, imageCount = 1) {
  totalCost.inputTokens += inputTokens;
  totalCost.outputTokens += outputTokens;
  totalCost.imageCount += imageCount;

  const inputCost = (inputTokens / 1_000_000) * CONFIG.COSTS.INPUT_PER_1M;
  const outputCost = (outputTokens / 1_000_000) * CONFIG.COSTS.OUTPUT_PER_1M;
  totalCost.usdTotal += inputCost + outputCost;

  return { inputCost, outputCost, total: inputCost + outputCost };
}

async function saveCosts() {
  const costData = {
    ...totalCost,
    timestamp: new Date().toISOString(),
    model: CONFIG.OPENAI_MODEL,
  };
  await fs.writeFile(CONFIG.COST_FILE, JSON.stringify(costData, null, 2));
}

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

// ============ OPENAI VISION ============
async function extractWithVision(screenshotPath, pageTitle) {
  const OpenAI = (await import("openai")).default;
  const openai = new OpenAI();

  // Read screenshot as base64
  const imageBuffer = await fs.readFile(screenshotPath);
  const base64Image = imageBuffer.toString("base64");

  const prompt = `Extract all text content from this Coda document page screenshot.
Format the output as clean markdown with:
- Headings (use # ## ### as appropriate)
- Bullet points for lists
- Preserve any tables as markdown tables
- Include all visible text content

Page title: ${pageTitle}

Return ONLY the extracted markdown content, no explanations.`;

  try {
    const response = await openai.chat.completions.create({
      model: CONFIG.OPENAI_MODEL,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: prompt },
            {
              type: "image_url",
              image_url: {
                url: `data:image/png;base64,${base64Image}`,
                detail: "high",
              },
            },
          ],
        },
      ],
      max_tokens: 4000,
    });

    const usage = response.usage || {};
    const inputTokens =
      usage.prompt_tokens || CONFIG.COSTS.IMAGE_TOKENS_HIGH + 100;
    const outputTokens = usage.completion_tokens || 500;

    const cost = updateCost(inputTokens, outputTokens);
    log(
      `  💰 Cost: $${cost.total.toFixed(4)} (in: ${inputTokens}, out: ${outputTokens})`,
    );

    return {
      content: response.choices[0].message.content,
      tokens: { input: inputTokens, output: outputTokens },
      cost: cost.total,
    };
  } catch (err) {
    log(`  ✗ Vision API error: ${err.message}`);
    throw err;
  }
}

// ============ MAIN EXTRACTION ============
async function main() {
  const startTime = Date.now();

  // Setup directories
  await fs.mkdir(CONFIG.OUTPUT_DIR, { recursive: true });
  await fs.mkdir(CONFIG.SCREENSHOTS_DIR, { recursive: true });
  await fs.mkdir(path.dirname(CONFIG.LOG_FILE), { recursive: true });

  const logFileHandle = await fs.open(CONFIG.LOG_FILE, "a");
  logStream = logFileHandle.createWriteStream();

  log("=".repeat(60));
  log("CODA VISION EXTRACTION - STARTING");
  log(`Document: ${CONFIG.CODA_URL}`);
  log(`Output: ${CONFIG.OUTPUT_DIR}/`);
  log(`Model: ${CONFIG.OPENAI_MODEL}`);
  log("=".repeat(60));

  // Load existing manifest
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
    // Navigate and login
    log("Navigating to Coda...");
    await page.goto(CONFIG.CODA_URL, {
      waitUntil: "networkidle",
      timeout: 60000,
    });
    await waitForLogin(page);

    // Discover pages
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

      if (extractedUrls.has(pageInfo.url)) {
        skipCount++;
        continue;
      }

      log(`\n${progress} Extracting: ${pageInfo.title.substring(0, 50)}...`);

      try {
        // Navigate to page
        await page.goto(pageInfo.url, {
          waitUntil: "networkidle",
          timeout: CONFIG.PAGE_TIMEOUT_MS,
        });

        // Wait for content to render
        await page.waitForTimeout(CONFIG.CONTENT_SETTLE_MS);

        // Scroll to load lazy content (this also helps render content)
        await scrollPage(page);
        await page.waitForTimeout(1000);

        // Expand any collapsed content sections
        await expandAllSections(page);

        // Scroll again after expanding to ensure all content is loaded
        await scrollPage(page);
        await page.waitForTimeout(500);

        // Close any open menus before screenshot
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);

        // Take screenshot
        const screenshotName = `page_${i + 1}_${Date.now()}.png`;
        const screenshotPath = path.join(
          CONFIG.SCREENSHOTS_DIR,
          screenshotName,
        );
        await page.screenshot({ path: screenshotPath, fullPage: true });
        log(`  📸 Screenshot saved: ${screenshotName}`);

        // Extract with vision
        const extraction = await extractWithVision(
          screenshotPath,
          pageInfo.title,
        );

        if (extraction.content && extraction.content.length > 50) {
          // Save markdown
          const saved = await savePageContent(extraction.content, pageInfo);
          results.push({
            ...pageInfo,
            ...saved,
            screenshot: screenshotPath,
            size: extraction.content.length,
            cost: extraction.cost,
          });
          extractedUrls.add(pageInfo.url);
          successCount++;
          log(`  ✓ Saved: ${(extraction.content.length / 1024).toFixed(1)}KB`);
        } else {
          log(`  ⚠ Skipped: minimal content extracted`);
          skipCount++;
        }

        // Discover new links (don't add to extractedUrls yet - only when actually extracted)
        const newLinks = await discoverLinksOnPage(page, extractedUrls);
        if (newLinks.length > 0) {
          log(`  📎 Found ${newLinks.length} new subpage links`);
          for (const nl of newLinks) {
            // Only add to allPages if not already queued or extracted
            const alreadyQueued = allPages.some((p) => p.url === nl.url);
            if (!extractedUrls.has(nl.url) && !alreadyQueued) {
              allPages.push(nl);
            }
          }
        }

        // Save progress
        if (successCount % 5 === 0) {
          await saveManifest(results, allPages.length);
          await saveCosts();
        }
      } catch (err) {
        errorCount++;
        log(`  ✗ Error: ${err.message}`);
      }
    }

    // Final saves
    await saveManifest(results, results.length + skipCount + errorCount);
    await saveCosts();

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
    log(`💰 TOTAL COST: $${totalCost.usdTotal.toFixed(4)}`);
    log(`   Input tokens: ${totalCost.inputTokens}`);
    log(`   Output tokens: ${totalCost.outputTokens}`);
    log(`   Images processed: ${totalCost.imageCount}`);
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
      methods: ["playwright", "gpt-4o-vision"],
    },
    content: {
      pages: {
        total: totalDiscovered,
        extracted: pages.length,
        with_content: pages.filter((p) => p.size > 0).length,
      },
    },
    costs: { ...totalCost },
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
      await delay(200);
      pos += step;
    }
    window.scrollTo(0, 0);
  });
}

async function expandAllSections(page) {
  // Close any open menus first
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);

  let expandedCount = 0;
  const maxRounds = 15; // Allow many rounds for deeply nested content

  for (let round = 0; round < maxRounds; round++) {
    // Use Playwright's accessibility-based locator to find buttons
    // with EXACT name "Expand content" - this targets only collapsed
    // content sections, NOT sidebar page expanders like "Expand Research Overview"
    const expandButtons = await page
      .getByRole("button", { name: "Expand content", exact: true })
      .all();

    if (expandButtons.length === 0) {
      break; // No more collapsed sections
    }

    let clickedThisRound = 0;
    for (const btn of expandButtons) {
      try {
        if (await btn.isVisible()) {
          // Scroll element into view before clicking
          await btn.scrollIntoViewIfNeeded();
          await page.waitForTimeout(100);
          await btn.click();
          clickedThisRound++;
          expandedCount++;
          // Brief pause to let content expand
          await page.waitForTimeout(300);
          // Escape to close any accidental popups
          await page.keyboard.press("Escape");
          await page.waitForTimeout(100);
        }
      } catch (e) {
        // Ignore click errors (element may have been removed/changed)
      }
    }

    if (clickedThisRound === 0) {
      break; // All visible buttons already clicked
    }

    // Wait for expanded content to render before next round
    await page.waitForTimeout(500);
  }

  // Final escape to ensure no menus are open
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);

  if (expandedCount > 0) {
    log(`  📂 Expanded ${expandedCount} collapsed sections`);
  }

  return expandedCount;
}

async function scrollSidebarAndCollectLinks(page, docId) {
  const allLinks = new Map(); // url -> {title, url, depth}

  // Find the sidebar/navigation container
  // Coda typically uses a scrollable nav panel on the left
  const sidebar = await page.$(
    '[data-testid="doc-nav"], [role="navigation"], .nav-panel, [class*="sidebar"], [class*="navigation"]',
  );

  if (!sidebar) {
    log("    (No sidebar container found, using page scroll)");
    // Fallback: scroll the whole page
    await page.evaluate(async () => {
      const delay = (ms) => new Promise((r) => setTimeout(r, ms));
      for (let i = 0; i < 20; i++) {
        window.scrollTo(0, i * 500);
        await delay(100);
      }
      window.scrollTo(0, 0);
    });
    return [];
  }

  // Scroll the sidebar incrementally and collect links at each position
  const scrollHeight = await sidebar.evaluate((el) => el.scrollHeight);
  const clientHeight = await sidebar.evaluate((el) => el.clientHeight);
  const scrollSteps = Math.ceil(scrollHeight / (clientHeight * 0.8));

  log(`    Sidebar scroll: ${scrollSteps} steps (height: ${scrollHeight}px)`);

  for (let step = 0; step <= scrollSteps; step++) {
    // Scroll to position
    await sidebar.evaluate(
      (el, pos) => {
        el.scrollTop = pos;
      },
      step * clientHeight * 0.8,
    );

    await page.waitForTimeout(150); // Let virtualized content render

    // Collect visible links
    const visibleLinks = await page.evaluate((docId) => {
      const results = [];
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
    }, docId);

    // Add to collection
    for (const link of visibleLinks) {
      if (!allLinks.has(link.url)) {
        allLinks.set(link.url, link);
      }
    }

    // Log progress every 5 steps
    if (step > 0 && step % 5 === 0) {
      log(
        `    ... ${allLinks.size} unique links found (step ${step}/${scrollSteps})`,
      );
    }
  }

  // Scroll back to top
  await sidebar.evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.waitForTimeout(200);

  return Array.from(allLinks.values());
}

async function discoverAllPages(page, seenUrls) {
  log("  Expanding navigation...");

  // Close any open popups/menus first
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);

  // Expand collapsed sidebar sections using accessibility-based selectors
  // Target ONLY buttons that start with "Expand " (sidebar page expanders)
  // Avoid "Change icon", "Options", or other buttons
  let totalExpanded = 0;
  for (let round = 0; round < 20; round++) {
    // Increased rounds for deep nesting
    // Get all buttons and filter to those with names starting with "Expand "
    const allButtons = await page.getByRole("button").all();
    let expandedThisRound = 0;

    for (const btn of allButtons) {
      try {
        const name =
          (await btn.getAttribute("aria-label")) || (await btn.innerText());
        const ariaExpanded = await btn.getAttribute("aria-expanded");

        // Only target buttons that:
        // 1. Have name starting with "Expand " (page expanders in sidebar)
        // 2. Are NOT expanded yet (aria-expanded="false")
        // 3. Are visible
        // Skip: "Change icon...", "...Options", "Expand content" (handled elsewhere)
        if (
          name &&
          name.startsWith("Expand ") &&
          !name.includes("content") && // "Expand content" handled by expandAllSections
          ariaExpanded === "false" &&
          (await btn.isVisible())
        ) {
          await btn.click();
          await page.waitForTimeout(150);
          expandedThisRound++;
          totalExpanded++;

          // Press Escape after each click to close any accidentally opened popups
          await page.keyboard.press("Escape");
          await page.waitForTimeout(100);
        }
      } catch {
        // Button may have become stale, continue
      }
    }

    if (expandedThisRound > 0) {
      log(`    Round ${round + 1}: expanded ${expandedThisRound} sections`);
    }

    if (expandedThisRound === 0) break; // No more to expand
  }

  log(`  ✓ Navigation expanded (${totalExpanded} total sections)`);

  // Scroll the sidebar to force all virtualized items to render
  log("  Scrolling sidebar to load all items...");
  const sidebarLinks = await scrollSidebarAndCollectLinks(
    page,
    CONFIG.CODA_DOC_ID,
  );
  log(`  ✓ Found ${sidebarLinks.length} links via sidebar scroll`);

  log("  Scanning for additional page links...");
  const links = await page.evaluate((docId) => {
    const results = [];
    const seen = new Set();

    // Method 1: Standard anchor tags
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

    // Method 2: Elements with data-href or data-url attributes (common in SPAs)
    document.querySelectorAll("[data-href], [data-url]").forEach((el) => {
      const href = el.dataset.href || el.dataset.url;
      const text = el.textContent.trim();
      if (href && href.includes(docId) && text && !seen.has(href)) {
        seen.add(href);
        results.push({
          title: text.replace(/\s+/g, " ").substring(0, 100),
          url: href.startsWith("http") ? href : `https://coda.io${href}`,
          depth: 0,
        });
      }
    });

    // Method 3: Navigation items (treeitem role often used in sidebars)
    document
      .querySelectorAll('[role="treeitem"], [role="menuitem"], [role="link"]')
      .forEach((el) => {
        // Try to find associated link
        const link = el.querySelector("a") || el.closest("a");
        const href = link?.href || el.getAttribute("href");
        const text = el.textContent.trim();

        if (href && href.includes(docId) && text && !seen.has(href)) {
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

  // Merge sidebar links with page-scanned links
  const allLinksMap = new Map();

  // Add sidebar links first
  for (const link of sidebarLinks) {
    if (!allLinksMap.has(link.url)) {
      allLinksMap.set(link.url, link);
    }
  }

  // Add page-scanned links
  for (const link of links) {
    if (!allLinksMap.has(link.url)) {
      allLinksMap.set(link.url, link);
    }
  }

  // Add main page if not already present
  if (!allLinksMap.has(CONFIG.CODA_URL)) {
    allLinksMap.set(CONFIG.CODA_URL, {
      title: "Main Page",
      url: CONFIG.CODA_URL,
      depth: 0,
    });
  }

  const allLinks = Array.from(allLinksMap.values());
  const newLinks = allLinks.filter((l) => !seenUrls.has(l.url));

  // Log discovered pages
  log(
    `  📄 Discovered ${newLinks.length} new pages (${allLinks.length} total unique):`,
  );
  for (const link of newLinks.slice(0, 20)) {
    // Show first 20
    log(`     • ${link.title}`);
  }
  if (newLinks.length > 20) {
    log(`     ... and ${newLinks.length - 20} more`);
  }

  return newLinks;
}

async function discoverLinksOnPage(page, seenUrls) {
  const links = await page.evaluate((docId) => {
    const results = [];
    const seen = new Set();

    // Same discovery logic as discoverAllPages
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

    // Check data attributes
    document.querySelectorAll("[data-href], [data-url]").forEach((el) => {
      const href = el.dataset.href || el.dataset.url;
      const text = el.textContent.trim();
      if (href && href.includes(docId) && text && !seen.has(href)) {
        seen.add(href);
        results.push({
          title: text.replace(/\s+/g, " ").substring(0, 100),
          url: href.startsWith("http") ? href : `https://coda.io${href}`,
          depth: 0,
        });
      }
    });

    // Check role-based navigation
    document
      .querySelectorAll('[role="treeitem"], [role="menuitem"], [role="link"]')
      .forEach((el) => {
        const link = el.querySelector("a") || el.closest("a");
        const href = link?.href || el.getAttribute("href");
        const text = el.textContent.trim();
        if (href && href.includes(docId) && text && !seen.has(href)) {
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

  return links.filter((l) => !seenUrls.has(l.url));
}

async function savePageContent(content, pageInfo) {
  const timestamp = new Date().toISOString();
  const pageId =
    pageInfo.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .substring(0, 50) || "page";

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

  const mdContent = `# Coda Extraction: ${pageInfo.title}

**Source**: ${pageInfo.url}
**Extracted**: ${timestamp}
**Method**: GPT-4o Vision

---

${content}
`;

  const metadata = {
    source: {
      doc_id: CONFIG.CODA_DOC_ID,
      page_url: pageInfo.url,
      page_title: pageInfo.title,
    },
    extraction: {
      timestamp,
      method: "gpt-4o-vision",
    },
    output: {
      markdown_file: mdFile,
      size_bytes: Buffer.byteLength(mdContent),
    },
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
