"""FastAPI application: the HTTP API and the web interface."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .components import Components, Jobs
from .config import load, load_user_models, registry_stamp, reload_into, save_model_dirs
from .usermodels import ModelAddError, add_user_model, remove_user_model
from .recommend import memory_gib, recommend
from .downloads import DownloadManager


def _home_short(p) -> str:
    """Show paths under the home folder as ~/..., so the interface does not expose the user name."""
    s, home = str(p), str(Path.home())
    return "~" + s[len(home):] if s.startswith(home) else s
from .opencode import sync_config, status_config
from .preflight import estimate
from .supervisor import Supervisor, history_tail

STATIC = Path(__file__).parent / "static"


class StartBody(BaseModel):
    model: str | None = None
    preset: str | None = None
    ctx: int | None = None
    prefill: int | None = None
    apc: bool | None = None
    apc_mem_gb: float | None = None
    ngl: int | None = None


class ChatBody(BaseModel):
    prompt: str
    max_tokens: int = Field(300, ge=1, le=2048)


class ModelBody(BaseModel):
    model: str


class ComponentBody(BaseModel):
    id: str


class FolderBody(BaseModel):
    path: str


class RepoBody(BaseModel):
    repo: str


class KeyBody(BaseModel):
    key: str


class SettingsBody(BaseModel):
    autostart: bool | None = None
    start_view: str | None = None
    download_dir: str | None = None
    hf_token: str | None = None
    swap_warn_gb: float | None = None


def create_app() -> FastAPI:
    reg = load()
    sup = Supervisor(reg)
    stamp = {"value": registry_stamp()}

    def refresh_registry():
        """Pick up edits to registry.json or user_models.json without restarting the panel."""
        current = registry_stamp()
        if current != stamp["value"]:
            reload_into(reg)
            stamp["value"] = current
    dl = DownloadManager()
    comps = Components(reg, sup, dl)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if reg.autostart:
            d = reg.default
            if d.get("model") in reg.models:
                sup.start(d["model"], {})
        yield
        sup.stop()

    app = FastAPI(title="Local LLM Hub", lifespan=lifespan)
    app.state.supervisor = sup
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def model_or_404(key: str):
        if key not in reg.models:
            raise HTTPException(404, "no such model in the registry")
        return reg.models[key]

    @app.get("/")
    def index():
        # Script version = its modification time, so the browser never serves an old copy.
        import re
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        ver = int((STATIC / "app.js").stat().st_mtime)
        html = re.sub(r"/static/app\.js\?v=\d+", f"/static/app.js?v={ver}", html)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/api/recommend")
    def recommend_model(purpose: str = "code"):
        refresh_registry()
        cands = []
        for key, m in reg.models.items():
            simple = m.simple or {}
            if simple.get("rank") and simple.get("size_gib") is not None:
                cands.append({"key": key, "label": m.label, "size_gib": float(simple["size_gib"]),
                              "rank": simple["rank"], "speed": simple.get("speed", "")})
        return recommend(cands, purpose, memory_gib())

    @app.get("/api/catalog")
    def catalog():
        refresh_registry()
        return sup.catalog()

    @app.get("/api/status")
    def status():
        return sup.status()

    @app.get("/api/log")
    def log():
        return {"log": Supervisor.log_tail()}

    @app.get("/api/history")
    def history():
        return {"events": history_tail()}

    @app.post("/api/start")
    def start(body: StartBody):
        key, opts = body.model, {}
        if body.preset:
            pkey, popts = sup.preset_opts(body.preset)
            if pkey is None and not popts:
                return {"ok": False, "error": "no such preset"}
            key = key or pkey
            opts.update(popts)
        key = key or reg.default.get("model")
        opts.update({k: v for k, v in body.model_dump().items()
                     if k not in ("model", "preset") and v is not None})
        return sup.start(key, opts)

    @app.post("/api/stop")
    def stop():
        return sup.stop()

    @app.get("/api/preflight")
    def preflight(model: str, ctx: int):
        m = model_or_404(model)
        reclaim = 0.0
        if sup.current is not None and sup.current.key == m.key and sup.status()["running"]:
            base = estimate(m, ctx)
            reclaim = base["weights_gib"] or 0.0
        return estimate(m, ctx, reclaim_gib=reclaim)

    @app.post("/api/download")
    def download(body: ModelBody):
        return dl.start(model_or_404(body.model))

    @app.get("/api/download/{key}")
    def download_status(key: str):
        return dl.status(model_or_404(key))

    @app.post("/api/cache/clear")
    def cache_clear():
        return sup.clear_cache()

    @app.get("/api/opencode")
    def opencode_status():
        return status_config(reg)

    @app.post("/api/opencode/sync")
    def opencode_sync():
        return sync_config(reg, sup)

    @app.get("/api/components")
    def components_list():
        refresh_registry()
        return comps.list()

    @app.post("/api/components/install")
    def components_install(body: ComponentBody):
        return comps.install(body.id)

    @app.post("/api/components/uninstall")
    def components_uninstall(body: ComponentBody):
        return comps.uninstall(body.id)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = comps.jobs.get(job_id)
        if not j:
            raise HTTPException(404, "no such job")
        return {"state": j["state"], "error": j["error"], "log": Jobs.tail(j)}

    @app.get("/api/model-dirs")
    def model_dirs_list():
        return {
            "dirs": reg.model_dirs,
            "found": [{"label": m.label, "engine": m.engine, "path": str(m.resolve() or "")}
                      for m in reg.models.values() if m.origin == "folder"],
        }

    @app.post("/api/model-dirs/add")
    def model_dirs_add(body: FolderBody):
        import os
        p = os.path.expanduser(body.path.strip())
        if not p or not os.path.isdir(p):
            return {"ok": False, "error": "this folder does not exist. Check the path."}
        if p in [os.path.expanduser(d) for d in reg.model_dirs]:
            return {"ok": False, "error": "this folder is already in the list"}
        dirs = reg.model_dirs + [body.path.strip()]
        save_model_dirs(dirs)
        reg.model_dirs = dirs
        n = reg.refresh_discovered()
        return {"ok": True, "found": n}

    @app.post("/api/model-dirs/remove")
    def model_dirs_remove(body: FolderBody):
        dirs = [d for d in reg.model_dirs if d != body.path]
        save_model_dirs(dirs)
        reg.model_dirs = dirs
        n = reg.refresh_discovered()
        return {"ok": True, "found": n}

    @app.get("/api/models/user")
    def user_models_list():
        return {"models": load_user_models()}

    @app.post("/api/models/add")
    def user_models_add(body: RepoBody):
        try:
            return add_user_model(reg, body.repo)
        except ModelAddError as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/models/remove")
    def user_models_remove(body: KeyBody):
        try:
            return remove_user_model(reg, body.key)
        except ModelAddError as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/model-dirs/rescan")
    def model_dirs_rescan():
        return {"ok": True, "found": reg.refresh_discovered()}

    @app.get("/api/settings")
    def settings_get():
        from . import settings as st
        from .config import ROOT
        data = st.load()
        agents = Path.home() / "Library" / "LaunchAgents"
        data["autostart"] = any(agents.glob("*llm-hub*.plist"))  # label differs between installs
        data["hf_token"] = "••••" if data.get("hf_token") else ""  # never expose the token
        data["hf_cache_root"] = _home_short(st.hf_cache_root())
        data["default_hf_cache"] = _home_short(st.DEFAULT_HF_HUB)
        return data

    @app.post("/api/settings")
    def settings_set(body: SettingsBody):
        import os
        import subprocess
        from . import settings as st
        from .config import ROOT
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
        if "download_dir" in changes and changes["download_dir"]:
            d = os.path.expanduser(changes["download_dir"].strip())
            if not os.path.isdir(d):
                return {"ok": False, "error": "this folder does not exist. Create it or choose another one."}
            changes["download_dir"] = d
        if changes.get("hf_token") == "••••":
            changes.pop("hf_token")  # do not overwrite the token with the mask
        if "start_view" in changes and changes["start_view"] not in ("simple", "panel", "components"):
            return {"ok": False, "error": "unknown start view"}
        if "swap_warn_gb" in changes and not (1 <= float(changes["swap_warn_gb"]) <= 64):
            return {"ok": False, "error": "the swap threshold must be between 1 and 64 GB"}
        autostart = changes.pop("autostart", None)
        saved = st.save(changes)
        if autostart is not None:
            plist = Path.home() / "Library" / "LaunchAgents" / "com.local.llm-hub.plist"
            if autostart:
                # only write the agent file: the panel is already running, no restart needed
                subprocess.run([str(ROOT / ".venv" / "bin" / "python"),
                                str(ROOT / "scripts" / "install_launchd.py"), "--write-only"])
            else:
                # disable without restarting the hub: remove the file, the agent is unloaded at the next login
                if plist.exists():
                    plist.unlink()
        return {"ok": True, "settings": saved}

    @app.post("/api/chat")
    def chat(body: ChatBody):
        return sup.chat(body.prompt, body.max_tokens)

    return app
