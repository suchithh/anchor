import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { once } from "node:events";
import { GroundingClient, groundingConfig, parseResult, type VerificationResult } from "../src/grounding-client.js";
import { Presentation, selectClaim } from "../src/grounding-presentation.js";
import { registerGrounding } from "../src/grounding-extension.js";

const result: VerificationResult = {
  run_id: "r", claim_id: "c", verdict: "SUPPORTED", p_supported: 1, p_contradicted: 0, p_insufficient: 0,
  probability_kind: "one_hot_label", evidence_ids: ["e1"], cache_hit: false, deduplicated: false,
  corpus_revision: "v1", verifier: "jev:fixture", cache_lookup_latency_ms: 2, retrieval_latency_ms: 3,
  reranker_latency_ms: 0, verifier_latency_ms: 4, persistence_latency_ms: 1, total_latency_ms: 10,
  verifier_cost: null, avoided_verifier_cost: null, avoided_cost_kind: "unavailable",
  usage: [{ provider: "openrouter", operation: "jev", calls: 1 }],
};
const request = { run_id: "r", claim_id: "c", claim: "A concrete claim to verify.", context: null, scope: { corpus_id: "http_rfc" }, importance: 1 };

test("contract rejects malformed verdicts, probabilities, latency and mismatched usage", () => {
  assert.deepEqual(parseResult(result), result);
  for (const patch of [{ verdict: "TRUE" }, { p_supported: .2 }, { total_latency_ms: -1 }, { cache_hit: "yes" }, { usage: [{}] }])
    assert.throws(() => parseResult({ ...result, ...patch }));
  assert.throws(() => groundingConfig({ PI_GRAIL_GROUNDING_URL: "https://user:secret@example.com" }));
  assert.equal(selectClaim("short"), undefined);
  assert.equal(selectClaim("```ts\n" + "x".repeat(50) + "\n```"), undefined);
});

test("score uses real events and counts; cache and duplicate handling", () => {
  const p = new Presentation();
  p.accept(result);
  assert.equal(p.score, 96);
  p.accept({ ...result, verdict: "CONTRADICTED", p_supported: 0, p_contradicted: 1 });
  assert.equal(p.score, 61);
  assert.equal(p.drift, true);
  assert.equal(p.accept(result).recovered, true);
  assert.equal(p.score, 91);
  p.accept({ ...result, cache_hit: true, usage: [], verifier_latency_ms: 0 });
  assert.equal(p.hits, 1); assert.equal(p.calls, 3); assert.equal(p.checked, 4);
  p.accept({ ...result, deduplicated: true });
  assert.equal(p.checked, 4);
  assert.ok(!p.lines(false, 0).join("\n").includes("%"));
});

test("HTTP transport preserves contract, makes no retries, supports timeout and abort", async () => {
  let mode = "ok", calls = 0;
  const server = createServer(async (req, res) => {
    calls++;
    let body = ""; for await (const chunk of req) body += chunk;
    if (mode === "hang") return;
    if (mode === "error") { res.writeHead(502); res.end(); return; }
    assert.deepEqual(JSON.parse(body), request);
    res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(result));
  });
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  const address = server.address() as { port: number };
  const client = new GroundingClient({ url: `http://127.0.0.1:${address.port}`, corpus: "http_rfc", enabled: true, demo: true, timeout: 100 });
  try {
    assert.deepEqual(await client.verify(request), result);
    mode = "error"; await assert.rejects(client.verify(request), /502/); assert.equal(calls, 2);
    mode = "hang"; await assert.rejects(client.verify(request), /timed out/);
    const controller = new AbortController(); controller.abort();
    await assert.rejects(client.verify(request, controller.signal), /cancelled/);
  } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
});

test("Pi hook returns before HTTP, injects evidence, and ignores results after reset", async () => {
  const oldEnv = { ...process.env }, oldFetch = globalThis.fetch;
  Object.assign(process.env, { PI_GRAIL_GROUNDING_ENABLED: "true", PI_GRAIL_CORPUS_ID: "http_rfc", DEMO_MODE: "true" });
  const handlers: Record<string, Function> = {}, commands: Record<string, any> = {}, messages: any[] = [];
  const pending: { request: any; resolve: (response: Response) => void }[] = [];
  globalThis.fetch = (async (_url: any, init: any) => {
    if (!init.body) return Response.json([{ id: "e1", text: "Official source fact.", source_uri: "https://example.org/rfc", version: "v1" }]);
    return new Promise<Response>(resolve => pending.push({ request: JSON.parse(init.body), resolve }));
  }) as typeof fetch;
  const pi = { on: (name: string, f: Function) => handlers[name] = f,
    registerCommand: (name: string, c: any) => commands[name] = c,
    appendEntry() {}, sendMessage: (...args: any[]) => messages.push(args) };
  const ctx = { hasUI: false, mode: "rpc" };
  const flush = () => new Promise(resolve => setTimeout(resolve, 10));
  try {
    registerGrounding(pi as any);
    const event = { message: { role: "assistant", content: [{ type: "text", text: "This is a concrete technical assertion that requires verification." }] } };
    assert.equal(handlers.message_end(event, ctx), undefined);
    assert.equal(pending.length, 1);
    const first = pending.shift()!;
    first.resolve(Response.json({ ...result, ...{ run_id: first.request.run_id, claim_id: first.request.claim_id }, verdict: "CONTRADICTED", p_supported: 0, p_contradicted: 1 }));
    await flush();
    assert.equal(messages.length, 1);
    assert.ok(messages[0][0].content.includes("Official source fact."));
    assert.deepEqual(messages[0][1], { deliverAs: "steer", triggerTurn: false });
    handlers.message_end(event, ctx);
    await commands.ground.handler("new", ctx);
    const stale = pending.shift()!;
    stale.resolve(Response.json({ ...result, run_id: stale.request.run_id, claim_id: stale.request.claim_id }));
    await flush();
    assert.equal(messages.length, 1);
  } finally {
    handlers.session_shutdown(); globalThis.fetch = oldFetch;
    for (const key of Object.keys(process.env)) if (!(key in oldEnv)) delete process.env[key];
    Object.assign(process.env, oldEnv);
  }
});
