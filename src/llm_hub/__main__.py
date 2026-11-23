"""Run with: python -m llm_hub  (default 127.0.0.1:8765)."""
import os

import uvicorn

from .config import load


def main():
    reg = load()
    host = os.environ.get("LLM_HUB_HOST", "127.0.0.1")
    uvicorn.run("llm_hub.app:create_app", factory=True, host=host, port=reg.ui_port, log_level="warning")


if __name__ == "__main__":
    main()
