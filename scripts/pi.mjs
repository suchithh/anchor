import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { productionPi } from "./production-pi.mjs";

const executable = productionPi();
// Invoke JS directly on Windows so prompt arguments never pass through cmd.exe.
const result = process.platform === "win32"
  ? spawnSync(process.execPath, [join(dirname(executable), "node_modules", "@earendil-works", "pi-coding-agent", "dist", "cli.js"), ...process.argv.slice(2)], { stdio: "inherit" })
  : spawnSync(executable, process.argv.slice(2), { stdio: "inherit" });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
