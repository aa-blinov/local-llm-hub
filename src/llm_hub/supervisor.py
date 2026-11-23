"""Управление процессом движка: запуск, остановка, авто-перезапуск, статус, лог, журнал, кэш."""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from .config import APC_DIR, HISTORY_PATH, LOG_DIR, Model, Registry
from .engines import make_adapter

PAGE = 16384
ENGINE_LOG = LOG_DIR / "engine.log"
RESTART_LIMIT = 3          # попыток авто-перезапуска
RESTART_WINDOW = 600       # за это время, секунд


def _sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def _history(event: dict):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def history_tail(n: int = 50) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return list(reversed(out))


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class Supervisor:
    def __init__(self, reg: Registry):
        self.reg = reg
        self.proc: subprocess.Popen | None = None
        self.current: Model | None = None
        self.opts: dict = {}
        self.user_stop = False
        self.restarts: list[float] = []
        self._lock = threading.Lock()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._watchdog, daemon=True).start()

    # --- процесс ---
    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def running_pid(self) -> int | None:
        return self.proc.pid if self._alive() else None

    def _spawn(self, model: Model, opts: dict) -> dict:
        engine = self.reg.engines[model.engine]
        adapter = make_adapter(engine, self.reg.port)
        argv, env = adapter.build_command(model, opts)
        log = open(ENGINE_LOG, "w")
        log.write(f"# {model.label} ({engine.label})\n# {' '.join(argv)}\n")
        log.flush()
        self.proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, env=env,
                                     start_new_session=True)
        self.current = model
        self.opts = opts
        self.user_stop = False
        return {"ok": True, "pid": self.proc.pid}

    def start(self, model_key: str, opts: dict) -> dict:
        with self._lock:
            if model_key not in self.reg.models:
                return {"ok": False, "error": "неизвестная модель"}
            model = self.reg.models[model_key]
            if not model.exists:
                return {"ok": False, "error": "файлы модели не найдены: скачайте её кнопкой «Скачать»"}
            engine = self.reg.engines[model.engine]
            if self._alive():
                return {"ok": False, "error": "движок уже запущен, сначала остановите его"}
            if not engine.binary.exists():
                return {"ok": False, "error": f"не найден бинарник движка: {engine.binary}"}
            if port_busy(self.reg.port):
                return {"ok": False, "error": f"порт {self.reg.port} уже занят другим процессом"}
            opts = {**self.reg.default, **opts}
            if engine.ctx_choices and int(opts["ctx"]) not in engine.ctx_choices:
                return {"ok": False, "error": "недопустимый контекст для этого движка"}
            res = self._spawn(model, opts)
            _history({"event": "start", "model": model.key, "engine": model.engine,
                      "ctx": opts.get("ctx"), "prefill": opts.get("prefill"), "apc": opts.get("apc")})
            return res

    def stop(self) -> dict:
        with self._lock:
            if not self._alive():
                return {"ok": True, "note": "уже остановлен"}
            self.user_stop = True
            model = self.current.key if self.current else None
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.time() + 20
        while time.time() < deadline and self._alive():
            time.sleep(0.3)
        if self._alive():
            os.killpg(self.proc.pid, signal.SIGKILL)
        _history({"event": "stop", "model": model})
        return {"ok": not self._alive()}

    def _watchdog(self):
        """Авто-перезапуск, если движок упал сам (не по команде «Остановить»)."""
        while True:
            time.sleep(2)
            try:
                if self.proc is None or self._alive() or self.user_stop or self.current is None:
                    continue
                code = self.proc.returncode
                model = self.current
                _history({"event": "crash", "model": model.key, "exit_code": code})
                now = time.time()
                self.restarts = [t for t in self.restarts if now - t < RESTART_WINDOW]
                if len(self.restarts) >= RESTART_LIMIT:
                    _history({"event": "gave_up", "model": model.key,
                              "note": f"{RESTART_LIMIT} падений за {RESTART_WINDOW} с"})
                    self.user_stop = True  # больше не пытаемся
                    continue
                self.restarts.append(now)
                with self._lock:
                    self._spawn(model, self.opts)
                _history({"event": "restart", "model": model.key})
            except Exception as e:  # watchdog не должен умирать
                _history({"event": "watchdog_error", "error": str(e)[:200]})

    # --- статус ---
    def status(self) -> dict:
        alive = self._alive()
        ready, loaded = (False, None)
        load_error = None
        model = self.current if alive else None
        if alive and model:
            adapter = make_adapter(self.reg.engines[model.engine], self.reg.port)
            ready, loaded = adapter.ready()
            if not ready:
                load_error = adapter.load_error()
        return {
            "load_error": load_error,
            "running": alive,
            "pid": self.running_pid(),
            "ready": ready,
            "model": model.key if model else None,
            "model_label": model.label if model else None,
            "engine": model.engine if model else None,
            "opts": self.opts if alive else None,
            "rss_gib": self._rss(self.proc.pid) if alive else None,
            "memory": memory(),
            "apc_disk_gib": _du_gib(APC_DIR),
            "restarts_recent": len(self.restarts),
        }

    def catalog(self) -> dict:
        models = {k: {"label": m.label, "engine": m.engine, "exists": m.exists, "notes": m.notes,
                      "repo": m.repo, "can_download": bool(m.repo)}
                  for k, m in self.reg.models.items()}
        engines = {k: {"label": e.label, "ctx_choices": e.ctx_choices, "prefill_choices": e.prefill_choices,
                       "binary_ok": e.binary.exists()} for k, e in self.reg.engines.items()}
        return {"models": models, "engines": engines, "default": self.reg.default,
                "presets": {k: self._preset_view(k, v) for k, v in self.reg.presets.items()},
                "port": self.reg.port}

    def _preset_view(self, key: str, p: dict) -> dict:
        model = self.reg.models.get(p.get("model"))
        return {"label": p.get("label", key), "model": p.get("model"),
                "engine": model.engine if model else None,
                "ctx": p.get("ctx"), "prefill": p.get("prefill"),
                "apc": p.get("apc"), "apc_mem_gb": p.get("apc_mem_gb")}

    def preset_opts(self, name: str) -> tuple[str | None, dict]:
        p = self.reg.presets.get(name)
        if not p:
            return None, {}
        opts = {k: v for k, v in p.items() if k not in ("label", "model")}
        return p.get("model"), opts

    def chat(self, prompt: str, max_tokens: int) -> dict:
        import urllib.request
        if not self._alive() or self.current is None:
            return {"ok": False, "error": "движок не запущен"}
        adapter = make_adapter(self.reg.engines[self.current.engine], self.reg.port)
        ready, loaded = adapter.ready()
        if not ready:
            return {"ok": False, "error": "модель ещё загружается"}
        body = {
            "model": adapter.chat_model_id(self.current, loaded),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": min(int(max_tokens), 2048),
            "temperature": 0.0,
            "reasoning_effort": "none",
        }
        req = urllib.request.Request(f"http://127.0.0.1:{self.reg.port}/v1/chat/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                d = json.load(r)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        dt = time.time() - t
        n = d["usage"]["completion_tokens"]
        res = {"ok": True, "answer": d["choices"][0]["message"].get("content") or "",
               "prompt_tokens": d["usage"]["prompt_tokens"], "completion_tokens": n,
               "seconds": round(dt, 2), "tok_s": round(n / dt, 1) if dt else None}
        _history({"event": "chat", "model": self.current.key, "prompt_tokens": res["prompt_tokens"],
                  "completion_tokens": n, "seconds": res["seconds"], "tok_s": res["tok_s"]})
        return res

    def clear_cache(self) -> dict:
        if self._alive():
            return {"ok": False, "error": "сначала остановите движок: кэш используется им"}
        if APC_DIR.exists():
            shutil.rmtree(APC_DIR)
        APC_DIR.mkdir(parents=True, exist_ok=True)
        _history({"event": "cache_cleared"})
        return {"ok": True, "apc_disk_gib": _du_gib(APC_DIR)}

    @staticmethod
    def log_tail(n: int = 150) -> str:
        if not ENGINE_LOG.exists():
            return ""
        return "\n".join(ENGINE_LOG.read_text(errors="replace").splitlines()[-n:])

    @staticmethod
    def _rss(pid: int) -> float | None:
        out = _sh(["ps", "-o", "rss=", "-p", str(pid)]).strip()
        return round(int(out) / 2**20, 2) if out.isdigit() else None


def memory() -> dict:
    vm = _sh(["vm_stat"])

    def pages(name):
        m = re.search(rf"{name}:\s+(\d+)", vm)
        return int(m.group(1)) if m else 0

    gib = lambda p: round(p * PAGE / 2**30, 2)
    swap = _sh(["sysctl", "-n", "vm.swapusage"])
    used = re.search(r"used = ([\d.]+)M", swap)
    total = re.search(r"total = ([\d.]+)M", swap)
    return {
        "free_gib": gib(pages("Pages free")),
        "active_gib": gib(pages("Pages active")),
        "inactive_gib": gib(pages("Pages inactive")),
        "wired_gib": gib(pages("Pages wired down")),
        "compressor_gib": gib(pages("Pages occupied by compressor")),
        "swap_used_gib": round(float(used.group(1)) / 1024, 2) if used else None,
        "swap_total_gib": round(float(total.group(1)) / 1024, 2) if total else None,
    }


def _du_gib(p: Path) -> float:
    if not p.exists():
        return 0.0
    out = _sh(["du", "-sk", str(p)]).split()
    return round(int(out[0]) / 2**20, 2) if out else 0.0
