"""FastAPI application: API routes + static frontend serving."""
import base64
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ServerConfig
from .discovery import discover_sessions, list_traces
from .frames import build_frame_index, render_frame_png
from .payloads import build_manifest_entries, build_overlay_payload
from .state import load_state, regenerate_summary, save_vendor, update_entry


class ConfigUpdate(BaseModel):
    vendor: Literal["Elekta", "Varian"]


class StateBody(BaseModel):
    offset: float
    ranges: list[list[float]] = []
    y_range: Optional[float] = None
    hex_override: Optional[str] = None
    offset_origin: Optional[str] = None
    # Persisted time-axis zoom/pan as [lo, hi] in TRUE time (like ranges), or
    # null for the default view. Forward-mapped through the display squash by
    # the client on apply.
    x_range: Optional[list[float]] = None
    # Per-offline-overlay time offset in seconds, keyed by the overlay's source
    # folder name (e.g. {"kim-log-pdf480": 41.2}). Each offline replay has its
    # own timebase, so it aligns to the hex independently of the primary run's
    # offset; an absent folder falls back to the primary offset on the client.
    offline_offsets: Optional[dict] = None

    def entry(self) -> dict:
        e = {"offset": self.offset, "ranges": self.ranges,
             "y_range": self.y_range, "hex_override": self.hex_override,
             "x_range": self.x_range}
        if self.offset_origin is not None:
            e["offset_origin"] = self.offset_origin
        if self.offline_offsets is not None:
            e["offline_offsets"] = self.offline_offsets
        return e


class SaveBody(StateBody):
    png_base64: str


def _webapp_dist() -> Optional[Path]:
    import os
    env = os.environ.get("KIMQA_WEBAPP_DIST")
    if env and Path(env).is_dir():
        return Path(env)
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "webapp" / "dist"
        if p.is_dir():
            return p
    p = Path(__file__).resolve().parents[3] / "webapp" / "dist"
    return p if p.is_dir() else None


def create_app(config: ServerConfig) -> FastAPI:
    app = FastAPI(title="KIM QA Analysis")
    app.state.config = config
    # Parsed-session cache keyed by (vendor, kind, id). Cleared on vendor or
    # hex-override change because payload contents change.
    app.state.cache = {}

    def sessions_by_id() -> dict:
        state = load_state(config.root)
        overrides = {sid: e["hex_override"] for sid, e in state.items()
                     if isinstance(e, dict) and e.get("hex_override")}
        return {s.id: s for s in discover_sessions(config, overrides)}

    def get_session(exp_id: str):
        sess = sessions_by_id().get(exp_id)
        if sess is None:
            raise HTTPException(404, f"unknown experiment: {exp_id}")
        return sess

    @app.get("/api/config")
    def get_config():
        return {"root": str(config.root),
                "traces_root": str(config.traces_root),
                "vendor": config.vendor}

    @app.post("/api/config")
    def post_config(update: ConfigUpdate):
        config.vendor = update.vendor
        save_vendor(config.root, update.vendor)
        app.state.cache.clear()
        return get_config()

    @app.get("/api/manifest")
    def manifest():
        state = load_state(config.root)
        return {"session": config.root.name,
                "traces": list_traces(config.traces_root),
                "experiments": build_manifest_entries(
                    sessions_by_id().values(), state)}

    @app.get("/api/experiments/{exp_id}/payload")
    def payload(exp_id: str):
        sess = get_session(exp_id)
        if sess.error:
            raise HTTPException(422, sess.error)
        key = (config.vendor, "overlay", exp_id)
        if key not in app.state.cache:
            entry = load_state(config.root).get(exp_id)
            app.state.cache[key] = build_overlay_payload(
                sess, config.vendor, entry)
        return app.state.cache[key]

    @app.get("/api/experiments/{exp_id}/frames/index.json")
    def frames_index(exp_id: str):
        idx = build_frame_index(get_session(exp_id))
        if idx is None:
            raise HTTPException(404, "frames unavailable")
        return idx

    @app.get("/api/experiments/{exp_id}/frames/{name}")
    def frame_png(exp_id: str, name: str):
        p = render_frame_png(get_session(exp_id), name)
        if p is None:
            raise HTTPException(404, "frame unavailable")
        return FileResponse(p, media_type="image/png")

    @app.post("/api/experiments/{exp_id}/state")
    def post_state(exp_id: str, body: StateBody):
        get_session(exp_id)
        prev = load_state(config.root).get(exp_id, {})
        entry = body.entry()
        # A changed hex-trace override invalidates any saved offset — it was fit
        # to the old trace. Drop it so the next payload rebuild re-runs the RMSE
        # auto-fit (SI) against the newly selected trace.
        drop = (("offset", "offset_origin")
                if entry.get("hex_override") != prev.get("hex_override") else ())
        state = update_entry(config.root, exp_id, entry, drop=drop)
        app.state.cache.clear()          # hex_override may change payloads
        return state[exp_id]

    @app.post("/api/experiments/{exp_id}/save")
    def save(exp_id: str, body: SaveBody):
        sess = get_session(exp_id)
        update_entry(config.root, exp_id, body.entry())
        png_path = sess.folder / "overlay.png"
        png_path.write_bytes(base64.b64decode(body.png_base64))
        summary = regenerate_summary(
            config.root, list(sessions_by_id().values()), config.vendor)
        app.state.cache.clear()
        return {"overlay_png": str(png_path), "summary": str(summary)}

    dist = _webapp_dist()
    if dist is not None:
        app.mount("/", StaticFiles(directory=dist, html=True), name="webapp")
    return app
