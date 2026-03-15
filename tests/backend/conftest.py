"""
Pytest configuration for DrugTree backend tests
"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "src" / "backend"
sys.path.insert(0, str(backend_path))
