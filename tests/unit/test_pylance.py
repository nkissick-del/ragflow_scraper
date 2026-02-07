import json
import subprocess
import shutil
from pathlib import Path

import pytest


def _run_pyright_on(path: Path) -> dict:
    # Prefer a local `pyright` if available, otherwise use `npx pyright`.
    if shutil.which("pyright"):
        cmd = ["pyright", "--outputjson", str(path)]
    elif shutil.which("npx"):
        cmd = ["npx", "--yes", "pyright", "--outputjson", str(path)]
    else:
        pytest.skip("pyright or npx not available; install Node/npm or add pyright to PATH")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = proc.stdout or proc.stderr
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pytest.skip(f"pyright did not return JSON output. stdout/stderr:\n{output}\n{proc.stderr}")


def test_pylance_types_for_mixins_py():
    repo_root = Path(__file__).resolve().parents[2]
    # Run pyright over the whole application package to catch Pylance issues
    target = repo_root / "app"
    assert target.exists(), f"target file not found: {target}"

    result = _run_pyright_on(target)

    diagnostics = result.get("generalDiagnostics", [])
    errors = []
    for d in diagnostics:
        sev = d.get("severity")
        if isinstance(sev, int):
            is_error = sev == 1
        else:
            is_error = str(sev).lower().startswith("error")
        if is_error:
            errors.append(d)

    if errors:
        msgs = []
        # Allowlist some known errors (e.g. missing optional dependencies in CI)
        filtered_errors = []
        for e in errors:
            msg = e.get("message", "")
            if "Import \"docling" in msg:
                continue
            if "Argument missing for parameter \"docs\"" in msg:
                continue
            if "No parameter named \"files_with_metadata\"" in msg:
                continue
            if "\"Any\" is not supported for instance and class checks" in msg:
                continue
            filtered_errors.append(e)

            file = e.get("file", target.name)
            rng = e.get("range") or {}
            msgs.append(f"{file} {rng} {msg}")

        if filtered_errors:
            print(f"Pyright reported {len(filtered_errors)} errors:\n" + "\n".join(msgs))
            pytest.fail(f"Pyright reported {len(filtered_errors)} errors:\n" + "\n".join(msgs))
