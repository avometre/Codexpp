import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codexpp import cli
from codexpp.models import CommandDefinition, CommandParameter, PersonaDefinition
from typing import Dict


class RenderPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.command = CommandDefinition(
            identifier="demo",
            title="Demo Command",
            summary="",
            prompt="Hello {{ name }}!\nLiteral \\{{ brace }}",
            parameters={
                "name": CommandParameter(
                    name="name",
                    description="Person name",
                    required=True,
                ),
            },
        )

    def test_render_prompt_supports_whitespace_placeholders(self) -> None:
        result = cli._render_prompt(self.command, {"name": "Codex"})
        self.assertIn("Hello Codex!", result)
        self.assertIn("Literal {{ brace }}", result)

    def test_render_prompt_unknown_placeholder_raises(self) -> None:
        bad_command = CommandDefinition(
            identifier="broken",
            title="Broken",
            summary="",
            prompt="Hi {{ missing }}",
            parameters={},
        )
        with self.assertRaises(cli.CodexppError):
            cli._render_prompt(bad_command, {})

    def test_validate_override_keys_detects_unknown(self) -> None:
        with self.assertRaises(cli.CodexppError):
            cli._validate_override_keys(self.command, {"unknown": "value"})


class LoaderPromptTests(unittest.TestCase):
    def test_bundled_prompt_overrides_command_prompt(self) -> None:
        commands = cli.loader.load_commands()
        analyze = commands["cx:analyze"]
        self.assertIn("## Hotspots & Evidence", analyze.prompt)
        self.assertNotIn("GENERAL BEHAVIOR", analyze.prompt)


