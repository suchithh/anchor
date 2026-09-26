from src.models import LABELS, Judgment
from src.providers import post, usage
from src.verification.common import CRITERIA, INSTRUCTIONS, PROMPT_VERSION, state


class JevVerifier:
    def __init__(self, client, settings):
        self.client, self.s = client, settings
        self.identity = f"jev:{settings.jev_model}:{PROMPT_VERSION}"

    async def judge(self, request, chunks):
        data = await post(
            self.client,
            "https://openrouter.ai/api/alpha/decisions",
            self.s.openrouter_api_key.get_secret_value(),
            {
                "model": self.s.jev_model,
                "state": state(request, chunks),
                "questions": {
                    "grounding": {"type": "choice", "criteria": CRITERIA, "instructions": INSTRUCTIONS}
                },
            },
        )
        answer = data["answers"]["grounding"]
        if answer.get("type") != "choice" or set(answer["probabilities"]) != set(LABELS):
            raise ValueError("Unexpected Jev CHOICE response")
        p = answer["probabilities"]
        result = Judgment(
            verdict=answer["choice"],
            p_supported=p["SUPPORTED"],
            p_contradicted=p["CONTRADICTED"],
            p_insufficient=p["INSUFFICIENT"],
        )
        return result, usage(data, "openrouter", "jev", self.s.jev_model)
