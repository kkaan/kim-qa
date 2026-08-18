"""_overlay_state.json persistence + summary.md regeneration.

State schema, one entry per session id:
    {"offset": float, "ranges": [[lo, hi], ...], "y_range": float | None,
     "hex_override": str | None, "offset_origin": str,
     "x_range": [lo, hi] | None, "offline_offsets": {folder: float} | None}
"x_range" is the persisted time-axis zoom in true (uncompressed) time, or null
for the default view. "offline_offsets" maps each offline overlay's source
folder name to its own time offset in seconds (independent of the primary run's
offset). Unknown keys written by other tools are preserved on update.

A reserved top-level "_config" entry holds per-root settings:
{"vendor": "Elekta" | "Varian", "centroid_file": str | None}. Session ids are
folder names and discovery skips "_"-prefixed folders, so the key can never
collide with a session.
"""
import json
from pathlib import Path

import numpy as np

from kim_qa.metrics import overlay_metrics_table, overlay_residuals
from kim_qa.version import __version__
from .config import VENDORS
from .discovery import Session
from .payloads import build_overlay_payload, expected_centroid, hex_time_axis

STATE_FILENAME = "_overlay_state.json"
SUMMARY_FILENAME = "summary.md"
CONFIG_KEY = "_config"


def load_state(root: Path) -> dict:
    path = Path(root) / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def update_entry(root: Path, session_id: str, entry: dict,
                 drop: tuple[str, ...] = ()) -> dict:
    state = load_state(root)
    merged = dict(state.get(session_id, {}))
    merged.update(entry)
    for key in drop:               # forget stale keys (e.g. an offset fit to a
        merged.pop(key, None)      # trace that has just been replaced)
    state[session_id] = merged
    (Path(root) / STATE_FILENAME).write_text(
        json.dumps(state, indent=2), encoding="utf-8")
    return state


def load_vendor(root: Path) -> str | None:
    cfg = load_state(root).get(CONFIG_KEY)
    vendor = cfg.get("vendor") if isinstance(cfg, dict) else None
    return vendor if vendor in VENDORS else None


def save_vendor(root: Path, vendor: str) -> None:
    update_entry(root, CONFIG_KEY, {"vendor": vendor})


def load_centroid_file(root: Path) -> str | None:
    """Manually chosen centroid filename for this root, or None for auto."""
    cfg = load_state(root).get(CONFIG_KEY)
    name = cfg.get("centroid_file") if isinstance(cfg, dict) else None
    return name or None


def save_centroid_file(root: Path, name: str | None) -> None:
    """Persist the manual pick; None/"" drops back to auto-detection."""
    update_entry(root, CONFIG_KEY, {"centroid_file": name or None})


def _fail_mean(v: float) -> bool:
    return abs(v) > 1.0


def _fail_std(v: float) -> bool:
    return v > 2.0


def _red(s: str) -> str:
    return f'<span style="color:#c0392b">{s}</span>'


def _hex_arrays(payload: dict, entry: dict):
    """Ground-truth arrays from the payload (fixed-dt hexamotion or
    irregular-t baseline KIM), or a flat-zero stand-in spanning the primary
    KIM run when the session has no ground truth."""
    if "hex" in payload:
        hx = payload["hex"]
        return hex_time_axis(hx), hx["lr"], hx["si"], hx["ap"]
    t = np.asarray(payload["kim"]["t"], float)
    off = float(entry.get("offset", 0.0))
    hex_t = np.array([t[0] + off - 1.0, t[-1] + off + 1.0])
    zeros = np.zeros(2)
    return hex_t, zeros, zeros, zeros


def _payload_metrics(payload: dict, entry: dict):
    kim = payload["kim"]
    hex_t, hlr, hsi, hap = _hex_arrays(payload, entry)
    res = overlay_residuals(kim["t"], kim["lr"], kim["si"], kim["ap"],
                            hex_t, hlr, hsi, hap,
                            float(entry.get("offset", 0.0)),
                            entry.get("ranges", []))
    return res, overlay_metrics_table(res)


def _offline_metrics(payload: dict, entry: dict) -> list:
    """(overlay, offset_used, res, rows) per offline kim-log* overlay, at its
    own saved offset or the primary run's when none is saved."""
    out = []
    overlays = payload.get("kim_offline") or []
    if overlays:
        hex_t, hlr, hsi, hap = _hex_arrays(payload, entry)
        for ov in overlays:
            off = ov.get("offset")
            off = float(entry.get("offset", 0.0)) if off is None else float(off)
            res = overlay_residuals(ov["t"], ov["lr"], ov["si"], ov["ap"],
                                    hex_t, hlr, hsi, hap, off,
                                    entry.get("ranges", []))
            out.append((ov, off, res, overlay_metrics_table(res)))
    return out


