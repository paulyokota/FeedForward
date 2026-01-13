#!/usr/bin/env node
/**
 * Probe Coda embed to discover data endpoints and page structure
 */

const { chromium } = require("playwright");
const fs = require("fs").promises;
const path = require("path");

const CONFIG = {
  EMBED_URL: "https://coda.io/embed/c4RRJ_VLtW/_susSTOua?viewMode=embedplay",
  DOC_URL: "https://coda.io/d/Tailwind-Research-Ops_dc4RRJ_VLtW",
  DOC_ID: "c4RRJ_VLtW",
  USER_DATA_DIR: ".playwright-profile",
};

async function main() {
  console.log("=".repeat(60));
  console.log("CODA EMBED PROBE - Discovering data endpoints");
  console.log("=".repeat(60));

  const context = await chromium.launchPersistentContext(
    path.join(process.cwd(), CONFIG.USER_DATA_DIR),
    { headless: false, viewport: { width: 1920, height: 1080 } },
  );

  const page = context.pages()[0] || (await context.newPage());

  // Collect all network requests
  const apiRequests = [];
  const jsonResponses = [];

  page.on("request", (req) => {
    const url = req.url();
    if (
      url.includes("/api") ||
      url.includes("graphql") ||
      url.includes("/v1/")
    ) {
      apiRequests.push({
        method: req.method(),
        url: url,
        type: "request",
      });
      console.log(`📡 API Request: ${req.method()} ${url.substring(0, 100)}`);
    }
  });

  page.on("response", async (res) => {
    const url = res.url();
    const contentType = res.headers()["content-type"] || "";

    if (contentType.includes("application/json")) {
      try {
        const body = await res.json();
        const bodyStr = JSON.stringify(body);

        jsonResponses.push({
          url: url.substring(0, 150),
          status: res.status(),
          keys: Object.keys(body).slice(0, 10),
          hasPages: bodyStr.includes("page"),
          hasSections: bodyStr.includes("section"),
          sample: bodyStr.substring(0, 500),
        });
        console.log(`📦 JSON Response: ${url.substring(0, 80)}...`);
        console.log(`   Keys: ${Object.keys(body).slice(0, 5).join(", ")}`);

        // Save critical responses to files
        if (url.includes("fui-critical") || url.includes("fui-allcanvas")) {
          const filename = url.includes("fui-critical")
            ? "fui-critical.json"
            : "fui-allcanvas.json";
          await fs.writeFile(
            `data/coda_raw/${filename}`,
            JSON.stringify(body, null, 2),
          );
          console.log(
            `   💾 SAVED: data/coda_raw/${filename} (${(bodyStr.length / 1024).toFixed(1)}KB)`,
          );
        }
      } catch (e) {
        // Not valid JSON
      }
    }
  });

  // Try loading the main doc first (authenticated)
  console.log("\n1. Loading main document...");
  await page.goto(CONFIG.DOC_URL, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(5000);

  // Now try the embed
  console.log("\n2. Loading embed URL...");
  await page.goto(CONFIG.EMBED_URL, {
    waitUntil: "networkidle",
    timeout: 60000,
  });
  await page.waitForTimeout(5000);

  // Check for any exposed data in window object
  console.log("\n3. Checking for exposed JavaScript data...");
  const windowData = await page.evaluate(() => {
    const found = {};

    // Check common patterns for embedded data
    if (window.__INITIAL_STATE__)
      found.initialState = Object.keys(window.__INITIAL_STATE__);
    if (window.__DATA__) found.data = Object.keys(window.__DATA__);
    if (window.__PRELOADED_STATE__)
      found.preloaded = Object.keys(window.__PRELOADED_STATE__);
    if (window.Coda) found.coda = Object.keys(window.Coda);
    if (window.CodaDoc) found.codaDoc = Object.keys(window.CodaDoc);
    if (window.__NEXT_DATA__)
      found.nextData = Object.keys(window.__NEXT_DATA__);

    // Look for any global with "doc" or "page" in the name
    for (const key of Object.keys(window)) {
      if (
        key.toLowerCase().includes("doc") ||
        key.toLowerCase().includes("page")
      ) {
        if (typeof window[key] === "object" && window[key] !== null) {
          found[key] = Object.keys(window[key]).slice(0, 5);
        }
      }
    }

    return found;
  });

  console.log("Window data found:", JSON.stringify(windowData, null, 2));

  // Look for page links in current DOM
  console.log("\n4. Extracting all internal links...");
  const links = await page.evaluate((docId) => {
    const results = [];
    document.querySelectorAll("a[href]").forEach((a) => {
      if (a.href.includes(docId) || a.href.includes("coda.io")) {
        results.push({
          text: a.textContent.trim().substring(0, 50),
          href: a.href,
        });
      }
    });
    return results;
  }, CONFIG.DOC_ID);

  console.log(`Found ${links.length} internal links`);
  links
    .slice(0, 20)
    .forEach((l) => console.log(`  • ${l.text}: ${l.href.substring(0, 60)}`));

  // Summary
  console.log("\n" + "=".repeat(60));
  console.log("SUMMARY");
  console.log("=".repeat(60));
  console.log(`API requests captured: ${apiRequests.length}`);
  console.log(`JSON responses captured: ${jsonResponses.length}`);

  if (jsonResponses.length > 0) {
    console.log("\nJSON endpoints found:");
    jsonResponses.forEach((r) => {
      console.log(`  ${r.url}`);
      console.log(`    Keys: ${r.keys.join(", ")}`);
      if (r.hasPages) console.log(`    ⭐ Contains 'page' data`);
      if (r.hasSections) console.log(`    ⭐ Contains 'section' data`);
    });
  }

  // Keep browser open for manual inspection
  console.log(
    "\n🔍 Browser left open for manual inspection. Press Ctrl+C to exit.",
  );
  await new Promise(() => {}); // Keep running
}

main().catch(console.error);
