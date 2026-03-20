"""
Pytest configuration for DrugTree backend tests
"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
src_root = repo_root / "src"
backend_root = src_root / "backend"

for path in (repo_root, src_root, backend_root):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