def _overview_cells(res, rows) -> list[str]:
    """mean±std cells for the overview table, failing axes wrapped in red."""
    if res.n < 2:
        return ["n<2"] * 4
    cells = []
    for r in rows:
        mean_s = f"{r['mean']:+.2f}"
        std_s = f"{r['std']:.2f}"
        if r["name"] != "3D":
            if _fail_mean(r["mean"]):
                mean_s = _red(mean_s)
            if _fail_std(r["std"]):
                std_s = _red(std_s)
        cells.append(f"{mean_s}±{std_s}")
    return cells


def _detail_table(rows) -> list[str]:
    """Per-axis detail table lines, failing axes wrapped in red."""
    lines = ["| Axis | Mean (mm) | Std (mm) | p5 (mm) | p95 (mm) |",
             "|---|---|---|---|---|"]
    for r in rows:
        mean_s = f"{r['mean']:+.3f}"
        std_s = f"{r['std']:.3f}"
        if r["name"] != "3D":
            if _fail_mean(r["mean"]):
                mean_s = _red(mean_s)
            if _fail_std(r["std"]):
                std_s = _red(std_s)
        lines.append(f"| {r['name']} | {mean_s} | "
                     f"{std_s} | {r['p5']:+.3f} | {r['p95']:+.3f} |")
    return lines


def regenerate_summary(root: Path, sessions: list, vendor: str) -> Path:
    root = Path(root)
    state = load_state(root)
    lines = [f"# {root.name} - overlay results (vendor={vendor})", "",
             f"Generated by KIM-QA-Server {__version__}", ""]
    lines.append("| Folder | Type | Offset (s) | # Ranges | "
                 "LR mean±std | SI mean±std | AP mean±std | 3D mean±std |")
    lines.append("|---|---|---|---|---|---|---|---|")

    details = []
    for sess in sessions:
        entry = state.get(sess.id)
        if entry is None or sess.error:
            continue
        payload = build_overlay_payload(sess, vendor, entry)
        res, rows = _payload_metrics(payload, entry)
        cells = _overview_cells(res, rows)
        lines.append(
            f"| {sess.id} | {sess.kind} | {float(entry.get('offset', 0)):+.2f} | "
            f"{len(entry.get('ranges', []))} | "
            f"{cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
        offline = _offline_metrics(payload, entry)
        for ov, off, ores, orows in offline:
            ocells = _overview_cells(ores, orows)
            lines.append(
                f"| {sess.id} / {ov['label']} | offline | {off:+.2f} | "
                f"{len(entry.get('ranges', []))} | "
                f"{ocells[0]} | {ocells[1]} | {ocells[2]} | {ocells[3]} |")
        details.append((sess, entry, res, rows, offline))

    lines.append("")
    for sess, entry, res, rows, offline in details:
        lines.append(f"## {sess.id}")
        lines.append("")
        if (sess.folder / "overlay.png").exists():
            lines.append(f"![overlay]({sess.id}/overlay.png)")
            lines.append("")
        if sess.baseline_dir is not None:
            hex_label = f"baseline {sess.baseline_dir.name}"
            if entry.get("gantry_remap"):
                hex_label += " (gantry-remapped)"
        elif sess.hex_file:
            hex_label = sess.hex_file.name
        else:
            hex_label = "(none, flat-zero)"
        lines.append(f"- **Type:** {sess.kind}")
        lines.append(f"- **Ground truth:** {hex_label}")
        if sess.centroid_file is not None:
            cent = expected_centroid(sess)
            lines.append(
                f"- **Centroid:** {cent['file']} (expected offset subtracted: "
                f"LR {cent['lr']:+.2f}, SI {cent['si']:+.2f}, "
                f"AP {cent['ap']:+.2f} mm)")
        else:
            lines.append("- **Centroid:** none (offset 0)")
        lines.append(f"- **Time offset:** {float(entry.get('offset', 0)):+.2f} s")
        lines.append(f"- **Ranges:** {len(entry.get('ranges', []))} "
                     f"(n = {res.n})")
        lines.append("")
        if res.n >= 2:
            lines.extend(_detail_table(rows))
            lines.append("")
        for ov, off, ores, orows in offline:
            saved = ov.get("offset") is not None
            lines.append(f"### Offline: {ov['label']}")
            lines.append("")
            lines.append(f"- **Source folder:** {ov['folder']}")
            lines.append(f"- **Time offset:** {off:+.2f} s "
                         f"({'independent' if saved else 'follows primary'})")
            lines.append(f"- **Samples:** n = {ores.n}")
            lines.append("")
            if ores.n >= 2:
                lines.extend(_detail_table(orows))
                lines.append("")
    out = root / SUMMARY_FILENAME
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