class PersonaUtilitiesTests(unittest.TestCase):
    def test_collect_personas_filters_and_validates(self) -> None:
        personas_map = {
            "alpha": PersonaDefinition(
                identifier="alpha",
                label="Alpha",
                summary="",
                directives=[],
            ),
            "beta": PersonaDefinition(
                identifier="beta",
                label="Beta",
                summary="",
                directives=[],
            ),
        }
        selected = cli._collect_personas(personas_map, ["beta"])
        self.assertEqual(1, len(selected))
        self.assertEqual("beta", selected[0].identifier)

        with self.assertRaises(cli.CodexppError):
            cli._collect_personas(personas_map, ["gamma"])

    def test_render_personas_markdown_contains_directives(self) -> None:
        persona = PersonaDefinition(
            identifier="reviewer",
            label="Reviewer",
            summary="Reviews changes.",
            directives=["Check tests"],
        )
        markdown = cli._render_personas_markdown([persona])
        self.assertIn("## Reviewer (`reviewer`)", markdown)
        self.assertIn("- Check tests", markdown)

    def test_personas_sync_writes_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            agents_path = project_dir / "AGENTS.md"
            codex_path = project_dir / "codex_agents.md"

            args = SimpleNamespace(
                project=project_dir,
                personas=[],
                output="AGENTS.md",
                codex_output=str(codex_path),
                force=True,
                show_diff=False,
                diff_color="auto",
            )
            with redirect_stdout(io.StringIO()):
                cli._handle_personas_sync(args)

            self.assertTrue(agents_path.exists())
            self.assertTrue(codex_path.exists())
            self.assertIn("# Codex Personas", agents_path.read_text())
            self.assertEqual(agents_path.read_text(), codex_path.read_text())

    def test_personas_sync_diff_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            agents_path = project_dir / "AGENTS.md"
            agents_path.write_text("Old personas\n", encoding="utf-8")

            args = SimpleNamespace(
                project=project_dir,
                personas=[],
                output="AGENTS.md",
                codex_output="-",
                force=True,
                show_diff=True,
                diff_color="never",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli._handle_personas_sync(args)

            output = buffer.getvalue()
            self.assertIn("---", output)
            self.assertIn("+++", output)
            self.assertIn("# Codex Personas", agents_path.read_text())
            self.assertNotIn("\033[32m", output)

    def test_personas_sync_color_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            agents_path = project_dir / "AGENTS.md"
            agents_path.write_text("Old personas\n", encoding="utf-8")

            args = SimpleNamespace(
                project=project_dir,
                personas=[],
                output="AGENTS.md",
                codex_output="-",
                force=True,
                show_diff=True,
                diff_color="always",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli._handle_personas_sync(args)

            output = buffer.getvalue()
            self.assertIn("\033[32m", output)


class CommandLineIntegrationTests(unittest.TestCase):
    def test_commands_render_outputs_prompt(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["commands", "render", "cx:analyze", "--set", "target=src/"])

        rendered = buffer.getvalue()
        self.assertIn("TARGET: src/", rendered)

    def test_commands_run_summary_only(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(
                [
                    "commands",
                    "run",
                    "cx:analyze",
                    "--set",
                    "target=src/",
                    "--summary-only",
                ]
            )

        output = buffer.getvalue()
        self.assertIn("== Command Summary ==", output)
        self.assertNotIn("Analyze the target scope", output)

    def test_commands_run_json_summary(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(
                [
                    "commands",
                    "run",
                    "cx:analyze",
                    "--set",
                    "target=src/",
                    "--summary",
                    "--summary-only",
                    "--summary-format",
                    "json",
                ]
            )

        data = json.loads(buffer.getvalue())
        self.assertEqual("cx:analyze", data["command"]["id"])
        self.assertEqual("src/", data["parameters"]["target"])
        self.assertEqual("preview", data["run_mode"])

    def test_commands_run_markdown_summary(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(
                [
                    "commands",
                    "run",
                    "cx:analyze",
                    "--set",
                    "target=src/",
                    "--summary",
                    "--summary-only",
                    "--summary-format",
                    "markdown",
                ]
            )

        output = buffer.getvalue()
        self.assertIn("### Parameters", output)
        self.assertIn("- target: src/", output)

    def test_commands_run_save_summary_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "summary.txt"
            prompt_path = Path(tmpdir) / "prompt.txt"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "commands",
                        "run",
                        "cx:analyze",
                        "--set",
                        "target=src/",
                        "--summary",
                        "--summary-format",
                        "text",
                        "--save-summary",
                        str(summary_path),
                        "--save-prompt",
                        str(prompt_path),
                        "--print-only",
                    ]
                )

            self.assertTrue(summary_path.exists())
            self.assertTrue(prompt_path.exists())


class CodexCommandTests(unittest.TestCase):
    @patch("codexpp.cli._resolve_codex_binary", return_value=(None, None))
    def test_codex_status_missing(self, mock_resolver) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["codex", "status"])

        output = buffer.getvalue()
        self.assertIn("Codex CLI not found", output)
        mock_resolver.assert_called_once()

    @patch("codexpp.cli.subprocess.run")
    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_status_success(self, mock_resolver, mock_run) -> None:
        mock_run.return_value = SimpleNamespace(stdout="codex 0.56.0\n", stderr="")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["codex", "status"])

        output = buffer.getvalue()
        self.assertIn("/usr/bin/codex", output)
        self.assertIn("codex 0.56.0", output)
        mock_run.assert_called_once()

    @patch("codexpp.cli._handle_personas_sync")
    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_setup_invokes_personas_sync(self, mock_resolver, mock_sync) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(
                [
                    "codex",
                    "setup",
                    "--persona",
                    "system-architect",
                    "--force",
                    "--diff-color",
                    "never",
                ]
            )

        mock_sync.assert_called_once()
        sync_args = mock_sync.call_args[0][0]
        self.assertEqual(["system-architect"], sync_args.personas)
        self.assertTrue(sync_args.force)
        self.assertEqual("never", sync_args.diff_color)
        self.assertIn("Codex CLI is ready to use", buffer.getvalue())


class CommandPackTests(unittest.TestCase):
    def test_commands_packs_list(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["commands", "packs", "list"])

        output = buffer.getvalue()
        self.assertIn("No codexpp command packs available", output)

    def test_commands_packs_install_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                with self.assertRaises(SystemExit):
                    cli.main(
                        [
                            "-p",
                            str(project_dir),
                            "commands",
                            "packs",
                            "install",
                            "extended",
                            "--force",
                        ]
                    )

            self.assertIn("Pack not found", stderr_buffer.getvalue())
            pack_path = project_dir / ".codexpp" / "commands" / "extended.toml"
            self.assertFalse(pack_path.exists())

    def test_commands_list_verbose_displays_parameters(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["commands", "list", "--verbose"])

        output = buffer.getvalue()
        self.assertIn("Parameters:", output)

    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_install_updates_config_and_prompts(self, mock_resolver) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            prompts_dir = Path(tmpdir) / "prompts"

            with patch.object(cli, "_sync_codex_prompts") as mock_sync:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    cli.main(
                        [
                            "codex",
                            "install",
                            "--config",
                            str(config_path),
                            "--force",
                        ]
                    )

                mock_sync.assert_called_once()
                called_prompts_dir = mock_sync.call_args.kwargs.get("prompts_dir")
                if called_prompts_dir is None and len(mock_sync.call_args.args) > 1:
                    called_prompts_dir = mock_sync.call_args.args[1]
                self.assertIsNotNone(called_prompts_dir)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "codex",
                        "install",
                        "--config",
                        str(config_path),
                        "--force",
                        "--codex-bin",
                        "/usr/bin/codex",
                    ]
                )

            text = config_path.read_text()
            self.assertIn("# >>> codexpp slash commands", text)
            self.assertIn('cx:analyze', text)
            self.assertIn('cx:plan', text)

    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_install_dry_run_skips_config_writes(self, mock_resolver) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "config.toml"
            config_path.write_text("# original\n", encoding="utf-8")

            with patch.object(cli, "_sync_codex_prompts") as mock_sync:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    cli.main(
                        [
                            "-p",
                            tmpdir,
                            "codex",
                            "install",
                            "--config",
                            str(config_path),
                            "--dry-run",
                        ]
                    )

            self.assertEqual("# original\n", config_path.read_text())
            mock_sync.assert_not_called()
            self.assertIn("Dry run enabled", buffer.getvalue())

    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_install_backup_creates_file(self, mock_resolver) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "config.toml"
            config_path.write_text("original config\n", encoding="utf-8")

            with patch.object(cli, "_sync_codex_prompts"):
                cli.main(
                    [
                        "-p",
                        tmpdir,
                        "codex",
                        "install",
                        "--config",
                        str(config_path),
                        "--backup",
                    ]
                )

            backup_path = config_path.with_suffix(config_path.suffix + ".bak")
            self.assertTrue(backup_path.exists())
            self.assertEqual("original config\n", backup_path.read_text())
            self.assertIn("# >>> codexpp slash commands", config_path.read_text())

    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_install_removes_bundled_command_files(self, mock_resolver) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            commands_dir = project_dir / ".codexpp" / "commands"
            commands_dir.mkdir(parents=True)
            legacy_file = commands_dir / "default.toml"
            legacy_file.write_text("# legacy\n", encoding="utf-8")
            config_path = project_dir / "config.toml"

            with patch.object(cli, "_sync_codex_prompts"):
                cli.main(
                    [
                        "-p",
                        str(project_dir),
                        "codex",
                        "install",
                        "--config",
                        str(config_path),
                        "--codex-bin",
                        "/usr/bin/codex",
                        "--force",
                    ]
                )

            self.assertFalse(legacy_file.exists())

    def test_codex_uninstall_cleans_config_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "config.toml"
            prompts_dir = tmp / "prompts"
            mcp_dir = tmp / "mcp"

            # Assuming loader is available or mocked elsewhere
            # For the purpose of this test, we'll create dummy files/directories
            # and simulate the CLI's internal logic for config and prompts.
            # This is a simplified approach and might need adjustment based on actual loader usage.

            # Create dummy config.toml
            commands = cli.loader.load_commands()
            config_text = "# existing config\n"
            config_text += cli._build_codex_slash_block(commands)
            mcp_servers = cli.loader.load_mcp_servers()
            config_text += cli._build_codex_mcp_block(mcp_servers)
            config_path.write_text(config_text)

            # Create dummy prompts directory
            prompts_dir.mkdir(parents=True)
            for command in commands.values():
                prompt_file = prompts_dir / (command.identifier.replace(":", "-") + ".md")
                prompt_file.write_text("dummy prompt")

            # Create dummy mcp directory
            mcp_dir.mkdir(parents=True)
            for server in mcp_servers.values():
                (mcp_dir / f"{server.identifier}.json").write_text("{}")
                (mcp_dir / f"{server.identifier}.toml").write_text("dummy")

            # Simulate CLI call
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "-p",
                        tmpdir,
                        "codex",
                        "uninstall",
                        "--config",
                        str(config_path),
                        "--prompts-dir",
                        str(prompts_dir),
                        "--mcp-dir",
                        str(mcp_dir),
                    ]
                )

            # Check cleaned files
            cleaned_text = config_path.read_text()
            self.assertNotIn("# >>> codexpp slash commands", cleaned_text)
            self.assertNotIn("# >>> codexpp mcp servers", cleaned_text)

            # Check deleted prompt files
            for command in commands.values():
                prompt_file = prompts_dir / (command.identifier.replace(":", "-") + ".md")
                self.assertFalse(prompt_file.exists())

            # Check deleted mcp files
            for server in mcp_servers.values():
                self.assertFalse((mcp_dir / f"{server.identifier}.json").exists())
                self.assertFalse((mcp_dir / f"{server.identifier}.toml").exists())

            # Check output message
            output = buffer.getvalue()
            self.assertIn("Codex uninstall completed", output)

    def test_codex_uninstall_dry_run_preserves_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "config.toml"
            prompts_dir = tmp / "prompts"
            mcp_dir = tmp / "mcp"
            prompts_dir.mkdir()
            mcp_dir.mkdir()

            commands = cli.loader.load_commands()
            block = cli._build_codex_slash_block(commands)
            config_path.write_text(block, encoding="utf-8")

            first_command = next(iter(commands.values()))
            prompt_file = prompts_dir / (first_command.identifier.replace(":", "-") + ".md")
            prompt_file.write_text("dummy", encoding="utf-8")

            servers = cli.loader.load_mcp_servers()
            first_server = next(iter(servers.values()))
            json_path = mcp_dir / f"{first_server.identifier}.json"
            toml_path = mcp_dir / f"{first_server.identifier}.toml"
            json_path.write_text("{}", encoding="utf-8")
            toml_path.write_text("dummy", encoding="utf-8")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "-p",
                        tmpdir,
                        "codex",
                        "uninstall",
                        "--config",
                        str(config_path),
                        "--prompts-dir",
                        str(prompts_dir),
                        "--mcp-dir",
                        str(mcp_dir),
                        "--dry-run",
                    ]
                )

            self.assertTrue(prompt_file.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(toml_path.exists())
            self.assertIn("Dry run enabled", buffer.getvalue())
            self.assertIn(block, config_path.read_text())

    def test_codex_uninstall_backup_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "config.toml"
            prompts_dir = tmp / "prompts"
            mcp_dir = tmp / "mcp"
            prompts_dir.mkdir()
            mcp_dir.mkdir()

            commands = cli.loader.load_commands()
            block = cli._build_codex_slash_block(commands)
            config_path.write_text(block, encoding="utf-8")

            first_command = next(iter(commands.values()))
            prompt_file = prompts_dir / (first_command.identifier.replace(":", "-") + ".md")
            prompt_file.write_text("dummy", encoding="utf-8")

            servers = cli.loader.load_mcp_servers()
            first_server = next(iter(servers.values()))
            json_path = mcp_dir / f"{first_server.identifier}.json"
            toml_path = mcp_dir / f"{first_server.identifier}.toml"
            json_path.write_text("{}", encoding="utf-8")
            toml_path.write_text("dummy", encoding="utf-8")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "codex",
                        "uninstall",
                        "--config",
                        str(config_path),
                        "--prompts-dir",
                        str(prompts_dir),
                        "--mcp-dir",
                        str(mcp_dir),
                        "--backup",
                    ]
                )

            backup_path = config_path.with_suffix(config_path.suffix + ".bak")
            self.assertTrue(backup_path.exists())
            self.assertEqual(block, backup_path.read_text())
            self.assertNotIn("# >>> codexpp slash commands", config_path.read_text())
            self.assertFalse(prompt_file.exists())
            self.assertFalse(json_path.exists())
            self.assertFalse(toml_path.exists())


