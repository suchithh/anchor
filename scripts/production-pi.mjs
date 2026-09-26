import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

export function productionPi() {
  const windows = process.platform === "win32";
  const prefix = execFileSync(windows ? "npm.cmd" : "npm", ["prefix", "--global"], { encoding: "utf8", shell: windows }).trim();
  const executable = windows ? join(prefix, "pi.cmd") : join(prefix, "bin", "pi");
  if (!existsSync(executable)) throw new Error("Install the production CLI: npm install -g --ignore-scripts @earendil-works/pi-coding-agent");
  return executable;
}
