# Coda Playwright Extraction - Autonomous Workflow

> **Part of the Hybrid Extraction Strategy**
>
> This workflow handles **page content extraction** via Playwright. For the overall extraction strategy, see `coda-extraction-doc.md`. API-based table/hierarchy extraction is handled separately.

**STATUS**: PHASE_0_PENDING
**CURRENT_PHASE**: None
**FILES_CREATED**: 0
**EXTRACTION_COMPLETE**: False
**GIT_COMMITTED**: False

---

## USER INPUTS REQUIRED

Before starting, you need these values from the user:

1. **CODA_DOC_URL**: Full URL of the Coda document to extract (e.g., `https://coda.io/@username/doc-name`)
2. **CODA_DOC_ID**: Document ID for file naming (e.g., `c4RRJ_VLtW`)

**Output Location**: Files saved to `data/coda_raw/pages/` per the extraction strategy.

**Once you have these inputs, proceed autonomously through all phases without waiting for approval between phases.**

---

## PHASE 1: SETUP & VERIFICATION

**Goal**: Verify environment and prepare for extraction.

**Steps**:

1. **Check Playwright installation**
   - Run: `npm list playwright` or check `node_modules`
   - If not installed: Run `npm install playwright` and `npx playwright install`
   - If npm not available: Alert user and provide installation instructions

2. **Verify git repository**
   - Check that we're in a git repo: `git status`
   - Verify branch is clean (or warn about uncommitted changes)
   - Confirm `REPO_PATH` exists or create it: `mkdir -p [REPO_PATH]`

3. **Generate extraction timestamp**
   - Create ISO 8601 timestamp: `YYYY-MM-DDTHH:MM:SSZ`
   - This will be used in all output files and commit messages

4. **Update status**
   - Set **STATUS**: `PHASE_1_COMPLETE`
   - Set **CURRENT_PHASE**: `PHASE_2`
   - Proceed immediately to Phase 2

**OUTPUT**: Environment verified, timestamp generated, ready to create script

---

## PHASE 2: GENERATE PLAYWRIGHT SCRIPT

**Goal**: Write the extraction script that will scrape the Coda doc.

**Script Requirements**:

Create `coda_extract.js` with the following logic:

```javascript
// Template - Claude should generate the actual implementation

const { chromium } = require("playwright");
const fs = require("fs").promises;
const readline = require("readline");

const CODA_URL = "[CODA_DOC_URL from user]";
const CODA_DOC_ID = "[CODA_DOC_ID from user]";
const OUTPUT_DIR = "data/coda_raw/pages";
const TIMESTAMP = "[generated ISO timestamp]";

// Output files follow strategy doc convention
// Each page: page_{id}.md + page_{id}.meta.json

async function waitForUser(prompt) {
  // Pause and wait for Enter keypress
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) =>
    rl.question(prompt, (ans) => {
      rl.close();
      resolve(ans);
    }),
  );
}

async function extractCoda() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  console.log("Navigating to Coda doc...");
  await page.goto(CODA_URL, { waitUntil: "networkidle" });

  console.log("\n⏸️  MANUAL AUTH REQUIRED ⏸️");
  console.log("Please log into Coda in the browser window.");
  console.log(
    "Once logged in and the doc is visible, press Enter here to continue...\n",
  );
  await waitForUser("Press Enter when ready: ");

  console.log("Extracting content...");

  // DOM traversal logic:
  // - Find main canvas/content area (skip navigation/sidebar)
  // - Extract text from headings, paragraphs, lists
  // - Preserve hierarchy (H1 > H2 > H3, etc.)
  // - Handle dynamic content (scroll, click sections if needed)
  // - Build Markdown string with proper formatting

  const extractedContent = await page.evaluate(() => {
    // Custom extraction logic goes here
    // Return { markdown: '...', sections: [...], stats: {...} }
  });

  // Format Markdown with header
  const markdownOutput = `# Coda Extraction: [doc name]

**Source**: ${CODA_URL}  
**Extracted**: ${TIMESTAMP}  
**Method**: Playwright + Claude Code  
**Sections**: ${extractedContent.sections.length}

---

