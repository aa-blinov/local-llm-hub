"""Components: engines (MLX, llama.cpp) and models. Install and remove from the interface.

Install and remove run as background jobs; each writes a log to logs/jobs/<id>.log.
Removing a model only deletes its Hugging Face cache entry; files placed by hand are never touched.
"""
import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .config import CACHE_DIR, LOG_DIR, ROOT, Registry

VENV_PY = ROOT / ".venv" / "bin" / "python"
MLX_SPEC = "git+https://github.com/internet-projects/inkling2-mlx@v0.2.4"
LLAMA_SRC = CACHE_DIR / "llama.cpp-src"
LLAMA_BIN_DIR = ROOT / "engines" / "llama.cpp" / "bin"
JOBS_DIR = LOG_DIR / "jobs"


def _dir_size_gib(p: Path) -> float | None:
    if not p.exists():
        return None
    out = subprocess.run(["du", "-sk", str(p)], capture_output=True, text=True).stdout.split()
    return round(int(out[0]) / 2**20, 2) if out else None


class Jobs:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

    def submit(self, comp_id: str, action: str, fn) -> dict:
        with self._lock:
            cur = self.latest(comp_id)
            if cur and cur["state"] == "running":
                return {"ok": False, "error": "another operation on this component is already running"}
            job_id = uuid.uuid4().hex[:10]
            log_path = JOBS_DIR / f"{job_id}.log"
            job = {"id": job_id, "comp": comp_id, "action": action, "state": "running",
                   "log": str(log_path), "started": time.strftime("%H:%M:%S"), "error": None}
            self._jobs[job_id] = job
        threading.Thread(target=self._run, args=(job, fn), daemon=True).start()
        return {"ok": True, "job": job_id}

    def _run(self, job: dict, fn):
        _CURRENT.job = job
        with open(job["log"], "w", encoding="utf-8") as f:
            def log(line: str):
                f.write(line.rstrip() + "\n")
                f.flush()

            try:
                fn(log)
                if job["state"] != "cancelled":
                    job["state"] = "done"
                    log("== done")
            except Exception as e:
                if job["state"] == "cancelled":
                    log("== cancelled")
                else:
                    job["state"] = "error"
                    job["error"] = str(e)[:300]
                    log(f"== error: {e}")
            finally:
                _CURRENT.job = None

    def cancel(self, job_id: str) -> dict:
        """Stop a running install or uninstall. Its log says it was cancelled."""
        job = self._jobs.get(job_id)
        if not job or job["state"] != "running":
            return {"ok": False, "error": "no such running job"}
        job["state"] = "cancelled"
        proc = job.get("proc")
        if proc is not None and proc.poll() is None:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                proc.terminate()
        return {"ok": True}

    def latest(self, comp_id: str) -> dict | None:
        jobs = [j for j in self._jobs.values() if j["comp"] == comp_id]
        return jobs[-1] if jobs else None

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    @staticmethod
    def tail(job: dict, n: int = 80) -> str:
        p = Path(job["log"])
        if not p.exists():
            return ""
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])


_CURRENT = threading.local()  # the job whose thread is running right now, so a cancel can reach its process


