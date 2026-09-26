# Anchor: Pi → Atlas grounding demo

This repository integrates Pi 0.87.1 and the Python grounding service. Both complete
upstream histories are retained by a non-squashed subtree merge. Upstream remotes:
`pi-upstream` and `grounding-upstream`. The existing Python checkout is untouched.

## Start (two terminals)

Use Node 22.19+ and Python 3.10+. From this repository:

```powershell
cd grounding-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
# Configure Atlas, Voyage and OpenRouter keys in this ignored file.
# Use the existing backend's configured .env if already provisioned.
$env:VERIFIER='jev'
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

The `http_rfc` corpus must already be ingested (see the backend README). Python's
default is `llm`; explicitly selecting `jev` is necessary for the Jev demo.
Python uses OpenRouter for Jev; the preserved `/jev` diagnostics use the direct
TypeSafe SDK and separate credentials. Integrated grounding never calls both.

```powershell
npm ci --ignore-scripts
Copy-Item .env.example .env
# Set PI_GRAIL_CORPUS_ID to the real ingested corpus.
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.87.1
npm run dev -- --extension .
```

The widget, notifications and correction message all render inside Pi. No dashboard.
The initial 95% is explicitly a demo score with zero checks, never fabricated history.

## 60-second presentation

1. `/ground status` then `/ground score`.
2. `/ground check An unqualified no-cache response can be reused without successful validation.`
   Wait for the actual verdict. If contradicted, the score drops, actual evidence is
   fetched from Atlas and queued into Pi context. Cache, verifier and timings are real.
3. Ask Pi: `Use the grounding evidence to correct that HTTP cache assumption in one sentence.`
   Its completed message is automatically checked. A supported follow-up raises the
   presentation score. Evidence delivery alone never raises it.
4. `/ground check An unqualified no-cache response requires successful validation before reuse.`
   Wait for completion, then `/ground new` and `/ground repeat`.
   The identical dependency uses persistent verified state if corpus and policy are
   unchanged. The UI shows the returned hit, real lookup latency, and skipped verifier.

An already-warm corpus may hit the cache on run one too. Do not label it a miss.
Rephrased claims are not exact cache matches. Use a genuinely new factual proposition
for a cold demonstration; do not delete shared Atlas state. The `createVectorIndex`
example requires an appropriate versioned API corpus; the existing RFC corpus cannot
establish that claim. Real network/provider latency can exceed 60 seconds; rehearse.

## Integration contract and limits

`message_end` and widget/steering APIs were checked against the installed 0.87.1 types.
One prose paragraph (40–2000 characters) is selected per completed assistant message.
At most two requests run concurrently; excess checks are visibly skipped. The hook
does not await HTTP, retry, intercept tools or block generation. Shutdown/session
changes cancel client work and ignore stale results. A cancelled HTTP request may
still finish on the backend. Run IDs reset on session changes and `/ground new`.

`src/grounding-client.ts` mirrors the Python Pydantic models and checks responses at
runtime. Existing `/verify`, `/verify/batch` and `/runs/{run_id}` are unchanged. The only
backend addition is `GET /runs/{run_id}/claims/{claim_id}/evidence`, returning actual
persisted evidence chunks scoped to the judgment's corpus/revision. Source excerpts
are injected as evidence with `deliverAs: steer`, without starting an extra agent turn.
If the agent is idle, correction is consumed on the next turn. Original backend
deployments lacking this endpoint still verify; correction reports an explicit 404.

`DEMO_MODE=true` enables the animated local score. It is not a calibrated probability
or the backend EWMA. Counts start at zero and use real events/usage. A supported
follow-up after drift is a presentation recovery, not proof all prior claims were fixed.
With demo mode off, verdicts, counters, timings and evidence still work without a score.
Errors stay errors, never INSUFFICIENT. `/ground test` makes a real RFC verification;
`/ground status` only displays local configuration. Default HTTP timeout is 15 seconds;
increase `PI_GRAIL_GROUNDING_TIMEOUT_MS` explicitly if the provider needs longer.

The original `/jev status`, `/jev models`, `/jev test` and `jev_evaluate` remain intact.

## Checks

```powershell
npm run typecheck
npm test
cd grounding-service
python -m pytest -q
```
