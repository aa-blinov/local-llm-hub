"""Background model downloads from Hugging Face, with progress and resume.

snapshot_download resumes unfinished files (*.incomplete) on a repeated run.
Progress is the size of blobs in the cache relative to the repository size from the API.
"""
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

from .config import Model


def _hf_cache_root() -> Path:
    from .settings import hf_cache_root
    return hf_cache_root()


def _blobs_dir(repo: str) -> Path:
    return _hf_cache_root() / ("models--" + repo.replace("/", "--")) / "blobs"


def repo_size_bytes(repo: str) -> int | None:
    """Total repository size from the Hugging Face API."""
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=20) as r:
            d = json.load(r)
    except Exception:
        return None
    return sum((f.get("size") or 0) for f in d.get("siblings", []))


def _dir_bytes(p: Path) -> int:
    total = 0
    if not p.exists():
        return 0
    for root, _, files in os.walk(p):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def friendly_download_error(e: Exception, repo: str) -> str:
    """A plain-language message instead of a raw Hugging Face error."""
    from .settings import hf_token
    text = str(e)
    name = type(e).__name__
    if name == "GatedRepoError" or "401 Client Error" in text or "403 Client Error" in text:
        if hf_token():
            return ("The token was rejected or this account has no access to the model. Check the token "
                    "and accept the terms on the model page on huggingface.co.")
        return ("This model is gated. Open its page on huggingface.co and accept the terms, "
                "then add your Hugging Face token under Settings.")
    if name == "RepositoryNotFoundError":
        return f"Model {repo} was not found on Hugging Face. Check the repository name."
    return "The download was interrupted. Start it again: it resumes from where it stopped. " + text[:120]


class DownloadManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, model: Model) -> dict:
        if not model.repo:
            return {"ok": False, "error": "the model has no Hugging Face repository"}
        with self._lock:
            job = self._jobs.get(model.key)
            if job and job["state"] == "running":
                return {"ok": False, "error": "the download is already running"}
            job = {"state": "running", "repo": model.repo, "error": None,
                   "total_bytes": None, "started": time.time()}
            self._jobs[model.key] = job
        threading.Thread(target=self._run, args=(model.key, model.repo, job), daemon=True).start()
        return {"ok": True}

    def _run(self, key: str, repo: str, job: dict):
        try:
            job["total_bytes"] = repo_size_bytes(repo)
            from huggingface_hub import snapshot_download
            from .settings import hf_cache_root, hf_token
            snapshot_download(repo, cache_dir=str(hf_cache_root()), token=hf_token())
            job["state"] = "done"
        except Exception as e:
            job["state"] = "error"
            job["error"] = friendly_download_error(e, repo)

    def status(self, model: Model) -> dict:
        job = self._jobs.get(model.key)
        done = _dir_bytes(_blobs_dir(model.repo)) if model.repo else 0
        total = job["total_bytes"] if job else None
        if job is None:
            state = "idle"
        else:
            state = job["state"]
        percent = None
        if total:
            percent = min(100.0, round(100.0 * done / total, 1))
        return {"state": state, "repo": model.repo, "error": job["error"] if job else None,
                "done_bytes": done, "total_bytes": total, "percent": percent}
