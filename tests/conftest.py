import sys
from pathlib import Path

# The package lives in src/; tests run without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
