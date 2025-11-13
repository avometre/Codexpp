"""Data models for Codexpp CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class CommandParameter:
    """Metadata describing a configurable placeholder in a command prompt."""

    name: str
    description: str
    required: bool = False
    default: Optional[str] = None
    placeholder: Optional[str] = None


@dataclass(slots=True)
class CommandDefinition:
    """A slash command template."""

    identifier: str
    title: str
    summary: str
    prompt: str
    parameters: Dict[str, CommandParameter] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class PersonaDefinition:
    """Behavioral guidance for a Codex collaborator persona."""

    identifier: str
    label: str
    summary: str
    directives: List[str]


@dataclass(slots=True)
class McpServerDefinition:
    """Model Context Protocol server profile."""

    identifier: str
    label: str
    summary: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    cwd: Optional[str] = None
    auto_start: bool = True
    tags: List[str] = field(default_factory=list)

