"""Command-line interface for Codexpp."""

from __future__ import annotations

import argparse
import difflib
import functools
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import config as cfg
from . import loader
from . import __version__ as CODEXPP_VERSION
from .models import (
    CommandDefinition,
    CommandParameter,
    McpServerDefinition,
    PersonaDefinition,
)

PLACEHOLDER_PATTERN = re.compile(r"(?<!\\)\{\{\s*([a-zA-Z0-9_\-]+)\s*\}\}")
PROMPT_TEMPLATE_PACKAGES = [
    "codexpp.resources.prompts.default",
]

_DEFAULT_CODEX_NAMES = ["codex.exe", "codex.cmd", "codex.bat", "codex"] if os.name == "nt" else ["codex"]


def _prepend_path(directory: Path) -> None:
    directory_str = str(directory)
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    if directory_str in parts:
        return
    os.environ["PATH"] = f"{directory_str}{os.pathsep}{current}" if current else directory_str


@functools.lru_cache(maxsize=1)
def _npm_global_bin_dir() -> Optional[Path]:
    prefix_env = os.environ.get("NPM_CONFIG_PREFIX")
    if prefix_env:
        path = Path(prefix_env).expanduser()
        return (path / "bin") if path else None

    npm_bin = shutil.which("npm")
    if not npm_bin:
        return None

    try:
        result = subprocess.run(
            ["npm", "config", "get", "prefix"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    prefix = result.stdout.strip()
    if not prefix or prefix == "undefined":
        return None
    return (Path(prefix).expanduser() / "bin").resolve()


def _known_codex_dirs() -> List[Path]:
    home = Path.home()
    candidates: List[Path] = [
        home / ".npm-global/bin",
        home / ".local/bin",
        home / ".local/share/pnpm",
        home / ".pnpm/bin",
        home / ".pnpm-global/bin",
        home / ".pnpm-global/node_modules/.bin",
        home / ".pnpm-global/5/node_modules/.bin",
        home / ".volta/bin",
        home / ".asdf/shims",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]

    pnpm_home = os.environ.get("PNPM_HOME")
    if pnpm_home:
        candidates.append(Path(pnpm_home).expanduser())

    volta_home = os.environ.get("VOLTA_HOME")
    if volta_home:
        candidates.append((Path(volta_home) / "bin").expanduser())

    npm_dir = _npm_global_bin_dir()
    if npm_dir:
        candidates.append(npm_dir)

    return candidates


@functools.lru_cache(maxsize=1)
def _bundled_command_files() -> List[str]:
    try:
        base = resources.files("codexpp.resources.commands")
    except ModuleNotFoundError:
        return []
    return sorted(item.name for item in base.iterdir() if item.name.endswith(".toml"))


def _purge_bundled_command_files(project: Path) -> List[Path]:
    filenames = _bundled_command_files()
    if not filenames:
        return []

    removed: List[Path] = []
    locations = [
        cfg.project_config_dir(project) / cfg.COMMANDS_DIR_NAME,
        cfg.user_config_dir() / cfg.COMMANDS_DIR_NAME,
    ]

    for directory in locations:
        if not directory.exists():
            continue
        for name in filenames:
            candidate = directory / name
            if candidate.exists():
                candidate.unlink()
                removed.append(candidate)
    if removed:
        print("[codexpp] Removed legacy bundled command file(s):")
        for path in removed:
            print(f"  - {path}")
    return removed


def _resolve_codex_binary(preferred: str) -> Tuple[Optional[str], Optional[str]]:
    candidate_path = Path(preferred).expanduser()
    if candidate_path.is_file():
        return str(candidate_path), None

    resolved = shutil.which(preferred)
    if resolved:
        return resolved, None

    for directory in _known_codex_dirs():
        names = _DEFAULT_CODEX_NAMES if preferred == "codex" else [preferred]
        for name in names:
            target = (directory / name).expanduser()
            if target.is_file() and os.access(target, os.X_OK):
                _prepend_path(target.parent)
                message = f"[codexpp] Codex CLI auto-detected: {target}"
                return str(target), message

    return None, None

def _write_text(path: str, content: str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"[codexpp] File created: {target}")
    return target


def main(argv: List[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return

    try:
        args.func(args)
    except CodexppError as exc:
        print(f"[codexpp] {exc}", file=sys.stderr)
        sys.exit(1)


class CodexppError(RuntimeError):
    """Raised when the CLI encounters a recoverable error."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codexpp",
        description="Codex CLI enhancement framework",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CODEXPP_VERSION}",
        help="Show codexpp version and exit.",
    )
    parser.add_argument(
        "-p",
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Project directory to operate on (default: current directory).",
    )

    subparsers = parser.add_subparsers(dest="command")

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Install sample command and persona sets into the project directory.",
    )
    bootstrap_parser.add_argument(
        "--user",
        action="store_true",
        help="Perform a user-level installation (HOME/.codexpp).",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files (use with caution).",
    )
    bootstrap_parser.set_defaults(func=_handle_bootstrap)

    commands_parser = subparsers.add_parser("commands", help="Command management.")
    commands_sub = commands_parser.add_subparsers(dest="subcommand")

    commands_list = commands_sub.add_parser("list", help="List all available commands.")
    commands_list.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed command parameters and descriptions.",
    )
    commands_list.set_defaults(func=_handle_commands_list)

    commands_show = commands_sub.add_parser("show", help="Display command details.")
    commands_show.add_argument("identifier", help="Command identifier (e.g. cx:analyze).")
    commands_show.set_defaults(func=_handle_commands_show)

    commands_render = commands_sub.add_parser("render", help="Render a command prompt.")
    commands_render.add_argument("identifier", help="Command identifier.")
    commands_render.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Parameter values (can be provided multiple times).",
    )
    commands_render.set_defaults(func=_handle_commands_render)

    commands_run = commands_sub.add_parser("run", help="Execute a command and optionally send it to Codex.")
    commands_run.add_argument("identifier", help="Command identifier.")
    commands_run.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Parameter values (can be provided multiple times).",
    )
    commands_run.add_argument(
        "--persona",
        dest="personas",
        action="append",
        default=[],
        metavar="ID",
        help="Persona identifier (can be provided multiple times).",
    )
    commands_run.add_argument(
        "--exec",
        dest="invoke_codex",
        action="store_true",
        help="Run the prompt immediately by invoking `codex exec`.",
    )
    commands_run.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary name or path (default: codex).",
    )
    commands_run.add_argument(
        "--print-only",
        dest="print_only",
        action="store_true",
        help="Print the prompt output without calling Codex (default behavior).",
    )
    commands_run.add_argument(
        "--codex-arg",
        dest="codex_args",
        action="append",
        default=[],
        metavar="ARG",
        help="Additional argument to pass to Codex CLI (e.g. --codex-arg=--skip-git-repo-check).",
    )
    commands_run.add_argument(
        "--summary",
        action="store_true",
        help="Print a summary of command parameters and personas before the prompt.",
    )
    commands_run.add_argument(
        "--summary-only",
        action="store_true",
        help="Show only the summary without rendering the prompt or calling Codex.",
    )
    commands_run.add_argument(
        "--summary-format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Summary output format (default: text).",
    )
    commands_run.add_argument(
        "--save-summary",
        metavar="PATH",
        help="Write the summary output to a file.",
    )
    commands_run.add_argument(
        "--save-prompt",
        metavar="PATH",
        help="Write the final prompt text to a file.",
    )
    commands_run.set_defaults(func=_handle_commands_run)

    commands_packs = commands_sub.add_parser("packs", help="Manage command packs.")
    packs_sub = commands_packs.add_subparsers(dest="pack_subcommand")

    packs_list = packs_sub.add_parser("list", help="List built-in command packs.")
    packs_list.set_defaults(func=_handle_commands_packs_list)

    packs_install = packs_sub.add_parser("install", help="Install a command pack into the project.")
    packs_install.add_argument("name", help="Pack name (e.g. extended).")
    packs_install.add_argument(
        "--user",
        action="store_true",
        help="Install the pack into the user directory (HOME/.codexpp).",
    )
    packs_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing pack file.",
    )
    packs_install.set_defaults(func=_handle_commands_packs_install)

    personas_parser = subparsers.add_parser("personas", help="Manage personas.")
    personas_sub = personas_parser.add_subparsers(dest="subcommand")

    personas_list = personas_sub.add_parser("list", help="List all personas.")
    personas_list.set_defaults(func=_handle_personas_list)

    personas_show = personas_sub.add_parser("show", help="Display persona details.")
    personas_show.add_argument("identifier", help="Persona identifier (e.g. system-architect).")
    personas_show.set_defaults(func=_handle_personas_show)

    personas_export = personas_sub.add_parser("export", help="Export persona directives as markdown.")
    personas_export.add_argument(
        "--output",
        default="AGENTS.md",
        help="Output file path (default: AGENTS.md). Use '-' to write to stdout.",
    )
    personas_export.add_argument(
        "--persona",
        dest="personas",
        action="append",
        default=[],
        metavar="ID",
        help="Include only the specified personas (can be provided multiple times).",
    )
    personas_export.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output if it already exists.",
    )
    personas_export.set_defaults(func=_handle_personas_export)

    personas_sync = personas_sub.add_parser(
        "sync",
        help="Synchronise persona directives with the project AGENTS.md file and Codex memory.",
    )
    personas_sync.add_argument(
        "--output",
        default="AGENTS.md",
        help="File path to write within the project (default: AGENTS.md). Use '-' to skip writing.",
    )
    personas_sync.add_argument(
        "--codex-output",
        default="~/.codex/AGENTS.md",
        help="Target path inside the Codex memory directory (default: ~/.codex/AGENTS.md). Use '-' to skip.",
    )
    personas_sync.add_argument(
        "--persona",
        dest="personas",
        action="append",
        default=[],
        metavar="ID",
        help="Include only the specified personas (can be provided multiple times).",
    )
    personas_sync.add_argument(
        "--force",
        action="store_true",
        help="Overwrite outputs if they already exist.",
    )
    personas_sync.add_argument(
        "--show-diff",
        action="store_true",
        help="Show a diff summary when existing files change.",
    )
    personas_sync.add_argument(
        "--diff-color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colour mode for diff output (default: auto).",
    )
    personas_sync.set_defaults(func=_handle_personas_sync)

    version_parser = subparsers.add_parser("version", help="Display codexpp version details.")
    version_parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary name or path to probe (default: codex).",
    )
    version_parser.add_argument(
        "--json",
        action="store_true",
        help="Output version details as JSON.",
    )
    version_parser.set_defaults(func=_handle_version)

    codex_parser = subparsers.add_parser("codex", help="Codex CLI integration utilities.")
    codex_sub = codex_parser.add_subparsers(dest="subcommand")

    codex_status = codex_sub.add_parser("status", help="Show Codex CLI installation status.")
    codex_status.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary name or path (default: codex).",
    )
    codex_status.add_argument(
        "--codex-agents",
        default="~/.codex/AGENTS.md",
        help="Location of the Codex memory file (default: ~/.codex/AGENTS.md).",
    )
    codex_status.set_defaults(func=_handle_codex_status)

    codex_setup = codex_sub.add_parser("setup", help="Prepare persona and memory files for Codex CLI.")
    codex_setup.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary name or path (default: codex).",
    )
    codex_setup.add_argument(
        "--output",
        default="AGENTS.md",
        help="Persona file to write inside the project (default: AGENTS.md).",
    )
    codex_setup.add_argument(
        "--codex-agents",
        default="~/.codex/AGENTS.md",
        help="Target Codex memory file (default: ~/.codex/AGENTS.md).",
    )
    codex_setup.add_argument(
        "--persona",
        dest="personas",
        action="append",
        default=[],
        metavar="ID",
        help="Include only the specified personas (can be provided multiple times).",
    )
    codex_setup.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs.",
    )
    codex_setup.add_argument(
        "--show-diff",
        action="store_true",
        help="Show a diff when files change.",
    )
    codex_setup.add_argument(
        "--diff-color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colour mode for diff output (default: auto).",
    )
    codex_setup.set_defaults(func=_handle_codex_setup)

    codex_install = codex_sub.add_parser(
        "install",
        help="Add slash commands to the Codex config file.",
    )
    codex_install.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary name or path (default: codex).",
    )
    codex_install.add_argument(
        "--config",
        default="~/.codex/config.toml",
        help="Codex config file to update (default: ~/.codex/config.toml).",
    )
    codex_install.add_argument(
        "--include-pack",
        action="append",
        default=None,
        metavar="NAME",
        help="Include the specified command pack (default: all bundled packs).",
    )
    codex_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing slash command block.",
    )
    codex_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview config changes without writing files.",
    )
    codex_install.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup of the config file before writing.",
    )
    codex_install.add_argument(
        "--backup-path",
        default=None,
        metavar="PATH",
        help="Custom path for the config backup (default: <config>.bak).",
    )
    codex_install.set_defaults(func=_handle_codex_install)

    codex_uninstall = codex_sub.add_parser(
        "uninstall",
        help="Remove Codexpp slash commands, prompts, and MCP entries from Codex CLI.",
    )
    codex_uninstall.add_argument(
        "--config",
        default="~/.codex/config.toml",
        help="Codex config file to clean (default: ~/.codex/config.toml).",
    )
    codex_uninstall.add_argument(
        "--prompts-dir",
        default="~/.codex/prompts",
        help="Directory containing Codex prompt files (default: ~/.codex/prompts).",
    )
    codex_uninstall.add_argument(
        "--mcp-dir",
        default="~/.codex/mcp",
        help="Directory containing Codex MCP profiles (default: ~/.codex/mcp).",
    )
    codex_uninstall.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which files would change without modifying anything.",
    )
    codex_uninstall.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup of the config file before cleaning it.",
    )
    codex_uninstall.add_argument(
        "--backup-path",
        default=None,
        metavar="PATH",
        help="Custom path for the config backup (default: <config>.bak).",
    )
    codex_uninstall.set_defaults(func=_handle_codex_uninstall)

    codex_init = codex_sub.add_parser("init", help="Perform a full Codex CLI setup.")
    codex_init.add_argument(
        "--profile",
        choices=["minimal", "full"],
        default="full",
        help="Setup profile (full installs bootstrap, personas, and command packs).",
    )
    codex_init.add_argument(
        "--include-pack",
        action="append",
        default=[],
        metavar="NAME",
        help="Include additional command packs (e.g. ops).",
    )
    codex_init.add_argument(
        "--include-mcp",
        action="append",
        default=[],
        metavar="NAME",
        help="Include additional MCP packs (e.g. default).",
    )
    codex_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    codex_init.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Skip the project bootstrap step.",
    )
    codex_init.set_defaults(func=_handle_codex_init)

    mcp_parser = subparsers.add_parser(
        "mcp",
        help="Manage Model Context Protocol server profiles.",
    )
    mcp_sub = mcp_parser.add_subparsers(dest="subcommand")

    mcp_list = mcp_sub.add_parser(
        "list",
        help="List installed MCP profiles.",
    )
    mcp_list.add_argument(
        "--verbose",
        action="store_true",
        help="Show server commands, arguments, and environment variables.",
    )
    mcp_list.set_defaults(func=_handle_mcp_list)

    mcp_setup = mcp_sub.add_parser(
        "setup",
        help="Synchronise MCP profiles into the directory used by Codex CLI.",
    )
    mcp_setup.add_argument(
        "--codex-dir",
        default="~/.codex/mcp",
        help="Target directory for the generated profiles (default: ~/.codex/mcp).",
    )
    mcp_setup.add_argument(
        "--format",
        choices=["json", "toml", "both"],
        default="json",
        help="Output format (default: json).",
    )
    mcp_setup.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    mcp_setup.add_argument(
        "--show-diff",
        action="store_true",
        help="Show a diff when files are updated.",
    )
    mcp_setup.add_argument(
        "--diff-color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colour mode for diff output (default: auto).",
    )
    mcp_setup.set_defaults(func=_handle_mcp_setup)

    mcp_packs = mcp_sub.add_parser(
        "packs",
        help="Manage bundled MCP packs.",
    )
    mcp_packs_sub = mcp_packs.add_subparsers(dest="pack_subcommand")

    mcp_packs_list = mcp_packs_sub.add_parser(
        "list",
        help="List available MCP packs.",
    )
    mcp_packs_list.set_defaults(func=_handle_mcp_packs_list)

    mcp_packs_install = mcp_packs_sub.add_parser(
        "install",
        help="Install an MCP pack into the project or user directory.",
    )
    mcp_packs_install.add_argument("name", help="Pack name (e.g. default).")
    mcp_packs_install.add_argument(
        "--user",
        action="store_true",
        help="Install the pack into the user directory (HOME/.codexpp).",
    )
    mcp_packs_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing file.",
    )
    mcp_packs_install.set_defaults(func=_handle_mcp_packs_install)

    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch an interactive text UI for exploring commands.",
    )
    tui_parser.add_argument(
        "--exec",
        action="store_true",
        help="Allow sending selected commands to Codex from the menu.",
    )
    tui_parser.set_defaults(func=_handle_tui)

    return parser


def _handle_bootstrap(args: argparse.Namespace) -> None:
    if args.user:
        base_dir = cfg.user_config_dir()
    else:
        base_dir = (args.project / cfg.APP_DIR_NAME).resolve()

    resource_cmd = resources.files("codexpp.resources") / "commands"
    resource_personas = resources.files("codexpp.resources") / "personas"
    resource_mcp = resources.files("codexpp.resources") / "mcp"

    commands_dir, personas_dir, mcp_dir = cfg.bootstrap_targets(base_dir)

    command_ops = _copy_resource_tree(resource_cmd, commands_dir, overwrite=args.force)
    persona_ops = _copy_resource_tree(resource_personas, personas_dir, overwrite=args.force)
    mcp_ops = _copy_resource_tree(resource_mcp, mcp_dir, overwrite=args.force)

    _print_bootstrap_summary(base_dir, command_ops + persona_ops + mcp_ops)


def _copy_resource_tree(
    source: resources.abc.Traversable, destination: Path, overwrite: bool = False
) -> List[Tuple[str, Path]]:
    destination.mkdir(parents=True, exist_ok=True)
    operations: List[Tuple[str, Path]] = []
    for item in source.iterdir():
        if not item.name.endswith(".toml"):
            continue
        target_path = destination / item.name
        if target_path.exists():
            if not overwrite:
                operations.append(("skipped", target_path))
                continue
            status = "overwritten"
        else:
            status = "created"
        with item.open("rb") as handle:
            data = handle.read()
        target_path.write_bytes(data)
        operations.append((status, target_path))

    return operations


def _print_bootstrap_summary(base_dir: Path, operations: List[Tuple[str, Path]]) -> None:
    print(f"[codexpp] Bootstrap complete: {base_dir}")

    if not operations:
        print("  - No new files to copy.")
        return

    groups: Dict[str, List[Path]] = {"created": [], "overwritten": [], "skipped": []}
    for status, path in operations:
        groups.setdefault(status, []).append(path)

    status_labels = {
        "created": "Created files",
        "overwritten": "Overwritten files",
        "skipped": "Skipped files (existing content preserved)",
    }

    for status_key, label in status_labels.items():
        paths = groups.get(status_key, [])
        if not paths:
            continue
        print(f"  - {label}:")
        for path in paths:
            try:
                relative = path.relative_to(base_dir)
            except ValueError:
                relative = path
            print(f"      • {relative}")


def _handle_commands_list(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    if not commands:
        print("No commands found. Try running `codexpp bootstrap`.")
        return

    for command in sorted(commands.values(), key=lambda c: c.identifier):
        tags = f" [{', '.join(command.tags)}]" if command.tags else ""
        print(f"- {command.identifier}{tags}\n  {command.title}")
        if command.summary:
            print(f"  {command.summary}")
        if args.verbose and command.parameters:
            print("  Parameters:")
            for param in command.parameters.values():
                required = "required" if param.required else "optional"
                default = f" (default: {param.default})" if param.default else ""
                print(f"    • {param.name}: {param.description or '-'} — {required}{default}")
        print("")


def _handle_commands_show(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    command = commands.get(args.identifier)
    if command is None:
        raise CodexppError(f"Command not found: {args.identifier}")

    print(f"{command.identifier} — {command.title}")
    if command.tags:
        print(f"Tags: {', '.join(command.tags)}")
    if command.summary:
        print(f"Summary: {command.summary}")
    if command.parameters:
        print("Parameters:")
        for param in command.parameters.values():
            required = "required" if param.required else "optional"
            default = f" (default: {param.default})" if param.default else ""
            print(f"  - {param.name}: {param.description} — {required}{default}")
    print("\nPrompt template:\n")
    print(command.prompt.strip())


def _handle_commands_render(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    command = commands.get(args.identifier)
    if command is None:
        raise CodexppError(f"Command not found: {args.identifier}")

    overrides = _parse_key_value_pairs(args.overrides)
    _validate_override_keys(command, overrides)
    missing = _required_missing(command, overrides)
    if missing:
        raise CodexppError(f"Missing required parameters: {', '.join(missing)}")

    rendered = _render_prompt(command, overrides)
    print(rendered.strip())


def _handle_commands_run(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    command = commands.get(args.identifier)
    if command is None:
        raise CodexppError(f"Command not found: {args.identifier}")

    overrides = _parse_key_value_pairs(args.overrides)
    _validate_override_keys(command, overrides)
    missing = _required_missing(command, overrides)
    if missing:
        raise CodexppError(f"Missing required parameters: {', '.join(missing)}")

    personas = _resolve_personas(args.personas, start=args.project)
    resolved_values = _resolve_parameter_values(command, overrides)

    if args.summary_only:
        args.summary = True

    rendered_prompt = _render_prompt(command, resolved_values)
    final_prompt = _compose_prompt(rendered_prompt, personas)

    summary_text: Optional[str] = None
    if args.summary:
        summary_text = _build_run_summary(
            command,
            resolved_values,
            personas,
            invoke_codex=args.invoke_codex and not args.print_only,
            print_only=args.print_only or not args.invoke_codex,
            summary_format=args.summary_format,
        )
        print(summary_text)
        print("")
        if args.save_summary:
            text_to_write = summary_text if summary_text.endswith("\n") else summary_text + "\n"
            _write_text(args.save_summary, text_to_write)
        if args.summary_only:
            if args.save_prompt:
                _write_text(
                    args.save_prompt,
                    final_prompt.strip() + ("\n" if not final_prompt.endswith("\n") else ""),
                )
            return

    if args.save_prompt:
        _write_text(
            args.save_prompt,
            final_prompt.strip() + ("\n" if not final_prompt.endswith("\n") else ""),
        )

    if args.invoke_codex and not args.print_only:
        _invoke_codex(final_prompt, args.codex_bin, args.codex_args)
    else:
        print(final_prompt.strip())
        if args.invoke_codex and args.print_only:
            print("\n[codexpp] `--print-only` active, Codex was not invoked.")


def _handle_commands_packs_list(args: argparse.Namespace) -> None:
    packs = _available_command_packs()
    if not packs:
        print("No codexpp command packs available. All built-in commands are included by default.")
        return

    installed: set[str] = set()
    for directory in cfg.candidate_command_dirs(args.project):
        if directory.exists():
            installed.update(path.stem for path in directory.glob("*.toml"))

    print("Available command packs:")
    for name in sorted(packs):
        marker = " (installed)" if name in installed else ""
        print(f"- {name}{marker}")


def _handle_commands_packs_install(args: argparse.Namespace) -> None:
    packs = _available_command_packs()
    resource = packs.get(args.name)
    if resource is None:
        raise CodexppError(f"Pack not found: {args.name}")

    if args.user:
        base_dir = cfg.user_config_dir()
    else:
        base_dir = cfg.project_config_dir(args.project)

    target_dir = base_dir / cfg.COMMANDS_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{args.name}.toml"
    if target_path.exists() and not args.force:
        raise CodexppError(
            f"Pack already exists: {target_path}. Use `--force` to overwrite."
        )

    with resource.open("rb") as handle:
        data = handle.read()
    target_path.write_bytes(data)

    location = "user" if args.user else "project"
    print(f"[codexpp] Pack `{args.name}` installed in the {location} directory: {target_path}")


def _parse_key_value_pairs(pairs: Iterable[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise CodexppError(f"Invalid mapping, expected `key=value` format: {item}")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _validate_override_keys(command: CommandDefinition, values: Dict[str, str]) -> None:
    unknown = sorted(key for key in values if key not in command.parameters)
    if unknown:
        raise CodexppError(f"Unknown parameter(s): {', '.join(unknown)}")


def _required_missing(command: CommandDefinition, values: Dict[str, str]) -> List[str]:
    missing: List[str] = []
    for name, param in command.parameters.items():
        candidate = values.get(name) or param.default
        if param.required and not candidate:
            missing.append(name)
    return missing


def _render_prompt(command: CommandDefinition, values: Dict[str, str]) -> str:
    placeholders = set(PLACEHOLDER_PATTERN.findall(command.prompt))
    undefined = sorted(placeholders - set(command.parameters))
    if undefined:
        raise CodexppError(f"Prompt references undefined placeholder(s): {', '.join(undefined)}")

    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        param = command.parameters[name]
        return values.get(name, param.default or "")

    result = PLACEHOLDER_PATTERN.sub(replacement, command.prompt)

    leftover = PLACEHOLDER_PATTERN.search(result)
    if leftover:
        raise CodexppError(
            f"Unresolved placeholder detected in prompt: {leftover.group(0)}"
        )

    return result.replace("\\{{", "{{")


def _resolve_parameter_values(command: CommandDefinition, values: Dict[str, str]) -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    for name, param in command.parameters.items():
        value = values.get(name)
        if value is None:
            value = param.default or ""
        resolved[name] = value
    return resolved


def _build_run_summary(
    command: CommandDefinition,
    resolved_values: Dict[str, str],
    personas: List[PersonaDefinition],
    invoke_codex: bool,
    print_only: bool,
    summary_format: str,
) -> str:
    run_mode = "Codex exec" if invoke_codex else ("stdout" if not print_only else "preview")
    summary = {
        "command": {
            "id": command.identifier,
            "title": command.title,
            "tags": command.tags,
        },
        "parameters": {name: resolved_values.get(name, "") for name in command.parameters},
        "personas": [
            {"id": persona.identifier, "label": persona.label} for persona in personas
        ],
        "run_mode": run_mode,
    }

    if summary_format == "json":
        return json.dumps(summary, ensure_ascii=False, indent=2)

    if summary_format == "markdown":
        lines = [
            "# Command Summary",
            f"## {command.title} (`{command.identifier}`)",
        ]
        if command.tags:
            lines.append(f"_Tags:_ {', '.join(command.tags)}")
        lines.append("")
        lines.append("### Parameters")
        if summary["parameters"]:
            for name, value in summary["parameters"].items():
                rendered_value = value if value else "(empty)"
                lines.append(f"- {name}: {rendered_value}")
        else:
            lines.append("- (No parameters defined)")

        lines.append("")
        lines.append("### Personas")
        if summary["personas"]:
            for persona in summary["personas"]:
                lines.append(f"- {persona['id']}: {persona['label']}")
        else:
            lines.append("- (None selected)")

        lines.append("")
        lines.append(f"**Run mode:** {run_mode}")
        return "\n".join(lines)

    # Default text format
    lines = [
        "== Command Summary ==",
        f"ID: {summary['command']['id']}",
        f"Title: {summary['command']['title']}",
    ]
    if command.tags:
        lines.append(f"Tags: {', '.join(command.tags)}")

    lines.append("\nParameters:")
    if summary["parameters"]:
        for name, value in summary["parameters"].items():
            rendered_value = value if value else "(empty)"
            lines.append(f"  - {name}: {rendered_value}")
    else:
        lines.append("  - (No parameters defined)")

    lines.append("\nPersonas:")
    if summary["personas"]:
        for persona in summary["personas"]:
            lines.append(f"  - {persona['id']}: {persona['label']}")
    else:
        lines.append("  - (None selected)")

    lines.append(f"\nRun mode: {run_mode}")
    return "\n".join(lines)


def _handle_personas_list(args: argparse.Namespace) -> None:
    personas = loader.load_personas(start=args.project)
    if not personas:
        print("No personas found. Try running `codexpp bootstrap`.")
        return

    for persona in sorted(personas.values(), key=lambda p: p.identifier):
        print(f"- {persona.identifier}: {persona.label} — {persona.summary}")


def _handle_personas_show(args: argparse.Namespace) -> None:
    personas = loader.load_personas(start=args.project)
    persona = personas.get(args.identifier)
    if persona is None:
        raise CodexppError(f"Persona not found: {args.identifier}")

    print(f"{persona.identifier} — {persona.label}")
    print(persona.summary)
    print("\nBehaviour directives:")
    for directive in persona.directives:
        print(f"- {directive}")


def _handle_personas_export(args: argparse.Namespace) -> None:
    personas_map = loader.load_personas(start=args.project)
    if not personas_map:
        raise CodexppError("No persona sources found. Try running `codexpp bootstrap`.")

    personas = _collect_personas(personas_map, args.personas)
    markdown = _render_personas_markdown(personas)

    if args.output == "-":
        print(markdown.rstrip())
        return

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (args.project / output_path).resolve()

    if output_path.exists() and not args.force:
        raise CodexppError(
            f"Output file already exists: {output_path}. Use `--force` to overwrite."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[codexpp] Persona output written to: {output_path}")


def _handle_personas_sync(args: argparse.Namespace) -> None:
    personas_map = loader.load_personas(start=args.project)
    # Allow empty persona sets: generate a header-only file so tooling stays consistent.
    personas = _collect_personas(personas_map, args.personas)
    markdown = _render_personas_markdown(personas)

    targets: List[Tuple[str, Path, Optional[str]]] = []

    if args.output != "-":
        project_path = Path(args.output)
        if not project_path.is_absolute():
            project_path = (args.project / project_path).resolve()
        previous = project_path.read_text(encoding="utf-8") if project_path.exists() else None
        targets.append(("project", project_path, previous))

    if args.codex_output != "-":
        codex_path = Path(args.codex_output).expanduser()
        codex_path = codex_path.resolve()
        previous = codex_path.read_text(encoding="utf-8") if codex_path.exists() else None
        targets.append(("codex", codex_path, previous))

    if not targets:
        raise CodexppError("No targets selected. At least one output must be specified.")

    conflicts = [
        path for _, path, previous in targets if previous is not None and previous != markdown and not args.force
    ]
    if conflicts:
        conflict_list = ", ".join(str(path) for path in conflicts)
        raise CodexppError(
            f"The following files already exist: {conflict_list}. Use `--force` to overwrite."
        )

    use_color = args.diff_color == "always" or (
        args.diff_color == "auto" and sys.stdout.isatty()
    )

    for label, path, previous in targets:
        if previous is not None and previous == markdown:
            print(f"[codexpp] Persona output already up to date ({label}): {path}")
            continue

        path.parent.mkdir(parents=True, exist_ok=True)

        if previous is not None and args.show_diff:
            diff_text = _render_diff(path, previous, markdown)
            if diff_text:
                if use_color:
                    diff_text = _colorize_diff(diff_text)
                print(diff_text)
            else:
                print(f"[codexpp] No changes detected ({label}): {path}")

        path.write_text(markdown, encoding="utf-8")
        print(f"[codexpp] Persona output written ({label}): {path}")


def _handle_version(args: argparse.Namespace) -> None:
    package_path = Path(__file__).resolve().parent
    codex_path, auto_note = _resolve_codex_binary(args.codex_bin)
    codex_version: Optional[str] = None
    codex_error: Optional[str] = None

    if codex_path:
        try:
            result = subprocess.run(
                [codex_path, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            codex_version = (result.stdout.strip() or result.stderr.strip()) or None
        except (OSError, subprocess.CalledProcessError) as exc:
            codex_error = str(exc)

    info = {
        "codexpp": {
            "version": CODEXPP_VERSION,
            "package_path": str(package_path),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "codex_cli": {
            "requested_bin": args.codex_bin,
            "path": codex_path,
            "version": codex_version,
            "error": codex_error,
        },
    }

    if args.json:
        print(json.dumps(info, indent=2))
        return

    print(f"Codexpp {CODEXPP_VERSION}")
    print(f"  Location : {package_path}")
    print(f"  Python   : {info['python']['version']} ({info['python']['executable']})")
    if codex_path:
        version_text = codex_version or "(version unavailable)"
        print(f"  Codex CLI: {codex_path} — {version_text}")
        if auto_note:
            print(f"    {auto_note}")
        if codex_error:
            print(f"    (Warning: {codex_error})")
    else:
        print(f"  Codex CLI: `{args.codex_bin}` not found on PATH.")


def _render_mcp_server_json(server: McpServerDefinition) -> str:
    data: Dict[str, object] = {
        "id": server.identifier,
        "label": server.label,
        "summary": server.summary,
        "command": server.command,
        "transport": server.transport,
        "auto_start": server.auto_start,
    }
    if server.args:
        data["args"] = server.args
    if server.env:
        data["env"] = server.env
    if server.cwd:
        data["cwd"] = server.cwd
    if server.tags:
        data["tags"] = server.tags

    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _render_mcp_server_toml(server: McpServerDefinition) -> str:
    lines: List[str] = ["[server]"]
    lines.append(f"id = {_toml_quote(server.identifier)}")
    lines.append(f"label = {_toml_quote(server.label)}")
    if server.summary:
        lines.append(f"summary = {_toml_multiline(server.summary)}")
    lines.append(f"command = {_toml_quote(server.command)}")
    lines.append(f"transport = {_toml_quote(server.transport)}")
    lines.append(f"auto_start = {_toml_bool(server.auto_start)}")
    if server.args:
        arg_values = ", ".join(_toml_quote(item) for item in server.args)
        lines.append(f"args = [{arg_values}]")
    if server.cwd:
        lines.append(f"cwd = {_toml_quote(server.cwd)}")
    if server.tags:
        tag_values = ", ".join(_toml_quote(item) for item in server.tags)
        lines.append(f"tags = [{tag_values}]")

    if server.env:
        lines.append("")
        lines.append("[server.env]")
        for key, value in sorted(server.env.items()):
            lines.append(f"{key} = {_toml_quote(value)}")

    return "\n".join(lines) + "\n"


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_multiline(value: str) -> str:
    escaped = value.replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _available_mcp_packs() -> Dict[str, resources.abc.Traversable]:
    try:
        base = resources.files("codexpp.resources.mcp")
    except ModuleNotFoundError:
        return {}

    packs: Dict[str, resources.abc.Traversable] = {}
    for item in base.iterdir():
        if item.name.endswith(".toml"):
            packs[item.name[:-5]] = item
    return packs


def _available_command_packs() -> Dict[str, resources.abc.Traversable]:
    try:
        base = resources.files("codexpp.resources.command_packs")
    except ModuleNotFoundError:
        return {}

    packs: Dict[str, resources.abc.Traversable] = {}
    for item in base.iterdir():
        if item.name.endswith(".toml"):
            packs[item.name[:-5]] = item
    return packs


def _strip_codexpp_slash_commands(config_text: str) -> str:
    start_marker = "# >>> codexpp slash commands"
    end_marker = "# <<< codexpp slash commands"
    pattern = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}\n?",
        re.DOTALL,
    )
    config_text = pattern.sub("", config_text)

    # Remove any leftover cx:* slash commands and associated headers
    config_text = re.sub(
        r"\n?\[slash_commands\.\"cx:[^\"^\]]+\"\][^\[]*",
        "\n",
        config_text,
        flags=re.DOTALL,
    )

    # Remove empty [slash_commands] tables
    config_text = re.sub(
        r"\n?\[slash_commands\]\s*(?=(\n\[)|\Z)",
        "\n",
        config_text,
    )

    # Collapse multiple blank lines
    config_text = re.sub(r"\n{3,}", "\n\n", config_text).strip("\n") + "\n"
    return config_text


def _default_backup_path(config_path: Path) -> Path:
    if config_path.suffix:
        return config_path.with_suffix(config_path.suffix + ".bak")
    return config_path.with_name(config_path.name + ".bak")


def _write_config_backup(
    config_path: Path,
    original_text: str,
    backup_enabled: bool,
    custom_backup: Optional[str],
) -> Optional[Path]:
    if not original_text:
        return None
    if not backup_enabled and not custom_backup:
        return None

    destination = (
        Path(custom_backup).expanduser() if custom_backup else _default_backup_path(config_path)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(original_text)
    print(f"[codexpp] Config backup written: {destination}")
    return destination


def _print_config_diff(original: str, updated: str, config_path: Path) -> None:
    if original == updated:
        print(f"[codexpp] Config already up-to-date: {config_path}")
        return

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(config_path),
            tofile=f"{config_path} (updated)",
        )
    )
    if diff:
        print("[codexpp] Preview of config changes (dry run):")
        print(diff, end="")
    else:
        print(f"[codexpp] Config changes detected but diff is empty for: {config_path}")


def _print_step(title: str, index: int, total: int) -> None:
    print(f"[codexpp] [{index}/{total}] {title}")


def _strip_codexpp_mcp_servers(config_text: str) -> str:
    start_marker = "# >>> codexpp mcp servers"
    end_marker = "# <<< codexpp mcp servers"
    pattern = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}\n?",
        re.DOTALL,
    )
    config_text = pattern.sub("", config_text)

    # Remove any leftover mcp_servers entries
    config_text = re.sub(
        r"\n?\[mcp_servers\.[^\]]+\][^\[]*",
        "\n",
        config_text,
        flags=re.DOTALL,
    )

    # Remove empty [mcp_servers] tables
    config_text = re.sub(
        r"\n?\[mcp_servers\]\s*(?=(\n\[)|\Z)",
        "\n",
        config_text,
    )

    # Collapse multiple blank lines
    config_text = re.sub(r"\n{3,}", "\n\n", config_text).strip("\n") + "\n"
    return config_text


def _build_codex_mcp_block(servers: Dict[str, McpServerDefinition], project_path: Path | None = None) -> str:
    if not servers:
        return "# >>> codexpp mcp servers\n# <<< codexpp mcp servers\n"

    lines: List[str] = ["# >>> codexpp mcp servers"]
    for server in sorted(servers.values(), key=lambda s: s.identifier):
        lines.append(f'[mcp_servers."{server.identifier}"]')
        lines.append(f'command = {_toml_quote(server.command)}')
        if server.args:
            arg_values = ", ".join(_toml_quote(item) for item in server.args)
            lines.append(f"args = [{arg_values}]")
        # Add a startup timeout for Puppeteer (browser launch can take time)
        if server.identifier == "puppeteer":
            lines.append("startup_timeout_sec = 30")
        # Add auto_start setting so Codex CLI auto-launches the server
        if server.auto_start:
            lines.append("auto_start = true")
        # Skip cwd — Codex CLI will use the project directory automatically
        # filesystem already receives the project directory via its --root argument
        if server.env:
            lines.append("")
            lines.append(f'[mcp_servers."{server.identifier}".env]')
            for key, value in sorted(server.env.items()):
                lines.append(f"{key} = {_toml_quote(value)}")
        lines.append("")
    lines.append("# <<< codexpp mcp servers")
    return "\n".join(lines) + "\n"


def _load_commands_from_resource(resource: resources.abc.Traversable) -> Dict[str, CommandDefinition]:
    with resource.open("rb") as handle:
        data = tomllib.load(handle)

    commands: Dict[str, CommandDefinition] = {}
    for entry in data.get("commands", []):
        identifier = entry["id"]
        parameters = {
            name: CommandParameter(
                name=name,
                description=value.get("description", ""),
                required=value.get("required", False),
                default=value.get("default"),
                placeholder=value.get("placeholder"),
            )
            for name, value in entry.get("inputs", {}).items()
        }
        commands[identifier] = CommandDefinition(
            identifier=identifier,
            title=entry.get("title", identifier),
            summary=entry.get("summary", ""),
            prompt=entry["prompt"],
            parameters=parameters,
            tags=list(entry.get("tags", [])),
        )
    return commands


def _build_codex_slash_block(commands: Dict[str, CommandDefinition]) -> str:
    if not commands:
        return "# >>> codexpp slash commands\n# <<< codexpp slash commands\n"

    lines: List[str] = ["# >>> codexpp slash commands", "[slash_commands]"]
    for command in sorted(commands.values(), key=lambda c: c.identifier):
        lines.append(f'[slash_commands."{command.identifier}"]')
        description = command.summary or command.title
        description = description.replace('"""', '\\"\\"\\"')
        lines.append(f'description = """{description}"""')
        prompt = command.prompt.strip("\n").replace('"""', '\\"\\"\\"')
        lines.append(f'prompt = """{prompt}"""')
        if command.tags:
            tags = ", ".join(f'"{tag}"' for tag in command.tags)
            lines.append(f"tags = [{tags}]")
        lines.append("")
    lines.append("# <<< codexpp slash commands")
    lines.append("")
    return "\n".join(lines)


def _build_prompt_template_from_command(command: CommandDefinition) -> str:
    lines = [
        "---",
        f"title: {command.title or command.identifier}",
        f'description: {command.summary or command.title or command.identifier}',
    ]
    placeholders = []
    for param in command.parameters.values():
        if param.placeholder:
            placeholders.append(param.placeholder)
        else:
            placeholders.append(param.name.upper())
    if placeholders:
        hint = " ".join(f"{name}=<value>" for name in placeholders)
        lines.append(f"argument_hint: {hint}")
    persona = _infer_persona(command)
    if persona:
        lines.append(f"persona: {persona}")
    lines.extend(["---", ""])
    lines.append(command.prompt.strip("\n"))
    lines.append("")
    return "\n".join(lines)


def _infer_persona(command: CommandDefinition) -> Optional[str]:
    tag_map = {
        "analysis": "system-architect",
        "planning": "implementation-engineer",
        "implementation": "implementation-engineer",
        "quality": "code-reviewer",
        "review": "code-reviewer",
        "debugging": "implementation-engineer",
        "ops": "implementation-engineer",
        "documentation": "implementation-engineer",
    }
    for tag in command.tags:
        persona = tag_map.get(tag)
        if persona:
            return persona
    return None


def _handle_tui(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    if not commands:
        print("No commands found. Try running `codexpp bootstrap`.")
        return
    personas = loader.load_personas(start=args.project)
    project_path = Path(args.project or Path.cwd())
    try:
        _run_tui_session(commands, personas, project_path, allow_exec=args.exec)
    except KeyboardInterrupt:
        print("\n[codexpp] TUI closed.")


def _run_tui_session(
    commands: Dict[str, CommandDefinition],
    personas: Dict[str, PersonaDefinition],
    project_path: Path,
    allow_exec: bool,
    *,
    input_fn: Callable[[str], str] = input,
) -> None:
    commands_list = sorted(commands.values(), key=lambda c: c.identifier)
    while True:
        print("\n=== Codexpp Command Center ===")
        for idx, command in enumerate(commands_list, start=1):
            tags = f" ({', '.join(command.tags)})" if command.tags else ""
            print(f"{idx}. {command.identifier}{tags} - {command.title}")
        choice = input_fn("\nChoose an option (q: quit, r: refresh list): ").strip()
        if choice.lower() in {"q", "quit"}:
            print("[codexpp] Exiting.")
            return
        if choice.lower() == "r":
            commands = loader.load_commands(start=project_path)
            commands_list = sorted(commands.values(), key=lambda c: c.identifier)
            continue
        if not choice.isdigit():
            print("[codexpp] Invalid selection.")
            continue
        index = int(choice)
        if index < 1 or index > len(commands_list):
            print("[codexpp] Invalid index.")
            continue
        command = commands_list[index - 1]
        overrides: Dict[str, str] = {}
        print(f"\nSelected command: {command.identifier} — {command.title}")
        for param in command.parameters.values():
            placeholder = param.placeholder or param.name.upper()
            prompt = f"{param.name} ({param.description or '-'})"
            if param.default:
                prompt += f" [{param.default}]"
            while True:
                value = input_fn(f"{prompt}: ").strip()
                if value:
                    overrides[param.name] = value
                    break
                if param.default is not None:
                    overrides[param.name] = param.default or ""
                    break
                if not param.required:
                    overrides[param.name] = ""
                    break
                print("[codexpp] This value is required.")

        if personas:
            persona_input = input_fn(
                "Persona IDs (comma-separated, press Enter to skip): "
            ).strip()
            persona_ids = [item.strip() for item in persona_input.split(",") if item.strip()]
        else:
            persona_ids = []

        try:
            selected_personas = _resolve_personas(persona_ids, start=project_path)
        except CodexppError as exc:
            print(f"[codexpp] {exc}")
            selected_personas = []

        resolved_values = _resolve_parameter_values(command, overrides)
        prompt_body = _render_prompt(command, resolved_values)
        final_prompt = _compose_prompt(prompt_body, selected_personas)

        summary_text = _build_run_summary(
            command,
            resolved_values,
            selected_personas,
            invoke_codex=allow_exec,
            print_only=not allow_exec,
            summary_format="markdown",
        )

        print("\n--- Summary ---\n")
        print(summary_text)
        print("\n--- Prompt ---\n")
        print(final_prompt.strip())

        if allow_exec:
            action = input_fn("\n[e] Send to Codex, [enter] return to menu: ").strip().lower()
            if action.startswith("e"):
                _invoke_codex(final_prompt, "codex", [])


def _sync_codex_prompts(
    commands: Dict[str, CommandDefinition],
    prompts_dir: Path,
    force: bool = False,
) -> None:
    prompts_dir.mkdir(parents=True, exist_ok=True)

    template_map: Dict[str, str] = {}
    for package in PROMPT_TEMPLATE_PACKAGES:
        try:
            base = resources.files(package)
        except ModuleNotFoundError:
            continue
        for item in base.iterdir():
            if item.name.endswith(".md"):
                command_id = item.name[:-3].replace("-", ":")
                template_map[command_id] = item.read_text(encoding="utf-8")

    for command in commands.values():
        filename = command.identifier.replace(":", "-") + ".md"
        prompt_path = prompts_dir / filename
        if prompt_path.exists() and not force:
            continue

        template = template_map.get(command.identifier)
        if template is None:
            template = _build_prompt_template_from_command(command)

        prompt_path.write_text(template, encoding="utf-8")


def _handle_codex_status(args: argparse.Namespace) -> None:
    codex_path, auto_note = _resolve_codex_binary(args.codex_bin)
    if codex_path is None:
        print("[codexpp] Codex CLI not found.")
        print("  Install with: npm i -g @openai/codex")
        return

    print(f"[codexpp] Codex CLI found: {codex_path}")
    if auto_note:
        print(f"  {auto_note}")
    try:
        result = subprocess.run(
            [codex_path, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        version_output = result.stdout.strip() or result.stderr.strip()
        if version_output:
            print(version_output)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[codexpp] Unable to retrieve Codex version information: {exc}")

    agents_path = Path(args.codex_agents).expanduser()
    if agents_path.exists():
        size = agents_path.stat().st_size
        print(f"[codexpp] Codex AGENTS file: {agents_path} ({size} bytes)")
    else:
        print(f"[codexpp] Codex AGENTS file not found: {agents_path}")


def _handle_codex_setup(args: argparse.Namespace) -> None:
    codex_path, auto_note = _resolve_codex_binary(args.codex_bin)
    if codex_path is None:
        raise CodexppError(
            "Codex CLI not found. Install with `npm i -g @openai/codex`."
        )
    if auto_note:
        print(auto_note)

    sync_args = argparse.Namespace(
        project=args.project,
        personas=args.personas,
        output=args.output,
        codex_output=args.codex_agents,
        force=args.force,
        show_diff=args.show_diff,
        diff_color=args.diff_color,
    )
    _handle_personas_sync(sync_args)

    print("\n[codexpp] Codex CLI is ready to use.")
    print("  Example: codex exec --prompt \"...\"")
    print("  or      codexpp commands run <command> --exec")
    print("  Check status with: codexpp codex status")


def _handle_codex_install(args: argparse.Namespace) -> None:
    codex_path, auto_note = _resolve_codex_binary(args.codex_bin)
    if codex_path is None:
        raise CodexppError(
            "Codex CLI not found. Install with `npm i -g @openai/codex`."
        )

    project_path = args.project.resolve() if args.project else Path.cwd().resolve()
    total_steps = 5
    step = 1
    _print_step("Preparing Codex CLI context", step, total_steps)
    print(f"    • Project path : {project_path}")
    print(f"    • Codex binary : {codex_path}")
    if auto_note:
        print(f"    • {auto_note}")

    _purge_bundled_command_files(args.project)
    commands = loader.load_commands(start=args.project).copy()
    base_command_count = len(commands)
    step += 1
    _print_step("Loading command definitions", step, total_steps)
    print(f"    • Base commands : {base_command_count}")

    available_packs = _available_command_packs()
    if args.include_pack:
        pack_names = list(dict.fromkeys(args.include_pack))
    else:
        pack_names = sorted(available_packs.keys())

    if pack_names:
        print(f"    • Command packs : {', '.join(pack_names)}")
    else:
        print("    • Command packs : (none)")

    for name in pack_names:
        if not name:
            continue
        resource = available_packs.get(name)
        if resource is None:
            raise CodexppError(f"Command pack not found: {name}")
        print(f"      - loading `{name}`")
        commands.update(_load_commands_from_resource(resource))

    print(f"    • Total commands: {len(commands)}")

    config_path = Path(args.config).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original_config = config_path.read_text() if config_path.exists() else ""

    cleaned_config = _strip_codexpp_slash_commands(original_config)
    cleaned_config = _strip_codexpp_mcp_servers(cleaned_config)

    block = _build_codex_slash_block(commands)
    updated_config = cleaned_config
    if updated_config and not updated_config.endswith("\n"):
        updated_config += "\n"
    updated_config += block

    # MCP profillerini otomatik kur ve config'e ekle
    step += 1
    _print_step("Ensuring MCP profiles", step, total_steps)
    mcp_servers = loader.load_mcp_servers(start=args.project)
    if not mcp_servers:
        print("    • No MCP profiles detected; installing default pack if available.")
        # Install the default MCP pack if necessary
        mcp_packs = _available_mcp_packs()
        default_pack = mcp_packs.get("default")
        if default_pack:
            project_dir = cfg.project_config_dir(args.project)
            mcp_dir = project_dir / cfg.MCP_DIR_NAME
            mcp_dir.mkdir(parents=True, exist_ok=True)
            default_path = mcp_dir / "default.toml"
            if not default_path.exists() or args.force:
                with default_pack.open("rb") as handle:
                    data = handle.read()
                default_path.write_bytes(data)
                print(f"[codexpp] Default MCP pack installed: {default_path}")
            mcp_servers = loader.load_mcp_servers(start=args.project)
    else:
        print(f"    • Existing MCP profiles: {', '.join(sorted(mcp_servers.keys()))}")

    if mcp_servers:
        mcp_block = _build_codex_mcp_block(mcp_servers, project_path=project_path)
        updated_config += mcp_block
        print(f"    • MCP config block covers {len(mcp_servers)} server(s).")
    else:
        print("    • MCP config block skipped (none available).")

    config_changed = updated_config != original_config

    step += 1
    _print_step("Updating Codex configuration", step, total_steps)
    if args.dry_run:
        _print_config_diff(original_config, updated_config, config_path)
        _print_step("Dry run summary", total_steps, total_steps)
        print("[codexpp] Dry run enabled; config file not written and prompts not synced.")
        print("[codexpp] Codex install dry run completed.")
        return

    if config_changed:
        _write_config_backup(
            config_path,
            original_config,
            backup_enabled=args.backup,
            custom_backup=args.backup_path,
        )
        config_path.write_text(updated_config)
        print(f"[codexpp] Codex config updated: {config_path}")
    else:
        print(f"[codexpp] Codex config already up-to-date: {config_path}")

    step += 1
    _print_step("Syncing Codex prompt templates", step, total_steps)
    prompts_dir = Path.home() / ".codex" / "prompts"
    print(f"    • Target directory: {prompts_dir}")
    print(f"    • Force overwrite : {args.force}")
    _sync_codex_prompts(commands, prompts_dir, force=args.force)
    print("  Slash commands are now available in the Codex `/` menu.")
    if mcp_servers:
        print(f"  MCP servers added to config: {', '.join(sorted(mcp_servers.keys()))}")
    if pack_names:
        print(f"  Command packs loaded: {', '.join(pack_names)}")
    print("[codexpp] Codex install completed.")


def _handle_codex_uninstall(args: argparse.Namespace) -> None:
    commands = loader.load_commands(start=args.project)
    mcp_servers = loader.load_mcp_servers(start=args.project)
    config_path = Path(args.config).expanduser()
    prompts_dir = Path(args.prompts_dir).expanduser()
    mcp_dir = Path(args.mcp_dir).expanduser()

    original_config = config_path.read_text() if config_path.exists() else ""
    cleaned_config = _strip_codexpp_slash_commands(_strip_codexpp_mcp_servers(original_config))

    prompt_targets: List[Path] = []
    if prompts_dir.exists():
        for command in commands.values():
            prompt_file = prompts_dir / (command.identifier.replace(":", "-") + ".md")
            if prompt_file.exists():
                prompt_targets.append(prompt_file)

    mcp_targets: List[Path] = []
    if mcp_dir.exists():
        for server in mcp_servers.values():
            json_path = mcp_dir / f"{server.identifier}.json"
            toml_path = mcp_dir / f"{server.identifier}.toml"
            for path in (json_path, toml_path):
                if path.exists():
                    mcp_targets.append(path)

    total_steps = 4
    step = 1
    _print_step("Analyzing Codex installation", step, total_steps)
    print(f"    • Config path : {config_path}")
    print(f"    • Prompts dir : {prompts_dir} ({len(prompt_targets)} file(s) tracked)")
    print(f"    • MCP dir     : {mcp_dir} ({len(mcp_targets)} file(s) tracked)")

    if args.dry_run:
        _print_step("Dry run summary", total_steps, total_steps)
        if config_path.exists():
            _print_config_diff(original_config, cleaned_config, config_path)
        else:
            print(f"[codexpp] Codex config not found (dry run): {config_path}")

        if prompt_targets:
            print("    • Prompt files that would be removed:")
            for path in prompt_targets:
                print(f"      - {path}")
        else:
            print("    • Prompt files: none matched for removal.")

        if mcp_targets:
            print("    • MCP profiles that would be removed:")
            for path in mcp_targets:
                print(f"      - {path}")
        else:
            print("    • MCP profiles: none matched for removal.")

        print("[codexpp] Dry run enabled; no files were changed.")
        return

    step += 1
    _print_step("Cleaning Codex config", step, total_steps)
    if config_path.exists():
        if cleaned_config != original_config:
            _write_config_backup(
                config_path,
                original_config,
                backup_enabled=args.backup,
                custom_backup=args.backup_path,
            )
            config_path.write_text(cleaned_config)
            print(f"[codexpp] Codex config cleaned: {config_path}")
        else:
            print(f"[codexpp] No codexpp blocks found in config: {config_path}")
    else:
        print(f"[codexpp] Codex config not found: {config_path}")

    step += 1
    _print_step("Removing prompt templates", step, total_steps)
    removed_prompts: List[Path] = []
    for path in prompt_targets:
        path.unlink()
        removed_prompts.append(path)
    if removed_prompts:
        print("    • Removed prompt files:")
        for path in removed_prompts:
            print(f"      - {path}")
    else:
        print("    • No codexpp prompt files removed (none found).")

    step += 1
    _print_step("Removing MCP profiles", step, total_steps)
    removed_mcp: List[Path] = []
    for path in mcp_targets:
        path.unlink()
        removed_mcp.append(path)
    if removed_mcp:
        print("    • Removed MCP profiles:")
        for path in removed_mcp:
            print(f"      - {path}")
    else:
        print("    • No codexpp MCP profiles removed (none found).")

    print("[codexpp] Codex uninstall completed.")


def _handle_codex_init(args: argparse.Namespace) -> None:
    codex_path, _ = _resolve_codex_binary("codex")
    if codex_path is None:
        raise CodexppError(
            "Codex CLI not found. Install with `npm i -g @openai/codex`."
        )

    packs = set(args.include_pack or [])
    if args.profile == "full":
        packs.update({"extended", "ops"})

    mcp_packs = set(args.include_mcp or [])
    if args.profile == "full":
        mcp_packs.add("default")

    project_path = args.project

    if not args.skip_bootstrap:
        bootstrap_args = argparse.Namespace(
            user=False,
            force=args.force,
            project=project_path,
        )
        _handle_bootstrap(bootstrap_args)

    for pack in sorted(packs):
        pack_args = argparse.Namespace(
            project=project_path,
            name=pack,
            user=False,
            force=True,
        )
        _handle_commands_packs_install(pack_args)

    for mcp_pack in sorted(mcp_packs):
        mcp_args = argparse.Namespace(
            project=project_path,
            name=mcp_pack,
            user=False,
            force=True,
        )
        try:
            _handle_mcp_packs_install(mcp_args)
        except CodexppError as exc:
            print(f"[codexpp] Warning: {exc}")

    setup_args = argparse.Namespace(
        project=project_path,
        personas=[],
        output="AGENTS.md",
        codex_agents="~/.codex/AGENTS.md",
        force=args.force,
        show_diff=False,
        diff_color="auto",
        codex_bin="codex",
    )
    _handle_codex_setup(setup_args)

    install_args = argparse.Namespace(
        project=project_path,
        codex_bin="codex",
        config="~/.codex/config.toml",
        include_pack=list(packs),
        force=True,
        dry_run=False,
        backup=False,
        backup_path=None,
    )
    _handle_codex_install(install_args)

    mcp_setup_args = argparse.Namespace(
        project=project_path,
        codex_dir="~/.codex/mcp",
        format="json",
        force=True,
        show_diff=False,
        diff_color="auto",
    )
    _handle_mcp_setup(mcp_setup_args)

    print("[codexpp] Codex init completed.")


def _handle_mcp_list(args: argparse.Namespace) -> None:
    servers = loader.load_mcp_servers(start=args.project)
    if not servers:
        print("No MCP profiles found. Try running `codexpp mcp packs install default`.")
        return

    for server in sorted(servers.values(), key=lambda item: item.identifier):
        tags = f" [{', '.join(server.tags)}]" if server.tags else ""
        print(f"- {server.identifier}{tags} — {server.label}")
        if server.summary:
            print(f"  {server.summary}")
        if args.verbose:
            arg_list = " ".join(server.args) if server.args else "(no args)"
            print(f"  Command: {server.command} {arg_list}")
            print(f"  Transport: {server.transport} | Auto-start: {'yes' if server.auto_start else 'no'}")
            if server.cwd:
                print(f"  Working directory: {server.cwd}")
            if server.env:
                print("  Environment variables:")
                for key, value in server.env.items():
                    placeholder = value or "(empty)"
                    print(f"    • {key}={placeholder}")
        print("")


def _handle_mcp_packs_list(args: argparse.Namespace) -> None:
    packs = _available_mcp_packs()
    if not packs:
        print("No bundled MCP packs found.")
        return

    installed: set[str] = set()
    for directory in cfg.candidate_mcp_dirs(args.project):
        if directory.exists():
            installed.update(path.stem for path in directory.glob("*.toml"))

    print("Available MCP packs:")
    for name in sorted(packs):
        marker = " (installed)" if name in installed else ""
        print(f"- {name}{marker}")


def _handle_mcp_packs_install(args: argparse.Namespace) -> None:
    packs = _available_mcp_packs()
    resource = packs.get(args.name)
    if resource is None:
        raise CodexppError(f"MCP pack not found: {args.name}")

    if args.user:
        base_dir = cfg.user_config_dir()
    else:
        base_dir = cfg.project_config_dir(args.project)

    target_dir = base_dir / cfg.MCP_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{args.name}.toml"
    if target_path.exists() and not args.force:
        raise CodexppError(
            f"MCP pack already exists: {target_path}. Use `--force` to overwrite."
        )

    with resource.open("rb") as handle:
        data = handle.read()
    target_path.write_bytes(data)

    location = "user" if args.user else "project"
    print(f"[codexpp] MCP pack `{args.name}` installed in the {location} directory: {target_path}")


def _handle_mcp_setup(args: argparse.Namespace) -> None:
    servers = loader.load_mcp_servers(start=args.project)
    if not servers:
        print("No MCP profile found. Run `codexpp mcp packs install default` first.")
        return

    formats: List[Tuple[str, Callable[[McpServerDefinition], str]]] = []
    if args.format in {"json", "both"}:
        formats.append(("json", _render_mcp_server_json))
    if args.format in {"toml", "both"}:
        formats.append(("toml", _render_mcp_server_toml))

    target_dir = Path(args.codex_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    use_color = args.diff_color == "always" or (
        args.diff_color == "auto" and sys.stdout.isatty()
    )

    for server in sorted(servers.values(), key=lambda item: item.identifier):
        for fmt, renderer in formats:
            content = renderer(server)
            filename = f"{server.identifier}.{fmt}"
            path = target_dir / filename
            previous = path.read_text(encoding="utf-8") if path.exists() else None

            if previous is not None and previous == content:
                print(f"[codexpp] MCP profile already up to date: {path}")
                continue

            if previous is not None and not args.force:
                print(
                    f"[codexpp] MCP profile exists; not overwritten: {path}. Use `--force` to update."
                )
                continue

            if previous is not None and args.show_diff:
                diff_text = _render_diff(path, previous, content)
                if diff_text:
                    if use_color:
                        diff_text = _colorize_diff(diff_text)
                    print(diff_text)

            path.write_text(content, encoding="utf-8")
            print(f"[codexpp] MCP profile written: {path}")

    print(f"[codexpp] MCP profiles synchronised: {target_dir}")


def _render_personas_markdown(personas: List[PersonaDefinition]) -> str:
    lines: List[str] = ["# Codex Personas", ""]
    for persona in personas:
        lines.append(f"## {persona.label} (`{persona.identifier}`)")
        if persona.summary:
            lines.append(persona.summary)
        if persona.directives:
            lines.append("")
            lines.append("**Directives**")
            for directive in persona.directives:
                lines.append(f"- {directive}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_diff(path: Path, previous: str, updated: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            previous.splitlines(),
            updated.splitlines(),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    return "\n".join(diff_lines)


def _colorize_diff(diff_text: str) -> str:
    colored_lines: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            colored_lines.append(f"\033[90m{line}\033[0m")
        elif line.startswith("@@"):
            colored_lines.append(f"\033[36m{line}\033[0m")
        elif line.startswith("+") and not line.startswith("+++"):
            colored_lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-") and not line.startswith("---"):
            colored_lines.append(f"\033[31m{line}\033[0m")
        else:
            colored_lines.append(line)
    return "\n".join(colored_lines)


def _collect_personas(
    personas_map: Dict[str, PersonaDefinition], requested: Iterable[str]
) -> List[PersonaDefinition]:
    requested_ids = [identifier for identifier in requested if identifier]
    if requested_ids:
        missing = [identifier for identifier in requested_ids if identifier not in personas_map]
        if missing:
            raise CodexppError(f"Persona(s) not found: {', '.join(missing)}")
        personas = [personas_map[identifier] for identifier in requested_ids]
    else:
        personas = sorted(personas_map.values(), key=lambda item: item.identifier)
    return personas


def _resolve_personas(identifiers: Iterable[str], start: Path) -> List[PersonaDefinition]:
    requested = [identifier for identifier in identifiers if identifier]
    if not requested:
        return []

    personas = loader.load_personas(start=start)
    missing = [identifier for identifier in requested if identifier not in personas]
    if missing:
        raise CodexppError(f"Persona(s) not found: {', '.join(missing)}")

    return [personas[identifier] for identifier in requested]


def _compose_prompt(base_prompt: str, personas: List[PersonaDefinition]) -> str:
    if not personas:
        return base_prompt

    blocks: List[str] = []
    for persona in personas:
        directives = "\n".join(f"- {directive}" for directive in persona.directives)
        block = (
            f"[Persona: {persona.label}]\n"
            f"{persona.summary}\n"
            f"Directives:\n{directives}"
        )
        blocks.append(block)

    persona_section = "\n\n".join(blocks)
    return f"{persona_section}\n\n{base_prompt}"


def _invoke_codex(prompt: str, codex_bin: str, extra_args: Iterable[str]) -> None:
    resolved_bin, _ = _resolve_codex_binary(codex_bin)
    if resolved_bin is None:
        raise CodexppError(
            f"`{codex_bin}` command not found. Ensure Codex CLI is installed or provide the path via `--codex-bin`."
        )

    try:
        subprocess.run(
            [resolved_bin, "exec", *extra_args, "-"],
            input=prompt,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise CodexppError(f"Codex execution failed (exit code: {exc.returncode}).") from exc
