from __future__ import annotations

from anthropic import Anthropic

from leadcompass.config import ZAI_API_KEY

ZAI_BASE_URL = "https://api.z.ai/api/anthropic"
GLM_MODEL = "glm-5.3-flash"


class GLMBackend:
    name = "GLM"

    def __init__(self, api_key: str = ZAI_API_KEY, model: str = GLM_MODEL):
        self._client = Anthropic(api_key=api_key, base_url=ZAI_BASE_URL)
        self._model = model

    def generate(self, system: str, user: str) -> str:
        # GLM flash is a thinking model: its internal reasoning trace can consume
        # thousands of tokens before the visible reply. 16 000 gives enough headroom.
        response = self._client.messages.create(
            model=self._model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
