"""Configuration helpers for Codexpp."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

APP_DIR_NAME = ".codexpp"
COMMANDS_DIR_NAME = "commands"
PERSONAS_DIR_NAME = "personas"
MCP_DIR_NAME = "mcp"


def resolve_project_root(start: Path | None = None) -> Path:
    """Return the first ancestor containing a `.codexpp` directory, else current path."""
    path = (start or Path.cwd()).resolve()

    for ancestor in [path, *path.parents]:
        candidate = ancestor / APP_DIR_NAME
        if candidate.exists():
            return ancestor
    return path


def project_config_dir(start: Path | None = None) -> Path:
    """Return the `.codexpp` directory for the project if present, else default location under start."""
    root = resolve_project_root(start)
    return (root / APP_DIR_NAME).resolve()


def user_config_dir() -> Path:
    """Return the per-user Codexpp directory."""
    return Path.home() / APP_DIR_NAME


def candidate_command_dirs(start: Path | None = None) -> Iterable[Path]:
    """Yield command directories in search order (project first, then user)."""
    project_dir = project_config_dir(start)
    yield project_dir / COMMANDS_DIR_NAME
    yield user_config_dir() / COMMANDS_DIR_NAME


def candidate_persona_dirs(start: Path | None = None) -> Iterable[Path]:
    """Yield persona directories in search order (project first, then user)."""
    project_dir = project_config_dir(start)
    yield project_dir / PERSONAS_DIR_NAME
    yield user_config_dir() / PERSONAS_DIR_NAME


def candidate_mcp_dirs(start: Path | None = None) -> Iterable[Path]:
    """Yield MCP profile directories in search order (project first, then user)."""
    project_dir = project_config_dir(start)
    yield project_dir / MCP_DIR_NAME
    yield user_config_dir() / MCP_DIR_NAME


def bootstrap_targets(base: Path) -> Tuple[Path, Path, Path]:
    """Return directories that should be created under `base`."""
    commands_dir = base / COMMANDS_DIR_NAME
    personas_dir = base / PERSONAS_DIR_NAME
    mcp_dir = base / MCP_DIR_NAME
    return commands_dir, personas_dir, mcp_dir

