import json

from src.models import LABELS, Judgment
from src.providers import post, usage
from src.verification.common import CRITERIA, INSTRUCTIONS, PROMPT_VERSION, state


class ContextBudgetExceeded(ValueError):
    pass


class LLMVerifier:
    def __init__(self, client, settings):
        self.client, self.s = client, settings
        self.identity = (
            f"llm:{settings.baseline_model}:reasoning={settings.baseline_reasoning}:{PROMPT_VERSION}"
        )

    async def _call(self, states):
        ids = [s["claim_id"] for s in states]
        schema = {
            "type": "object",
            "properties": {
                "judgments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim_id": {"type": "string"},
                            "verdict": {"type": "string", "enum": LABELS},
                        },
                        "required": ["claim_id", "verdict"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["judgments"],
            "additionalProperties": False,
        }
        data = await post(
            self.client,
            "https://openrouter.ai/api/v1/chat/completions",
            self.s.openrouter_api_key.get_secret_value(),
            {
                "model": self.s.baseline_model,
                "temperature": 0,
                "max_tokens": min(8192, max(512, len(states) * 128)),
                "reasoning": {"enabled": self.s.baseline_reasoning},
                "messages": [
                    {
                        "role": "system",
                        "content": INSTRUCTIONS
                        + " Return exactly one judgment for each claim_id; copy IDs unchanged. "
                        "shared_evidence_for_all_claims, if present, applies to every claim.\n"
                        + json.dumps(CRITERIA),
                    },
                    {"role": "user", "content": json.dumps(states, ensure_ascii=False)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "grounding", "strict": True, "schema": schema},
                },
                "provider": {"require_parameters": True},
            },
        )
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("LLM output incomplete or refused")
        rows = json.loads(choice["message"]["content"])["judgments"]
        if len(rows) != len(ids) or sorted(r["claim_id"] for r in rows) != sorted(ids):
            raise ValueError("LLM must return each requested claim_id exactly once")
        result = {r["claim_id"]: Judgment.hard(r["verdict"]) for r in rows}
        return result, usage(data, "openrouter", "llm", self.s.baseline_model)

    async def judge(self, request, chunks):
        results, u = await self._call([{"claim_id": request.claim_id, **state(request, chunks)}])
        return results[request.claim_id], u

    async def posthoc(self, requests, chunks):
        # Send evidence once, not once per claim. Same structured response contract.
        states = [
            {"claim_id": r.claim_id, "claim": r.claim, "context": r.context, "scope": r.scope}
            for r in requests
        ]
        states[0]["shared_evidence_for_all_claims"] = state(requests[0], chunks)["evidence"]
        size = len(json.dumps(states, ensure_ascii=False).encode("utf-8"))
        if size > self.s.posthoc_max_input_bytes:
            raise ContextBudgetExceeded(
                f"Input {size} bytes exceeds POSTHOC_MAX_INPUT_BYTES="
                f"{self.s.posthoc_max_input_bytes}; no silent truncation"
            )
        return await self._call(states)