${extractedContent.markdown}
`;

  // Create metadata JSON (per strategy doc format)
  const pageId = extractedContent.pageId || "main";
  const mdFile = `${OUTPUT_DIR}/page_${pageId}.md`;
  const metaFile = `${OUTPUT_DIR}/page_${pageId}.meta.json`;

  const metadata = {
    source: {
      doc_id: CODA_DOC_ID,
      doc_url: CODA_URL,
      page_id: pageId,
      doc_name: "[extracted or provided doc name]",
    },
    extraction: {
      timestamp: TIMESTAMP,
      method: "playwright_claude",
      sections_found: extractedContent.sections,
      total_sections: extractedContent.sections.length,
    },
    output: {
      markdown_file: mdFile,
      meta_file: metaFile,
      size_bytes: Buffer.byteLength(markdownOutput, "utf8"),
    },
  };

  // Ensure output directory exists
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  // Write files
  await fs.writeFile(mdFile, markdownOutput, "utf8");
  await fs.writeFile(metaFile, JSON.stringify(metadata, null, 2), "utf8");

  console.log(`✅ Extracted ${extractedContent.sections.length} sections`);
  console.log(`📄 Saved to: ${mdFile}`);
  console.log(`📊 Metadata: ${metaFile}`);

  await browser.close();
  return metadata;
}

extractCoda().catch(console.error);
```

**Claude's Tasks**:

1. Generate the complete, functional script (not just template)
2. Implement robust DOM extraction logic for Coda's structure
3. Handle edge cases:
   - Lazy-loaded content (scroll or click to trigger)
   - Nested sections (preserve hierarchy)
   - Code blocks, lists, formatted text
   - Skip navigation UI, sidebars, menus
4. Save script as `coda_extract.js` in current directory
5. Update status:
   - **STATUS**: `PHASE_2_COMPLETE`
   - **CURRENT_PHASE**: `PHASE_3`
6. Proceed immediately to Phase 3

**OUTPUT**: `coda_extract.js` ready to execute

---

## PHASE 3: EXECUTE EXTRACTION

**Goal**: Run the script, pause for user auth, complete extraction.

**Steps**:

1. **Launch the extraction script**
   - Run: `node coda_extract.js`
   - Script will open browser and navigate to Coda URL

2. **User intervention point**
   - Script pauses with message: "⏸️ MANUAL AUTH REQUIRED"
   - **YOU (the user) log into Coda manually in the browser**
   - Once logged in and doc is visible, press Enter in terminal
   - Script resumes automatically

3. **Extraction proceeds**
   - Script extracts all content
   - Formats as Markdown
   - Saves both files to `REPO_PATH`

4. **Capture execution output**
   - Note any warnings or errors
   - Record extraction statistics (sections found, file sizes)

5. **Update status**
   - Set **STATUS**: `PHASE_3_COMPLETE`
   - Set **FILES_CREATED**: 2
   - Set **EXTRACTION_COMPLETE**: True
   - Set **CURRENT_PHASE**: `PHASE_4`
   - Proceed immediately to Phase 4

**OUTPUT**: Both files created in repo

---

## PHASE 4: VERIFICATION

**Goal**: Verify extraction quality and completeness.

**Steps**:

1. **Check files exist**
   - Verify: `data/coda_raw/pages/page_{id}.md`
   - Verify: `data/coda_raw/pages/page_{id}.meta.json`

2. **Validate Markdown content**
   - Check file size (should be > 0 bytes)
   - Verify header metadata is present
   - Spot-check first few sections for proper formatting
   - Confirm heading hierarchy looks correct

3. **Validate JSON metadata**
   - Parse JSON to verify valid structure
   - Check all required fields are populated
   - Verify section count matches Markdown content

4. **Report extraction statistics**
   - Total sections extracted: X
   - Markdown file size: Y KB
   - Extraction timestamp: [ISO date]
   - Source URL: [CODA_DOC_URL]

5. **Quality assessment**
   - If content looks complete: Proceed to Phase 5
   - If content appears incomplete or malformed:
     - Report specific issues found
     - Recommend fixes (e.g., "Section X appears truncated, may need scroll logic")
     - Ask user if they want to: (a) Accept as-is, (b) Retry with adjusted script
     - If user chooses retry: Return to Phase 2 with refinements

