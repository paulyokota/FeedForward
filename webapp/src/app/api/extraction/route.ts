import { NextRequest, NextResponse } from "next/server";
import { spawn, ChildProcess } from "child_process";
import { readFile, access } from "fs/promises";
import { join, dirname } from "path";

// Store running process reference (survives across requests in development)
let extractionProcess: ChildProcess | null = null;
let processOutput: string[] = [];
let processStatus: "idle" | "running" | "paused" | "completed" | "error" =
  "idle";
let processError: string | null = null;
let currentMode: "dom" | "vision" = "vision";

// Get project root (parent of webapp directory)
function getProjectRoot(): string {
  const cwd = process.cwd();
  if (cwd.endsWith("webapp")) {
    return dirname(cwd);
  }
  return cwd;
}

function getScriptPath(mode: "dom" | "vision"): string {
  const scriptName =
    mode === "vision" ? "coda_vision_extract.js" : "coda_full_extract.js";
  return join(getProjectRoot(), "scripts", scriptName);
}

function getManifestPath(): string {
  return join(getProjectRoot(), "data", "coda_raw", "extraction_manifest.json");
}

function getLogPath(): string {
  return join(getProjectRoot(), "data", "coda_raw", "extraction.log");
}

function getCostPath(): string {
  return join(getProjectRoot(), "data", "coda_raw", "extraction_costs.json");
}

export async function GET() {
  let manifest = null;
  let logTail: string[] = [];
  let costs = null;

  try {
    const manifestData = await readFile(getManifestPath(), "utf8");
    manifest = JSON.parse(manifestData);
  } catch {
    // No manifest yet
  }

  try {
    const logData = await readFile(getLogPath(), "utf8");
    const lines = logData.split("\n").filter((l) => l.trim());
    logTail = lines.slice(-50);
  } catch {
    // No log yet
  }

  try {
    const costData = await readFile(getCostPath(), "utf8");
    costs = JSON.parse(costData);
  } catch {
    // No costs yet
  }

  // Also extract running cost from output if available
  let runningCost = 0;
  for (const line of processOutput) {
    const match = line.match(/💰.*\$([0-9.]+)/);
    if (match) {
      runningCost = parseFloat(match[1]) || 0;
    }
    // Also check for TOTAL COST line
    const totalMatch = line.match(/TOTAL COST: \$([0-9.]+)/);
    if (totalMatch) {
      runningCost = parseFloat(totalMatch[1]) || 0;
    }
  }

  return NextResponse.json({
    status: processStatus,
    isRunning: extractionProcess !== null && !extractionProcess.killed,
    error: processError,
    output: processOutput.slice(-100),
    manifest,
    logTail,
    costs,
    runningCost,
    mode: currentMode,
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { action, mode } = body;

  switch (action) {
    case "start":
      return startExtraction(mode || "vision");
    case "stop":
      return stopExtraction();
    case "clear":
      return clearOutput();
    default:
      return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  }
}

async function startExtraction(mode: "dom" | "vision") {
  if (extractionProcess && !extractionProcess.killed) {
    return NextResponse.json(
      { error: "Extraction already running" },
      { status: 400 },
    );
  }

  const scriptPath = getScriptPath(mode);
  const projectRoot = getProjectRoot();
  currentMode = mode;

  // Check script exists
  try {
    await access(scriptPath);
  } catch {
    return NextResponse.json(
      { error: `Script not found: ${scriptPath}` },
      { status: 404 },
    );
  }

  processOutput = [];
  processError = null;
  processStatus = "running";

  try {
    extractionProcess = spawn("node", [scriptPath], {
      cwd: projectRoot,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env },
    });

    extractionProcess.stdout?.on("data", (data: Buffer) => {
      const lines = data
        .toString()
        .split("\n")
        .filter((l) => l.trim());
      processOutput.push(...lines);
      if (processOutput.length > 500) {
        processOutput = processOutput.slice(-500);
      }
    });

    extractionProcess.stderr?.on("data", (data: Buffer) => {
      const lines = data
        .toString()
        .split("\n")
        .filter((l) => l.trim());
      processOutput.push(...lines.map((l) => `[ERROR] ${l}`));
    });

    extractionProcess.on("close", (code) => {
      if (code === 0) {
        processStatus = "completed";
      } else {
        processStatus = "error";
        processError = `Process exited with code ${code}`;
      }
      extractionProcess = null;
    });

    extractionProcess.on("error", (err) => {
      processStatus = "error";
      processError = err.message;
      extractionProcess = null;
    });

    return NextResponse.json({
      success: true,
      message: `Extraction started (${mode} mode)`,
      pid: extractionProcess.pid,
      mode,
    });
  } catch (err) {
    processStatus = "error";
    processError = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: processError }, { status: 500 });
  }
}

async function stopExtraction() {
  if (!extractionProcess || extractionProcess.killed) {
    return NextResponse.json(
      { error: "No extraction running" },
      { status: 400 },
    );
  }

  extractionProcess.kill("SIGTERM");

  setTimeout(() => {
    if (extractionProcess && !extractionProcess.killed) {
      extractionProcess.kill("SIGKILL");
    }
  }, 2000);

  processStatus = "idle";
  processOutput.push("[SYSTEM] Extraction stopped by user");

  return NextResponse.json({ success: true, message: "Extraction stopped" });
}

async function clearOutput() {
  processOutput = [];
  processError = null;
  if (!extractionProcess || extractionProcess.killed) {
    processStatus = "idle";
  }
  return NextResponse.json({ success: true, message: "Output cleared" });
}
