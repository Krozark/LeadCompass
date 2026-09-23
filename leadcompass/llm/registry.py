from __future__ import annotations

import shutil

from leadcompass.config import load_llm_backends, load_llm_choice
from leadcompass.llm.claude_cli import ClaudeCLIBackend


def configured_backends() -> dict[str, str]:
    """Modèles enregistrés dont le binaire est détecté : nom -> chemin du CLI."""
    return {
        backend.name: backend.cli_path
        for backend in load_llm_backends()
        if shutil.which(backend.cli_path) is not None
    }


def default_backend_name() -> str:
    """Choix enregistré s'il reste disponible, sinon premier modèle disponible."""
    backends = configured_backends()
    saved = load_llm_choice()
    if saved in backends:
        return saved
    return next(iter(backends), "")


def get_backend(name: str, **kwargs) -> ClaudeCLIBackend:
    """Backend prêt à l'emploi pour un modèle enregistré et détecté.

    kwargs (max_turns, timeout…) est transmis au backend, utile pour les tâches
    longues comme la découverte web.
    """
    cli_path = configured_backends().get(name)
    if cli_path is None:
        raise KeyError(f"LLM backend not available: {name}")
    return ClaudeCLIBackend(cli_path=cli_path, name=name, **kwargs)