6. **Update status**
   - Set **STATUS**: `PHASE_4_COMPLETE`
   - Set **CURRENT_PHASE**: `PHASE_5`
   - Proceed immediately to Phase 5 (if quality is acceptable)

**OUTPUT**: Extraction verified and ready to commit

---

## PHASE 5: GIT COMMIT

**Goal**: Commit the extracted files with structured metadata.

**Steps**:

1. **Stage the new files**
   - Run: `git add data/coda_raw/pages/`

2. **Generate commit message**
   - Use this exact format:

     ```
     Extract Coda pages: [DOC_ID]

     Source: [CODA_DOC_URL]
     Timestamp: [ISO timestamp]
     Pages extracted: [count]
     Method: Playwright + Claude Code
     Output: data/coda_raw/pages/
     ```

3. **Create the commit**
   - Run: `git commit -m "[generated message]"`
   - Capture commit hash

4. **Report commit details**
   - Commit hash: [hash]
   - Files committed: 2
   - Branch: [current branch name]
   - Remind user: "Changes committed locally. Run `git push` when ready to sync to remote."

5. **Update status**
   - Set **STATUS**: `PHASE_5_COMPLETE`
   - Set **GIT_COMMITTED**: True
   - Set **CURRENT_PHASE**: `COMPLETE`

6. **Output completion signal**
   - Print: `<promise>CODA_EXTRACTION_COMPLETE</promise>`

**OUTPUT**: Files committed to git, workflow complete

---

## COMPLETION CRITERIA

Before outputting `<promise>CODA_EXTRACTION_COMPLETE</promise>`, verify ALL of these are true:

✓ Playwright script generated and functional
✓ Extraction executed successfully
✓ Markdown files created in `data/coda_raw/pages/`
✓ Metadata JSON files created alongside markdown
✓ Files verified for quality and completeness
✓ Git commit created with structured message
✓ User notified of commit hash and reminded to push

**If all criteria met**: Output `<promise>CODA_EXTRACTION_COMPLETE</promise>` and stop.

---

## ERROR HANDLING

**If Playwright installation fails**:

- Provide explicit installation commands for user's OS
- Offer to retry after user confirms installation
- Do NOT proceed to script generation without working Playwright

**If extraction script crashes**:

- Capture and report the error message
- Identify likely cause (auth timeout, DOM selector issue, etc.)
- Suggest specific fix
- Offer to regenerate script with adjustments

**If extraction produces empty or malformed content**:

- Report what was found (or not found)
- Check if auth actually succeeded (user may have skipped login)
- Suggest: "Re-run script and ensure you're fully logged into Coda before pressing Enter"
- Do NOT commit empty or broken files

**If git commit fails**:

- Report git error message
- Check for common issues (nothing staged, merge conflicts, etc.)
- Offer solutions
- Do NOT mark as complete if commit didn't succeed

**If user wants to abort mid-workflow**:

- Clean up any partial files created
- Report current state: which phases completed, which files exist
- User can manually delete `coda_extract.js` and output files if needed

---

## AUTONOMOUS EXECUTION INSTRUCTIONS

**How to Run (from user's perspective)**:

```
Read docs/coda-extraction/coda-extraction-pmt.md and execute autonomously.

Required inputs:
- CODA_DOC_URL: [your Coda doc URL]
- CODA_DOC_ID: [document ID, e.g., c4RRJ_VLtW]

Output goes to: data/coda_raw/pages/

Proceed through all 5 phases without waiting for approval between phases. The ONLY time you pause is during Phase 3 when the browser opens for manual Coda authentication. After I press Enter, resume immediately.

Update the status header after completing each phase, then auto-advance to the next phase.

When all phases complete successfully, output <promise>CODA_EXTRACTION_COMPLETE</promise> and stop.

Begin now.
```

---

## STATUS TRACKING

Update the header of this file after each phase:

- **STATUS**: Current phase completion state (`PHASE_X_COMPLETE`)
- **CURRENT_PHASE**: Next phase to execute or `COMPLETE`
- **FILES_CREATED**: Count of output files (0, 1, or 2)
- **EXTRACTION_COMPLETE**: Boolean
- **GIT_COMMITTED**: Boolean

This provides at-a-glance progress tracking and makes it easy to resume if interrupted.

---

**END OF PROMPT**
