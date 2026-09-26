import type { VerificationResult } from "./grounding-client.js";

export class Presentation {
  score = 95;
  checked = 0;
  hits = 0;
  calls = 0;
  drift = false;
  status = "WAITING FOR CHECKS";
  accept(r: VerificationResult): { before: number; after: number; recovered: boolean } {
    const before = this.score;
    if (r.deduplicated) return { before, after: before, recovered: false };
    this.checked++;
    this.hits += Number(r.cache_hit);
    this.calls += r.usage.filter(u => ["jev", "llm"].includes(u.operation)).reduce((n,u) => n + u.calls, 0);
    const recovered = this.drift && r.verdict === "SUPPORTED";
    if (r.verdict === "CONTRADICTED") { this.score = Math.max(45, this.score - 35); this.drift = true; }
    else if (r.verdict === "INSUFFICIENT") this.score = Math.max(70, this.score - 8);
    else if (recovered) { this.score = Math.min(95, this.score + 30); this.drift = false; }
    else this.score = Math.min(98, this.score + 1);
    if (r.cache_hit) this.score = Math.min(97, this.score + 1);
    this.status = this.drift ? "DRIFT DETECTED" : r.verdict === "SUPPORTED" ? "GROUNDED" : "INSUFFICIENT EVIDENCE";
    return { before, after: this.score, recovered };
  }
  lines(demo: boolean, pending: number, shown = this.score): string[] {
    return ["──────────────────────────────────", "GRAIL GROUNDING",
      ...(demo ? [`Demo score        ${shown}% (not a probability)`, "█".repeat(Math.round(shown/5)) + "░".repeat(20-Math.round(shown/5))] : []),
      `Status            ${this.status}`, `Claims checked    ${this.checked}`,
      `Verified hits     ${this.hits}`, `Verifier calls    ${this.calls}`, `Pending           ${pending}`,
      "──────────────────────────────────"];
  }
}

// Deliberately tiny MVP adapter: one prose paragraph per completed assistant message.
export function selectClaim(text: string): string | undefined {
  const prose = text.replace(/```[\s\S]*?```/g, "").split(/\n\s*\n/).map(x => x.trim());
  return prose.find(x => x.length >= 40)?.slice(0, 2000);
}
