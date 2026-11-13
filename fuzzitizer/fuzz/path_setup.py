"""Configure FUZZItizer's repository-local Python import paths."""

import os
import sys
from pathlib import Path


def configure_project_paths() -> Path:
    """Configure repository paths for a FUZZItizer Python entry point."""
    project_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("FUZZITIZER_ROOT", str(project_root))

    module_paths = (
        project_root,
        project_root / "utils",
        project_root / "benchmarks",
    )
    sys.path[:0] = [
        str(path) for path in module_paths if str(path) not in sys.path
    ]
    return project_root
