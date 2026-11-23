import sys
from pathlib import Path

# Пакет лежит в src/, тесты запускаются без установки.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
