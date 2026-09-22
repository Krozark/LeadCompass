from __future__ import annotations

import json
import subprocess

from leadcompass.config import CLAUDE_CLI_PATH


class ClaudeCLIError(RuntimeError):
    pass


class ClaudeCLIBackend:
    name = "Claude"

    def __init__(self, cli_path: str = CLAUDE_CLI_PATH, max_turns: int = 6, timeout: int = 180):
        self._cli_path = cli_path
        self._max_turns = max_turns
        self._timeout = timeout

    def generate(self, system: str, user: str) -> str:
        prompt = f"{system}\n\n{user}"
        command = [
            self._cli_path,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            str(self._max_turns),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=self._timeout, check=True
            )
        except subprocess.CalledProcessError as exc:
            raise ClaudeCLIError(exc.stderr or str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCLIError(f"Claude CLI timed out after {self._timeout}s") from exc

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCLIError(f"Unexpected Claude CLI output: {result.stdout[:500]}") from exc

        if payload.get("is_error"):
            raise ClaudeCLIError(payload.get("result", "Claude CLI reported an error"))

        return payload.get("result", "")
