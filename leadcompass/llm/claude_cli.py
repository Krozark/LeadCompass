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
        return self._run(system, user, self._max_turns, self._timeout, extra_args=[])

    def explore(
        self,
        system: str,
        user: str,
        directories: list[str],
        max_turns: int = 40,
        timeout: int = 900,
    ) -> str:
        """Let Claude read files under `directories` to answer, with no write/exec access.

        `--restricted` drops Bash/code-execution/WebFetch and confines file tools to
        the working directory plus `--add-dir` paths; `--allowedTools` additionally
        whitelists only the read-only tools, so nothing outside those directories can
        be touched and nothing inside them can be modified.
        """
        add_dir_args = []
        for directory in directories:
            add_dir_args += ["--add-dir", directory]

        extra_args = [
            "--restricted",
            "--allowedTools",
            "Read Glob Grep",
            "--permission-prompts",
            "none",
            *add_dir_args,
        ]
        return self._run(system, user, max_turns, timeout, extra_args)

    def _run(
        self, system: str, user: str, max_turns: int, timeout: int, extra_args: list[str]
    ) -> str:
        prompt = f"{system}\n\n{user}"
        command = [
            self._cli_path,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            str(max_turns),
            *extra_args,
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=True
            )
        except subprocess.CalledProcessError as exc:
            raise ClaudeCLIError(exc.stderr or str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCLIError(f"Claude CLI timed out after {timeout}s") from exc

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCLIError(f"Unexpected Claude CLI output: {result.stdout[:500]}") from exc

        if payload.get("is_error"):
            raise ClaudeCLIError(payload.get("result", "Claude CLI reported an error"))

        return payload.get("result", "")