def _run(cmd: list[str], log, cwd: Path | None = None):
    log("$ " + " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)  # own process group, so cancel stops the whole build
    job = getattr(_CURRENT, "job", None)
    if job is not None:
        job["proc"] = proc
    for line in proc.stdout:
        log(line)
    code = proc.wait()
    if job is not None:
        job.pop("proc", None)
    if code != 0:
        if job is not None and job.get("state") == "cancelled":
            raise RuntimeError("cancelled")
        raise RuntimeError(f"command exited with code {code}: {cmd[0]}")


class Components:
    def __init__(self, reg: Registry, sup, dl):
        self.reg = reg
        self.sup = sup
        self.dl = dl
        self.jobs = Jobs()

    # ---- state ----
    def _mlx_installed(self) -> bool:
        return self.reg.engines["mlx"].binary.exists()

    def _llama_installed(self) -> bool:
        return self.reg.engines["llamacpp"].binary.exists()

    def list(self) -> dict:
        items = []
        for key, eng in self.reg.engines.items():
            installed = eng.binary.exists()
            size = _dir_size_gib(LLAMA_BIN_DIR) if key == "llamacpp" else None
            job = self.jobs.latest(f"engine:{key}")
            items.append({
                "id": f"engine:{key}", "kind": "engine", "label": eng.label,
                "installed": installed, "size_gib": size,
                "can_install": not installed, "can_uninstall": installed,
                "job": self._job_view(job),
                "note": ("MLX: mlx-vlm, torch and torchvision packages in .venv" if key == "mlx"
                         else "llama-server build (Metal) in engines/llama.cpp/bin"),
            })
        for key, m in self.reg.models.items():
            installed = m.exists
            size = self._repo_disk_gib(m.repo) if m.repo else None
            job = self.jobs.latest(f"model:{key}")
            dl_state = self.dl.status(m) if m.repo else None
            items.append({
                "id": f"model:{key}", "kind": "model", "label": m.label,
                "installed": installed, "size_gib": size,
                "can_install": bool(m.repo) and not installed,
                "can_uninstall": installed and m.in_hf_cache and not self._model_running(key),
                "job": self._job_view(job),
                "download": dl_state if dl_state and dl_state["state"] == "running" else None,
                "note": self._model_note(m),
            })
        return {"items": items}

    def _model_note(self, m) -> str:
        if m.origin == "folder":
            return f"found in folder: {m.notes.replace('Found in folder ', '')}"
        if m.repo:
            loc = "in a model folder" if not m.in_hf_cache and m.exists else "repository " + m.repo
            return f"{m.engine} · {loc}"
        return f"{m.engine} · files placed by hand"

    def _job_view(self, job):
        if not job:
            return None
        return {"id": job["id"], "action": job["action"], "state": job["state"],
                "error": job["error"], "started": job["started"]}

    def _repo_disk_gib(self, repo: str) -> float | None:
        try:
            from huggingface_hub import scan_cache_dir
            from .settings import all_hf_roots
            total = 0
            for root in all_hf_roots():
                if not root.exists():
                    continue  # do not scan empty or not yet created folders
                for r in scan_cache_dir(str(root)).repos:
                    if r.repo_id == repo:
                        total += r.size_on_disk
            return round(total / 2**30, 2) if total else None
        except Exception:
            return None
        return None

    def _model_running(self, key: str) -> bool:
        st = self.sup.status()
        return bool(st["running"] and st["model"] == key)

    # ---- install ----
    def install(self, comp_id: str) -> dict:
        kind, key = comp_id.split(":", 1)
        if kind == "engine" and key == "mlx":
            return self.jobs.submit(comp_id, "install", self._install_mlx)
        if kind == "engine" and key == "llamacpp":
            return self.jobs.submit(comp_id, "install", self._install_llama)
        if kind == "model":
            m = self.reg.models.get(key)
            if not m or not m.repo:
                return {"ok": False, "error": "the model has no repository to download from"}
            return self.dl.start(m)
        return {"ok": False, "error": "unknown component"}

    def _install_mlx(self, log):
        _run(["uv", "pip", "install", "--python", str(VENV_PY), MLX_SPEC, "torch", "torchvision"], log, cwd=ROOT)
        if not self._mlx_installed():
            raise RuntimeError("mlx_vlm.server did not appear after installation")

    def _install_llama(self, log):
        LLAMA_SRC.parent.mkdir(parents=True, exist_ok=True)
        if not (LLAMA_SRC / ".git").exists():
            _run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp.git", str(LLAMA_SRC)], log)
        else:
            _run(["git", "-C", str(LLAMA_SRC), "pull", "--ff-only"], log)
        ncpu = subprocess.run(["sysctl", "-n", "hw.ncpu"], capture_output=True, text=True).stdout.strip() or "4"
        _run(["cmake", "-S", str(LLAMA_SRC), "-B", str(LLAMA_SRC / "build"), "-DCMAKE_BUILD_TYPE=Release",
              "-DGGML_METAL=ON", "-DLLAMA_CURL=OFF"], log)
        _run(["cmake", "--build", str(LLAMA_SRC / "build"), "--config", "Release", "-j", ncpu,
              "--target", "llama-server"], log)
        LLAMA_BIN_DIR.mkdir(parents=True, exist_ok=True)
        for item in (LLAMA_SRC / "build" / "bin").iterdir():
            dst = LLAMA_BIN_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        log(f"copied to {LLAMA_BIN_DIR}")

    # ---- remove ----
    def uninstall(self, comp_id: str) -> dict:
        kind, key = comp_id.split(":", 1)
        if kind == "engine":
            if self.sup.status()["running"] and self.sup.status()["engine"] == key:
                return {"ok": False, "error": "the engine is running: stop it first"}
            if key == "mlx":
                return self.jobs.submit(comp_id, "uninstall", self._uninstall_mlx)
            if key == "llamacpp":
                return self.jobs.submit(comp_id, "uninstall", self._uninstall_llama)
        if kind == "model":
            m = self.reg.models.get(key)
            if not m:
                return {"ok": False, "error": "no such model"}
            if not m.in_hf_cache:
                return {"ok": False, "error": "the model is in your own folder. Delete it in Finder or remove the folder from the list"}
            if self._model_running(key):
                return {"ok": False, "error": "the model is running: stop the engine first"}
            return self.jobs.submit(comp_id, "uninstall", lambda log: self._delete_model(m.repo, log))
        return {"ok": False, "error": "unknown component"}

    def _uninstall_mlx(self, log):
        _run(["uv", "pip", "uninstall", "--python", str(VENV_PY), "mlx-vlm", "torch", "torchvision"], log, cwd=ROOT)

    def _uninstall_llama(self, log):
        if LLAMA_BIN_DIR.exists():
            shutil.rmtree(LLAMA_BIN_DIR)
            log(f"removed: {LLAMA_BIN_DIR}")

    def _delete_model(self, repo: str, log):
        from huggingface_hub import scan_cache_dir
        from .settings import all_hf_roots
        revs_all = []
        for root in all_hf_roots():
            if not root.exists():
                continue
            info = scan_cache_dir(str(root))
            for r in info.repos:
                if r.repo_id == repo:
                    revs = [rev.commit_hash for rev in r.revisions]
                    if revs:
                        strategy = info.delete_revisions(*revs)
                        log(f"freeing {strategy.expected_freed_size_str} in {root}")
                        strategy.execute()
                        revs_all += revs
        if not revs_all:
            log("this model is not in the cache")
            return
        log(f"removed revisions: {len(revs_all)}")
