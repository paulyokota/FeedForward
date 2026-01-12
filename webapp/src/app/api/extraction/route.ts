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

// Get project root (parent of webapp directory)
function getProjectRoot(): string {
  // process.cwd() returns webapp directory when running Next.js
  // We need parent directory for the main FeedForward project
  const cwd = process.cwd();
  // Check if we're in webapp subdirectory
  if (cwd.endsWith("webapp")) {
    return dirname(cwd);
  }
  return cwd;
}

function getScriptPath(): string {
  return join(getProjectRoot(), "scripts", "coda_full_extract.js");
}

function getManifestPath(): string {
  return join(getProjectRoot(), "data", "coda_raw", "extraction_manifest.json");
}

function getLogPath(): string {
  return join(getProjectRoot(), "data", "coda_raw", "extraction.log");
}

export async function GET() {
  // Return current status
  let manifest = null;
  let logTail: string[] = [];

  try {
    const manifestData = await readFile(getManifestPath(), "utf8");
    manifest = JSON.parse(manifestData);
  } catch {
    // No manifest yet
  }

  try {
    const logData = await readFile(getLogPath(), "utf8");
    const lines = logData.split("\n").filter((l) => l.trim());
    logTail = lines.slice(-50); // Last 50 lines
  } catch {
    // No log yet
  }

  return NextResponse.json({
    status: processStatus,
    isRunning: extractionProcess !== null && !extractionProcess.killed,
    error: processError,
    output: processOutput.slice(-100), // Last 100 lines
    manifest,
    logTail,
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { action } = body;

  switch (action) {
    case "start":
      return startExtraction();
    case "stop":
      return stopExtraction();
    case "clear":
      return clearOutput();
    default:
      return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  }
}

async function startExtraction() {
  if (extractionProcess && !extractionProcess.killed) {
    return NextResponse.json(
      { error: "Extraction already running" },
      { status: 400 },
    );
  }

  const scriptPath = getScriptPath();
  const projectRoot = getProjectRoot();

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
    });

    extractionProcess.stdout?.on("data", (data: Buffer) => {
      const lines = data
        .toString()
        .split("\n")
        .filter((l) => l.trim());
      processOutput.push(...lines);
      // Keep last 500 lines
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
      message: "Extraction started",
      pid: extractionProcess.pid,
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

  // Give it 2 seconds then force kill
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
