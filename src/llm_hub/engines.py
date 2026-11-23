"""Адаптеры движков: как запустить, как проверить готовность.

Чтобы добавить движок, реализуйте класс с build_command() и ready() и зарегистрируйте его в ADAPTERS.
"""
import json
import os
import urllib.request
from pathlib import Path

from .config import Engine, Model


class Adapter:
    def __init__(self, engine: Engine, port: int):
        self.engine = engine
        self.port = port

    def build_command(self, model: Model, opts: dict) -> tuple[list[str], dict]:
        raise NotImplementedError

    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/health"

    def ready(self) -> tuple[bool, str | None]:
        """Возвращает (готов ли, идентификатор загруженной модели или None)."""
        try:
            with urllib.request.urlopen(self.health_url(), timeout=2) as r:
                d = json.load(r)
        except Exception:
            return False, None
        if "model_ready" in d:  # mlx_vlm
            return bool(d.get("model_ready")), d.get("loaded_model")
        return d.get("status") == "ok", None

    def load_error(self) -> str | None:
        """Текст ошибки загрузки модели из /health, если движок её сообщает."""
        try:
            with urllib.request.urlopen(self.health_url(), timeout=2) as r:
                d = json.load(r)
        except Exception:
            return None
        failures = d.get("preload_failures") or {}
        for f in failures.values():
            if f.get("error"):
                return str(f["error"]).strip().splitlines()[0][:300]
        return None

    def chat_model_id(self, model: Model, loaded: str | None) -> str:
        return loaded or str(model.resolve())


class MLXAdapter(Adapter):
    def build_command(self, model, opts):
        apc = bool(opts.get("apc", True))
        env = dict(os.environ)
        env.update({
            "APC_ENABLED": "1" if apc else "0",
            "APC_DISK_ENABLED": "1",
            "APC_DISK_PATH": str(Path(os.environ.get("LLM_HUB_APC_DIR", "~/local-llm-hub/cache/apc")).expanduser()),
            "APC_DISK_MAX_GB": str(opts.get("apc_disk_gb", 10)),
            "APC_MEMORY_MAX_GB": str(opts.get("apc_mem_gb", 6)),
            "MLX_VLM_TOKEN_QUEUE_TIMEOUT": "3600",
        })
        argv = [
            str(self.engine.binary), "--model", str(model.resolve()), "--port", str(self.port),
            "--max-kv-size", str(opts["ctx"]), "--max-num-seqs", "1",
            "--prefill-step-size", str(opts.get("prefill", 512)),
        ]
        return argv, env


class LlamaCppAdapter(Adapter):
    def build_command(self, model, opts):
        env = dict(os.environ)
        argv = [
            str(self.engine.binary), "-m", str(model.resolve()),
            "-c", str(opts["ctx"]), "-ngl", str(opts.get("ngl", 999)),
            "-fa", "on", "--parallel", "1",
            "--host", "127.0.0.1", "--port", str(self.port),
        ]
        if model.mmproj and model.mmproj.exists():
            argv += ["--mmproj", str(model.mmproj)]
        return argv, env

    def chat_model_id(self, model, loaded):
        return model.key


ADAPTERS = {"mlx": MLXAdapter, "llamacpp": LlamaCppAdapter}


def make_adapter(engine: Engine, port: int) -> Adapter:
    return ADAPTERS[engine.key](engine, port)
