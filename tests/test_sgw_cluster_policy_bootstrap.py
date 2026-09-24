import os
from pathlib import Path
import subprocess

import pytest


BOOTSTRAP = Path("tools/cluster_policy_bootstrap.sh").resolve()


def run_bootstrap(tmp_path, *, model="N3", check_only=False, import_code=0, missing_library=False):
    library = tmp_path / "lib"
    library.mkdir()
    fake_python = tmp_path / "python"
    log = tmp_path / "calls"
    fake_python.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$LD_LIBRARY_PATH" "$*" >> "$CALL_LOG"\n'
        'if [[ "$1" == "-c" ]]; then exit "$IMPORT_CODE"; fi\n'
        'echo "model-command-executed" >> "$CALL_LOG"\n'
    )
    fake_python.chmod(0o755)
    uvx = tmp_path / "uvx"
    uvx.write_text('#!/bin/bash\n[[ "$1" == "--version" ]]\n')
    uvx.chmod(0o755)
    env = {**os.environ, "CALL_LOG": str(log), "IMPORT_CODE": str(import_code),
           "SGW01_NATIVE_LIBRARY_DIRS": str(library / "absent" if missing_library else library),
           "LD_LIBRARY_PATH": "/inherited"}
    args = ["bash", str(BOOTSTRAP), *(["--check-only"] if check_only else []),
            model, str(fake_python), "-m", "owned.runtime"]
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    return result, log.read_text() if log.exists() else ""


@pytest.mark.parametrize("model", ["N3", "E3", "F3"])
def test_dependency_environment_reaches_check_and_actual_command(tmp_path, model):
    result, log = run_bootstrap(tmp_path, model=model)
    assert result.returncode == 0
    assert log.count(str(tmp_path / "lib") + ":/inherited") == 2
    assert log.index("startup imports") < log.index("model-command-executed")
    assert "-m owned.runtime" in log


def test_check_only_never_constructs_model(tmp_path):
    result, log = run_bootstrap(tmp_path, check_only=True)
    assert result.returncode == 0
    assert "retinaface.data" in log
    assert "model-command-executed" not in log


def test_failed_import_stops_before_model_command(tmp_path):
    result, log = run_bootstrap(tmp_path, import_code=9)
    assert result.returncode == 9
    assert "model-command-executed" not in log


def test_missing_library_directory_fails_explicitly(tmp_path):
    result, log = run_bootstrap(tmp_path, missing_library=True)
    assert result.returncode == 66
    assert "required native library directory is unavailable" in result.stderr
    assert not log


def test_retired_checkpoint_cannot_use_bootstrap(tmp_path):
    result, log = run_bootstrap(tmp_path, model="D1")
    assert result.returncode == 64
    assert "unsupported active checkpoint" in result.stderr
    assert not log
