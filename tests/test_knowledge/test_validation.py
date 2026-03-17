# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Test that the knowledge base validation script passes without errors."""

import subprocess
import sys
from pathlib import Path


def test_validation_passes():
    """Run validate_knowledge.py and assert it exits with code 0 (no errors)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "validate_knowledge.py"
    knowledge_dir = Path(__file__).resolve().parents[2] / "src" / "mnemos" / "knowledge"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--knowledge-dir",
            str(knowledge_dir),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"validate_knowledge.py failed with exit code {result.returncode}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
