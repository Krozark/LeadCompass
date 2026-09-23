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
        # GLM flash models are thinking models: the reasoning trace precedes the
        # visible reply, so only text blocks are returned to the caller.
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
