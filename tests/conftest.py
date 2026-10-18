import sys
from pathlib import Path

# Ensure project root directory is on Python path during test runs
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))