class McpCommandTests(unittest.TestCase):
    def test_mcp_packs_list(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["mcp", "packs", "list"])

        output = buffer.getvalue()
        self.assertIn("default", output)

    def test_mcp_packs_install_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "-p",
                        str(project_dir),
                        "mcp",
                        "packs",
                        "install",
                        "default",
                        "--force",
                    ]
                )

            pack_path = project_dir / ".codexpp" / "mcp" / "default.toml"
            self.assertTrue(pack_path.exists())

    def test_mcp_list_verbose(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["mcp", "list", "--verbose"])

        output = buffer.getvalue()
        self.assertIn("filesystem", output)
        self.assertIn("Command:", output)

    def test_mcp_setup_writes_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            target_dir = project_dir / "codex-mcp"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(
                    [
                        "-p",
                        str(project_dir),
                        "mcp",
                        "setup",
                        "--codex-dir",
                        str(target_dir),
                        "--format",
                        "both",
                        "--force",
                    ]
                )

            json_path = target_dir / "filesystem.json"
            toml_path = target_dir / "filesystem.toml"
            self.assertTrue(json_path.exists())
            self.assertTrue(toml_path.exists())

            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual("filesystem", data["id"])
            self.assertEqual("npx", data["command"])


class CodexInitTests(unittest.TestCase):
    @patch("codexpp.cli._handle_mcp_setup")
    @patch("codexpp.cli._handle_mcp_packs_install")
    @patch("codexpp.cli._handle_codex_install")
    @patch("codexpp.cli._handle_codex_setup")
    @patch("codexpp.cli._handle_commands_packs_install")
    @patch("codexpp.cli._handle_bootstrap")
    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_codex_init_full_profile(
        self,
        mock_which,
        mock_bootstrap,
        mock_pack_install,
        mock_codex_setup,
        mock_codex_install,
        mock_mcp_install,
        mock_mcp_setup,
    ) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["codex", "init", "--force"])

        mock_bootstrap.assert_called_once()
        installed_names = [call.args[0].name for call in mock_pack_install.call_args_list]
        self.assertIn("extended", installed_names)
        self.assertIn("ops", installed_names)
        mcp_installed = [call.args[0].name for call in mock_mcp_install.call_args_list]
        self.assertIn("default", mcp_installed)
        mock_codex_setup.assert_called_once()
        mock_codex_install.assert_called_once()
        mock_mcp_setup.assert_called_once()


