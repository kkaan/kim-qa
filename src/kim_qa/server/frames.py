"""kV frame hover preview: per-point index + on-the-fly TIFF crops.

Recipe from the deck's tools/export_debug_frames.py: crop the central 256x256
region (top-left 384, 256) of the referenced KIM-KV TIFF and window it to
8-bit with lo = 2nd percentile of the crop, hi = crop max. PNGs are generated
per request and cached under the OS temp dir (never inside session folders).
"""
import csv
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from .discovery import Session

CROP_X0, CROP_Y0, CROP_SIZE = 384, 256, 256
_GA_RE = re.compile(r"^MarkerLocationsGA_CouchShift_(\d+)\.txt$")
_COLS = {
    "file": "Filename (of base frame in average framestack)",
    "t": "Time (sec)",
    "gantry": "Gantry",
    "frame": "Frame No",
    "mx": "Marker_0_X",
    "my": "Marker_0_Y",
}


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)


def _cache_dir(session: Session) -> Path:
    d = Path(tempfile.gettempdir()) / "kim-qa-frames" / slugify(session.id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ga_rows(folder: Path):
    """Concatenated GA data rows + column index map, or (None, None)."""
    files = sorted(
        ((int(_GA_RE.match(p.name).group(1)), p)
         for p in folder.iterdir() if _GA_RE.match(p.name)),
    )
    if not files:
        return None, None
    cols = None
    rows = []
    for _, fp in files:
        with open(fp, newline="", encoding="utf-8", errors="replace") as fh:
            file_rows = list(csv.reader(fh))
        if not file_rows:
            continue
        header = [c.strip() for c in file_rows[0]]
        if header and header[0].startswith("Frame"):
            if cols is None:
                cols = {k: header.index(v) for k, v in _COLS.items()}
            file_rows = file_rows[1:]
        rows.extend(file_rows)
    if cols is None:
        return None, None
    return rows, cols


def build_frame_index(session: Session):
    folder = session.kim_file.parent
    kv_dir = folder / "KIM-KV"
    if not kv_dir.is_dir():
        return None
    rows, cols = _ga_rows(folder)
    if rows is None:
        return None
    frames = []
    for i, row in enumerate(rows):
        fname = row[cols["file"]].strip()
        marker_x = int(float(row[cols["mx"]]))
        marker_y = int(float(row[cols["my"]]))
        entry = {
            "i": i,
            "file": Path(fname).stem + ".png",
            "frame": int(float(row[cols["frame"]])),
            "t": float(row[cols["t"]]),
            "gantry": float(row[cols["gantry"]]),
            "marker_x": marker_x,
            "marker_y": marker_y,
            "mx": marker_x - CROP_X0,
            "my": marker_y - CROP_Y0,
        }
        if not (kv_dir / fname).exists():
            entry["missing"] = True
        frames.append(entry)
    return {
        "experiment": session.id,
        "crop": {"x0": CROP_X0, "y0": CROP_Y0, "size": CROP_SIZE},
        "count": len(frames),
        "frames": frames,
    }


def _window_to_uint8(crop: np.ndarray) -> np.ndarray:
    c = crop.astype(np.float64)
    lo = float(np.percentile(c, 2))
    hi = float(c.max())
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((c - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def render_frame_png(session: Session, png_name: str):
    if "/" in png_name or "\\" in png_name or ".." in png_name:
        return None                              # path traversal guard
    out = _cache_dir(session) / png_name
    if out.exists():
        return out
    kv_dir = session.kim_file.parent / "KIM-KV"
    tiff = kv_dir / (Path(png_name).stem + ".tiff")
    if not tiff.exists():
        tiff = kv_dir / (Path(png_name).stem + ".tif")
        if not tiff.exists():
            return None
    arr = np.asarray(Image.open(tiff))
    crop = arr[CROP_Y0:CROP_Y0 + CROP_SIZE, CROP_X0:CROP_X0 + CROP_SIZE]
    Image.fromarray(_window_to_uint8(crop), mode="L").save(out)
    return out
