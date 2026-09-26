import { readFileSync } from "node:fs";
import { parseEnv } from "node:util";

export interface VerificationRequest {
  run_id: string;
  claim_id: string;
  claim: string;
  context: string | null;
  scope: { corpus_id: string; source_id?: string; version?: string };
  importance: number;
}
// Mirrors grounding-service/src/models.py. Unknown additive fields are retained.
export interface VerificationResult {
  run_id: string; claim_id: string;
  verdict: "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT";
  p_supported: number; p_contradicted: number; p_insufficient: number;
  probability_kind: string; evidence_ids: string[]; cache_hit: boolean;
  cache_lookup_latency_ms: number; retrieval_latency_ms: number;
  reranker_latency_ms: number; verifier_latency_ms: number;
  persistence_latency_ms: number; total_latency_ms: number;
  corpus_revision: string; verifier: string; deduplicated: boolean;
  verifier_cost: number | null; avoided_verifier_cost: number | null; avoided_cost_kind: string;
  usage: { provider: string; operation: string; calls: number; model?: string | null }[];
}
export interface Evidence { id: string; text: string; source_uri: string; version: string }
export interface GroundingConfig { url: string; corpus: string; enabled: boolean; demo: boolean; timeout: number }

export function groundingConfig(env?: NodeJS.ProcessEnv): GroundingConfig {
  if (!env) {
    let local = {};
    try { local = parseEnv(readFileSync(new URL("../.env", import.meta.url), "utf8")); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    env = { ...local, ...process.env };
  }
  const url = new URL(env.PI_GRAIL_GROUNDING_URL || "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw new Error("PI_GRAIL_GROUNDING_URL must be an HTTP(S) URL without credentials/query/fragment.");
  const timeout = Number(env.PI_GRAIL_GROUNDING_TIMEOUT_MS || 15000);
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 180000) throw new Error("Invalid grounding timeout (1–180000 ms).");
  return { url: url.href.replace(/\/$/, ""), corpus: env.PI_GRAIL_CORPUS_ID?.trim() || "",
    enabled: env.PI_GRAIL_GROUNDING_ENABLED === "true", demo: env.DEMO_MODE === "true", timeout };
}

export function parseResult(value: unknown): VerificationResult {
  const r = value as VerificationResult;
  const bad = () => { throw new Error("Grounding service returned an invalid VerificationResult."); };
  if (!r || typeof r !== "object" || !["SUPPORTED", "CONTRADICTED", "INSUFFICIENT"].includes(r.verdict)) bad();
  for (const k of ["run_id", "claim_id", "corpus_revision", "verifier", "probability_kind", "avoided_cost_kind"] as const)
    if (typeof r[k] !== "string") bad();
  const probabilities = [r.p_supported, r.p_contradicted, r.p_insufficient];
  if (probabilities.some(p => !Number.isFinite(p) || p < 0 || p > 1) || Math.abs(probabilities.reduce((a,b) => a+b, 0)-1) > .002) bad();
  if (probabilities[["SUPPORTED", "CONTRADICTED", "INSUFFICIENT"].indexOf(r.verdict)] + .002 < Math.max(...probabilities)) bad();
  for (const k of ["cache_lookup_latency_ms", "retrieval_latency_ms", "reranker_latency_ms", "verifier_latency_ms", "persistence_latency_ms", "total_latency_ms"] as const)
    if (!Number.isFinite(r[k]) || r[k] < 0) bad();
  if (typeof r.cache_hit !== "boolean" || typeof r.deduplicated !== "boolean" || !Array.isArray(r.evidence_ids) || r.evidence_ids.some(x => typeof x !== "string")) bad();
  if (!Array.isArray(r.usage) || r.usage.some(u => !u || typeof u.provider !== "string" || typeof u.operation !== "string" || !Number.isInteger(u.calls) || u.calls < 0)) bad();
  for (const k of ["verifier_cost", "avoided_verifier_cost"] as const)
    if (r[k] !== null && (!Number.isFinite(r[k]) || r[k]! < 0)) bad();
  return r;
}

export class GroundingClient {
  constructor(readonly config: GroundingConfig) {}
  private async request(path: string, init: RequestInit, signal?: AbortSignal): Promise<unknown> {
    const deadline = AbortSignal.timeout(this.config.timeout);
    try {
      const response = await fetch(this.config.url + path, { ...init,
        signal: signal ? AbortSignal.any([signal, deadline]) : deadline });
      if (!response.ok) throw new Error(`Grounding HTTP ${response.status}; no judgment substituted.`);
      return await response.json();
    } catch (error) {
      if (signal?.aborted) throw new Error("Grounding request cancelled.");
      if (deadline.aborted) throw new Error(`Grounding timed out after ${this.config.timeout} ms; backend may still finish.`);
      throw new Error(error instanceof Error ? error.message : "Grounding request failed.");
    }
  }
  async verify(request: VerificationRequest, signal?: AbortSignal): Promise<VerificationResult> {
    const result = parseResult(await this.request("/verify", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }, signal));
    if (result.run_id !== request.run_id || result.claim_id !== request.claim_id) throw new Error("Grounding response IDs do not match request.");
    return result;
  }
  async evidence(result: VerificationResult, signal?: AbortSignal): Promise<Evidence[]> {
    const data = await this.request(`/runs/${encodeURIComponent(result.run_id)}/claims/${encodeURIComponent(result.claim_id)}/evidence`, {}, signal);
    if (!Array.isArray(data) || data.some(e => !e || ["id", "text", "source_uri", "version"].some(k => typeof e[k] !== "string") || !result.evidence_ids.includes(e.id)))
      throw new Error("Grounding service returned invalid evidence.");
    return data;
  }
}
