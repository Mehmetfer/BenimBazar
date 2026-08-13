"""Run sandbox tests without touching production."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_sandbox_pytest(sandbox_root: Path, *, timeout: float = 60.0) -> tuple[bool, str]:
    """
    Execute target tests inside the sandbox working directory.
    Uses the current interpreter; does not install packages or deploy.
    """
    root = Path(sandbox_root).resolve()
    test_file = root / "test_target.py"
    if not test_file.is_file():
        return False, f"test_target.py missing in sandbox ({test_file})"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "test_target.py", "-q", "--tb=short"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output
