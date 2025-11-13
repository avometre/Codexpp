"""Load command, persona, and MCP definitions from TOML files."""

from __future__ import annotations

import itertools
import tomllib
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import models
from . import config as cfg

RESOURCE_COMMANDS = resources.files("codexpp.resources") / "commands"
RESOURCE_PERSONAS = resources.files("codexpp.resources") / "personas"
RESOURCE_MCP = resources.files("codexpp.resources") / "mcp"
RESOURCE_PROMPTS = resources.files("codexpp.resources.prompts") / "default"


def _iter_toml_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".toml")


def _load_toml_file(path: Path) -> Dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_from_resource(package_path: resources.abc.Traversable) -> List[Dict]:
    items: List[Dict] = []
    for file in package_path.iterdir():
        if not file.name.endswith(".toml"):
            continue
        with file.open("rb") as handle:
            items.append(tomllib.load(handle))
    return items


def _load_prompt_template(command_id: str) -> Optional[str]:
    filename = command_id.replace(":", "-") + ".md"
    try:
        template = RESOURCE_PROMPTS / filename
    except ModuleNotFoundError:
        return None

    if not template.exists():
        return None

    text = template.read_text(encoding="utf-8")
    return _strip_front_matter(text)


def _strip_front_matter(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return normalized.strip("\n")

    closing_index = normalized.find("\n---", 4)
    if closing_index == -1:
        return normalized.strip("\n")

    remainder = normalized[closing_index + len("\n---") :]
    if remainder.startswith("\n"):
        remainder = remainder[1:]
    return remainder.strip("\n")


def _apply_parameter_placeholders(
    text: str, parameters: Dict[str, models.CommandParameter]
) -> str:
    result = text
    for name, param in parameters.items():
        token = (param.placeholder or name.upper()).strip()
        if not token:
            continue
        result = result.replace(f"${token}", f"{{{{{name}}}}}")
    return result


def load_commands(start: Path | None = None) -> Dict[str, models.CommandDefinition]:
    commands: Dict[str, models.CommandDefinition] = {}

    sources = itertools.chain(
        (_load_toml_file(path) for directory in cfg.candidate_command_dirs(start) for path in _iter_toml_files(directory)),
        _load_from_resource(RESOURCE_COMMANDS),
    )

    for doc in sources:
        for entry in doc.get("commands", []):
            identifier = entry["id"]
            params = {
                name: models.CommandParameter(
                    name=name,
                    description=data.get("description", ""),
                    required=data.get("required", False),
                    default=data.get("default"),
                )
                for name, data in entry.get("inputs", {}).items()
            }
            command = models.CommandDefinition(
                identifier=identifier,
                title=entry.get("title", identifier),
                summary=entry.get("summary", ""),
                prompt=entry["prompt"],
                parameters=params,
                tags=list(entry.get("tags", [])),
            )
            commands[identifier] = command
    for identifier, command in commands.items():
        template = _load_prompt_template(identifier)
        if template:
            command.prompt = _apply_parameter_placeholders(template, command.parameters)
    return commands


def load_personas(start: Path | None = None) -> Dict[str, models.PersonaDefinition]:
    personas: Dict[str, models.PersonaDefinition] = {}

    sources = itertools.chain(
        (_load_toml_file(path) for directory in cfg.candidate_persona_dirs(start) for path in _iter_toml_files(directory)),
        _load_from_resource(RESOURCE_PERSONAS),
    )

    for doc in sources:
        for entry in doc.get("personas", []):
            identifier = entry["id"]
            persona = models.PersonaDefinition(
                identifier=identifier,
                label=entry.get("label", identifier.title()),
                summary=entry.get("summary", ""),
                directives=list(entry.get("directives", [])),
            )
            personas[identifier] = persona
    return personas


def load_mcp_servers(start: Path | None = None) -> Dict[str, models.McpServerDefinition]:
    servers: Dict[str, models.McpServerDefinition] = {}

    sources = itertools.chain(
        (
            _load_toml_file(path)
            for directory in cfg.candidate_mcp_dirs(start)
            for path in _iter_toml_files(directory)
        ),
        _load_from_resource(RESOURCE_MCP),
    )

    for doc in sources:
        for entry in doc.get("servers", []):
            identifier = entry["id"]
            server = models.McpServerDefinition(
                identifier=identifier,
                label=entry.get("label", identifier),
                summary=entry.get("summary", ""),
                command=entry["command"],
                args=list(entry.get("args", [])),
                env=dict(entry.get("env", {})),
                transport=entry.get("transport", "stdio"),
                cwd=entry.get("cwd"),
                auto_start=entry.get("auto_start", True),
                tags=list(entry.get("tags", [])),
            )
            servers[identifier] = server
    return servers
