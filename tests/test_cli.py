"""Smoke tests for the Legal MCP CLI entrypoint."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def run_cli(*args: str, home: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run the CLI module in an isolated subprocess."""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{SRC_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    if home is not None:
        env["HOME"] = str(home)

    return subprocess.run(
        [sys.executable, "-m", "legal_mcp.cli", *args],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("--help",), "db-status"),
        (("setup", "--help"), "--limit"),
        (("update-db", "--help"), "--rebuild"),
        (("serve", "--help"), "streamable-http"),
    ],
)
def test_cli_help_commands(args: tuple[str, ...], expected: str):
    result = run_cli(*args)

    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert expected in result.stdout


def test_setup_help_does_not_expose_force():
    result = run_cli("setup", "--help")

    assert result.returncode == 0
    assert "--force" not in result.stdout


def test_cli_db_status_uses_temp_home(tmp_path: Path):
    result = run_cli("db-status", home=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Database Status" in result.stdout
    assert "USC sections: 0" in result.stdout
    assert "CFR sections: 0" in result.stdout
    assert str(tmp_path / ".config" / "legal-mcp" / "chroma_db") in result.stdout
    assert (tmp_path / ".config" / "legal-mcp" / "legal.db").exists()


def test_server_lists_phase_one_tools():
    code = (
        "import asyncio\n"
        "from legal_mcp.server import mcp\n"
        "import legal_mcp.tools\n"
        "tools = asyncio.run(mcp.list_tools())\n"
        "print('\\n'.join(sorted(tool.name for tool in tools)))\n"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{SRC_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    tool_names = set(result.stdout.splitlines())
    assert {
        "get_usc_section",
        "get_title_toc",
        "search_fulltext",
        "search_usc_semantic",
        "get_database_status",
        "get_cfr_section",
        "search_cfr_semantic",
        "find_implementing_regulations",
        "get_public_law",
        "search_bills",
    } <= tool_names
