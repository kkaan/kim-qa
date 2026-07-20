"""Session discovery and static/motion classification.

A folder under the results root is a session when it contains
MarkerLocations_CouchShift_0.txt (searched one level deep, as some sessions
nest it). Name-substring matching against PAIR_MAP assigns the hexamotion
ground-truth trace; anything unmatched is static (flat-zero ground truth).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kim_qa.io.marker_locations import KIM_FILENAME, read_kim_segments
from .config import ServerConfig

# (folder-name substrings, trace filename). First match wins; substrings are
# matched case-insensitively against the space-stripped folder name.
# ("lung", "baselin") also catches the real-world "baselinshift" misspelling.
PAIR_MAP = [
    (("lung", "typical"), "t_Lung_Typical.txt"),
    (("lung", "baselin"), "t_Lung_Baseline_Shifts.txt"),
    (("lung", "predom"), "t_Lung_Predominantly_Left_Right.txt"),
    (("lung", "highfreq"), "t_Lung_High_Frequency.txt"),
    (("lung", "high_freq"), "t_Lung_High_Frequency.txt"),
    (("prostate", "continuous"), "t_Prostate_Continuous_Drift.txt"),
    (("prostate", "interrupt"), "t_Prostate_Continuous_Drift.txt"),
    (("prostate", "drift"), "t_Prostate_Continuous_Drift.txt"),
    (("prostate", "erratic"), "t_Prostate_Erratic.txt"),
    (("prostate", "highfreq"), "t_Prostate_High_Frequency.txt"),
    (("prostate", "high_freq"), "t_Prostate_High_Frequency.txt"),
    (("prostate", "stable"), "t_Prostate_Stable.txt"),
    (("liver", "cardiac"), "LiverTraj_BaselineWanderWithCardiac.txt"),
    (("liver", "breathhold"), "LiverTraj_LargeSIandAPWithBreathHold.txt"),
]

# Per-session offset-alignment axis override: use the axis with the most
# motion (lung-predominant is left-right dominant, so SI cannot localise it).
ALIGN_AXIS = [(("lung", "predom"), "LR")]


@dataclass
class Session:
    id: str
    folder: Path
    kim_file: Path
    kind: str                      # "motion" | "static"
    hex_file: Optional[Path]
    has_frames: bool
    has_couch_shifts: bool
    error: Optional[str] = None


def _norm(name: str) -> str:
    return name.lower().replace(" ", "")


def align_axis_for(name: str) -> str:
    key = _norm(name)
    for subs, axis in ALIGN_AXIS:
        if all(s in key for s in subs):
            return axis
    return "SI"


def find_trace(traces_root: Path, filename: str) -> Optional[Path]:
    if not traces_root.exists():
        return None
    for p in traces_root.rglob(filename):
        return p
    return None


def list_traces(traces_root: Path) -> list[str]:
    if not traces_root.exists():
        return []
    names = {p.name for pat in ("t_*.txt", "LiverTraj_*.txt")
             for p in traces_root.rglob(pat)}
    return sorted(names)


def _classify(name: str, traces_root: Path,
              override: Optional[str]) -> tuple[str, Optional[Path]]:
    if override:
        p = find_trace(traces_root, override)
        if p is not None:
            return "motion", p
    key = _norm(name)
    for subs, trace_name in PAIR_MAP:
        if all(s in key for s in subs):
            p = find_trace(traces_root, trace_name)
            if p is not None:
                return "motion", p
            return "static", None      # matched but trace file missing
    return "static", None


def discover_sessions(config: ServerConfig,
                      overrides: Optional[dict] = None) -> list[Session]:
    overrides = overrides or {}
    out: list[Session] = []
    if not config.root.exists():
        return out
    for folder in sorted(config.root.iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", ".")):
            continue
        if folder == config.traces_root:
            continue
        kim_file = folder / KIM_FILENAME
        if not kim_file.exists():
            nested = list(folder.rglob(KIM_FILENAME))
            if not nested:
                continue
            kim_file = nested[0]
        kind, hex_path = _classify(folder.name, config.traces_root,
                                   overrides.get(folder.name))
        sess = Session(
            id=folder.name,
            folder=folder,
            kim_file=kim_file,
            kind=kind,
            hex_file=hex_path,
            has_frames=(kim_file.parent / "KIM-KV").is_dir(),
            has_couch_shifts=(kim_file.parent / "couchShifts.txt").exists(),
        )
        try:
            # Parse eagerly enough to surface unreadable folders in the UI.
            read_kim_segments(kim_file.parent)
        except Exception as e:  # noqa: BLE001 - surfaced to the client
            sess.error = str(e)
        out.append(sess)
    return out
