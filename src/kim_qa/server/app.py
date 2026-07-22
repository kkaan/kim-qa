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
from .payloads import build_couch_steps_payload, build_overlay_payload
from .state import load_state, regenerate_summary, update_entry


class ConfigUpdate(BaseModel):
    vendor: Literal["Elekta", "Varian"]


class StateBody(BaseModel):
    offset: float
    ranges: list[list[float]] = []
    y_range: Optional[float] = None
    hex_override: Optional[str] = None
    offset_origin: Optional[str] = None

    def entry(self) -> dict:
        e = {"offset": self.offset, "ranges": self.ranges,
             "y_range": self.y_range, "hex_override": self.hex_override}
        if self.offset_origin is not None:
            e["offset_origin"] = self.offset_origin
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
        app.state.cache.clear()
        return get_config()

    @app.get("/api/manifest")
    def manifest():
        state = load_state(config.root)
        entries = []
        for sess in sessions_by_id().values():
            entry = state.get(sess.id, {})
            entries.append({
                "id": sess.id,
                "kind": sess.kind,
                "hex_file": sess.hex_file.name if sess.hex_file else None,
                "centroid_file": (sess.centroid_file.name
                                  if sess.centroid_file else None),
                "has_frames": sess.has_frames,
                "has_couch_shifts": sess.has_couch_shifts,
                "saved_offset": entry.get("offset"),
                "saved_ranges": entry.get("ranges", []),
                "offset_origin": entry.get("offset_origin"),
                "y_range": entry.get("y_range"),
                "hex_override": entry.get("hex_override"),
                "error": sess.error,
            })
        return {"session": config.root.name,
                "traces": list_traces(config.traces_root),
                "experiments": entries}

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

    @app.get("/api/experiments/{exp_id}/couch-steps")
    def couch_steps(exp_id: str):
        sess = get_session(exp_id)
        if not sess.has_couch_shifts:
            raise HTTPException(404, f"{exp_id} has no couchShifts.txt")
        key = (config.vendor, "couch", exp_id)
        if key not in app.state.cache:
            entry = load_state(config.root).get(exp_id)
            app.state.cache[key] = build_couch_steps_payload(
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
        state = update_entry(config.root, exp_id, body.entry())
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