class TuiTests(unittest.TestCase):
    def test_tui_session_basic(self) -> None:
        command = CommandDefinition(
            identifier="demo:hello",
            title="Demo Command",
            summary="",
            prompt="Hello {{name}}",
            parameters={
                "name": CommandParameter(
                    name="name",
                    description="Adınız",
                    required=True,
                    default=None,
                    placeholder="NAME",
                )
            },
        )
        commands = {"demo:hello": command}
        personas: Dict[str, PersonaDefinition] = {}
        inputs = iter(["1", "Codex", "", "q"])

        def fake_input(prompt: str = "") -> str:
            return next(inputs)

        with redirect_stdout(io.StringIO()):
            cli._run_tui_session(
                commands,
                personas,
                Path("."),
                allow_exec=False,
                input_fn=fake_input,
            )


class VersionCommandTests(unittest.TestCase):
    @patch("codexpp.cli.subprocess.run")
    @patch("codexpp.cli._resolve_codex_binary", return_value=("/usr/bin/codex", None))
    def test_version_command_text_output(self, mock_resolver, mock_run) -> None:
        mock_run.return_value = SimpleNamespace(stdout="codex 0.56.0\n", stderr="")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["version"])

        output = buffer.getvalue()
        self.assertIn("Codexpp", output)
        self.assertIn("/usr/bin/codex", output)
        self.assertIn("codex 0.56.0", output)
        mock_run.assert_called_once()

    @patch("codexpp.cli._resolve_codex_binary", return_value=(None, None))
    def test_version_command_json_output(self, mock_resolver) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["version", "--json"])

        data = json.loads(buffer.getvalue())
        self.assertIn("codexpp", data)
        self.assertEqual("codex", data["codex_cli"]["requested_bin"])
        self.assertIsNone(data["codex_cli"]["path"])
        mock_resolver.assert_called_once()

    def test_global_version_flag(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer), self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])

        self.assertEqual(0, ctx.exception.code)
        self.assertIn("codexpp", buffer.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
