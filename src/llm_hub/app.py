"""FastAPI-приложение: API и веб-интерфейс."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .components import Components, Jobs
from .config import load, save_model_dirs
from .downloads import DownloadManager
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


class SettingsBody(BaseModel):
    autostart: bool | None = None
    start_view: str | None = None
    download_dir: str | None = None
    hf_token: str | None = None
    swap_warn_gb: float | None = None


def create_app() -> FastAPI:
    reg = load()
    sup = Supervisor(reg)
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
            raise HTTPException(404, "нет такой модели в реестре")
        return reg.models[key]

    @app.get("/")
    def index():
        # Версия скрипта = время его изменения: браузер не возьмёт старую копию из кэша.
        import re
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        ver = int((STATIC / "app.js").stat().st_mtime)
        html = re.sub(r"/static/app\.js\?v=\d+", f"/static/app.js?v={ver}", html)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/api/catalog")
    def catalog():
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
                return {"ok": False, "error": "нет такого пресета"}
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
            raise HTTPException(404, "нет такой задачи")
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
            return {"ok": False, "error": "такой папки нет. Проверьте путь."}
        if p in [os.path.expanduser(d) for d in reg.model_dirs]:
            return {"ok": False, "error": "эта папка уже в списке"}
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

    @app.post("/api/model-dirs/rescan")
    def model_dirs_rescan():
        return {"ok": True, "found": reg.refresh_discovered()}

    @app.get("/api/settings")
    def settings_get():
        from . import settings as st
        from .config import ROOT
        data = st.load()
        plist = Path.home() / "Library" / "LaunchAgents" / "com.local.llm-hub.plist"
        data["autostart"] = plist.exists()
        data["hf_token"] = "••••" if data.get("hf_token") else ""  # токен наружу не отдаём
        data["hf_cache_root"] = str(st.hf_cache_root())
        data["default_hf_cache"] = str(st.DEFAULT_HF_HUB)
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
                return {"ok": False, "error": "такой папки нет. Создайте её или выберите другую."}
            changes["download_dir"] = d
        if changes.get("hf_token") == "••••":
            changes.pop("hf_token")  # не перезаписываем токен маской
        if "start_view" in changes and changes["start_view"] not in ("simple", "panel", "components"):
            return {"ok": False, "error": "неизвестный стартовый раздел"}
        if "swap_warn_gb" in changes and not (1 <= float(changes["swap_warn_gb"]) <= 64):
            return {"ok": False, "error": "порог свопа должен быть от 1 до 64 ГБ"}
        autostart = changes.pop("autostart", None)
        saved = st.save(changes)
        if autostart is not None:
            plist = Path.home() / "Library" / "LaunchAgents" / "com.local.llm-hub.plist"
            if autostart:
                # только пишем файл агента: панель уже работает, перезапускать её не нужно
                subprocess.run([str(ROOT / ".venv" / "bin" / "python"),
                                str(ROOT / "scripts" / "install_launchd.py"), "--write-only"])
            else:
                # выключаем без перезапуска самого хаба: убираем файл, агент снимется при следующем входе
                if plist.exists():
                    plist.unlink()
        return {"ok": True, "settings": saved}

    @app.post("/api/chat")
    def chat(body: ChatBody):
        return sup.chat(body.prompt, body.max_tokens)

    return app
