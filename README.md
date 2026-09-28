# Anchor

**Evidence-grounded verification for Pi agents, backed by durable MongoDB Atlas state.**

Anchor helps agent systems distinguish an unsupported assertion from one that can be traced to a declared source corpus. It connects a Pi extension to a persistent grounding service that retrieves relevant evidence, evaluates selected claims, and records the result with its provenance for reuse and inspection.

This is more than a demo integration: Anchor is a foundation for building agent workflows that can verify important claims without putting every verification request directly on the agent's critical path.

## What Anchor does

Anchor has two cooperating components:

- **Pi integration:** observes completed assistant messages when grounding is enabled, submits verification work asynchronously, and renders results inside Pi. It also exposes explicit `/jev` commands and a `jev_evaluate` tool for direct TypeSafe Jev requests.
- **Grounding service:** a Python/FastAPI service that retrieves evidence from a declared MongoDB Atlas corpus, verifies selected claims with an LLM or Jev, and persists the judgment, evidence IDs, corpus revision, verifier, cache status, usage, and timings.

The service supports both individual and concurrent verification:

- `POST /verify` verifies one claim.
- `POST /verify/batch` verifies a bounded batch with per-claim results or errors.
- `GET /runs/{run_id}` returns the current run state, provenance, counts, and running support/contradiction/insufficient-evidence scores.
- `GET /runs/{run_id}/claims/{claim_id}/evidence` returns the persisted source chunks used for a judgment.

Exact judgments are reusable, while corpus revisions and verifier configuration remain part of the provenance. This makes the system useful for long-running agent sessions where evidence should remain inspectable rather than disappearing with a single model response.

## Architecture

```text
Pi agent
  │
  ├─ completed assistant message
  │
  └─ asynchronous grounding request
        │
        ▼
  FastAPI grounding service
        │
        ├─ retrieve scoped evidence from MongoDB Atlas
        ├─ verify the selected claim with an LLM or Jev
        ├─ persist the judgment and provenance
        └─ update the run's grounding scores
```

The caller owns claim selection and context. Anchor owns corpus-scoped retrieval, evidence-support judgments, exact caching, persistence, and score tracking. Verification requests can be scheduled in the background so the main agent can continue working; completed state survives in Atlas, while in-flight tasks are intentionally not a durable job queue.

## Scope and guarantees

Anchor is designed to make evidence and uncertainty explicit, not to claim more than the system can establish.

- A `SUPPORTED` result means the verifier found supporting evidence in the declared corpus; it is not a universal proof of truth.
- `INSUFFICIENT` can mean that the scoped corpus did not provide enough evidence. Retrieval coverage and verdict quality are tracked separately.
- Jev distributions and running scores are retained for analysis, but they are not guaranteed calibrated probabilities and should not be used as automatic action-safety thresholds.
- Anchor does not currently extract every claim, infer risk, block agent actions, rewrite responses, or provide a durable job queue.
- Context helps disambiguate a claim but is not trusted evidence unless the relevant material has been ingested into the source corpus.

## Setup

The Pi extension requires Node.js 22.19+ and a production Pi install:

```sh
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.87.1
npm ci --ignore-scripts
npm run link
pi install npm:pi-subagents@0.71.0
```

`npm run link` registers this checkout's absolute path in Pi's personal settings. Pi reads the TypeScript extension directly from the checkout, so use `/reload` or restart Pi after editing.

The grounding service has its own Python environment and Atlas configuration. See [`grounding-service/README.md`](grounding-service/README.md) for installation, corpus ingestion, environment variables, benchmark commands, and the FastAPI service. See [`grounding-service/INTEGRATION.md`](grounding-service/INTEGRATION.md) for the upstream contract and background-calling pattern.

## Run with Pi

```sh
npm run dev
```

Inside Pi, the explicit Jev commands are:

```text
/jev status
/jev models
/jev test
/reload
```

Grounding is enabled with `PI_GRAIL_GROUNDING_ENABLED=true` once the Python service is configured and running. Jev authentication is separate from the generative model used by Pi:

```sh
npm run jev:auth
npm run jev:models
npm run jev:test
```

Credentials are stored outside the repository when using the default key-file flow. Do not place API keys in chat, source files, or command arguments.

For a short end-to-end walkthrough, see [`DEMO.md`](DEMO.md). It demonstrates the integration; the grounding service and API described above are the core application.

## Verify and iterate

```sh
npm run typecheck
npm test
npm run test:pi
npm run pi:status
```

The local Pi tests use fixtures and do not claim to measure model quality. `npm run jev:test` and `npm run test:pi:live` make real TypeSafe requests and may consume API credits.

## Repository layout

- `extensions/` — Pi extension entry point and command/tool registration.
- `src/` — TypeScript integration, Jev client, and grounding bridge.
- `grounding-service/` — FastAPI verification service, Atlas persistence, ingestion, and benchmarks.
- `DEMO.md` — concise end-to-end walkthrough.
- `.pi/` — Pi project resources, including the optional reviewer persona.

## Development references

- [Pi extensions](https://pi.dev/docs/latest/extensions)
- [Local Pi packages](https://pi.dev/docs/latest/packages)
- [pi-subagents integration](https://github.com/nicobailon/pi-subagents/blob/main/docs/extension-api.md)
- [TypeSafe SDK](https://docs.typesafe.ai/sdk/javascript)
- [TypeSafe skill](https://github.com/typesafe-ai/skills/tree/main/skills/typesafe-ai)
- [Pi extension development skill](https://github.com/Dwsy/pi-extensions-skill)
