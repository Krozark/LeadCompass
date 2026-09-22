from __future__ import annotations

from typing import Protocol


class LLMBackend(Protocol):
    name: str

    def generate(self, system: str, user: str) -> str: ...
