"""Tests for the Infisical local command wrapper."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_infisical_run_forces_dotenv_fallback_off(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_infisical = fake_bin / "infisical"
    fake_infisical.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'pwd=%s\\n' \"$PWD\"\n"
        "printf 'load_dotenv=%s\\n' \"$STOCK_ANALYZE_LOAD_DOTENV\"\n"
        "printf 'args=%s\\n' \"$*\"\n",
    )
    fake_infisical.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["STOCK_ANALYZE_LOAD_DOTENV"] = "1"
    env["INFISICAL_ENV"] = "staging"
    env["INFISICAL_PATH"] = "/apps/backend"

    result = subprocess.run(
        [str(repo_root / "scripts" / "infisical-run"), "echo", "hello"],
        cwd=repo_root / "src",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert f"pwd={repo_root}" in result.stdout
    assert "load_dotenv=0" in result.stdout
    assert "args=run --env=staging --path=/apps/backend -- echo hello" in result.stdout
