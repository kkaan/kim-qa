"""Session discovery and static/motion classification.

A folder under the results root is a session when it contains
MarkerLocationsGA_CouchShift_0.txt (or the non-GA fallback; searched
recursively, as some sessions nest it). Name-substring matching against
PAIR_MAP assigns the hexamotion ground-truth trace; anything unmatched is
static (flat-zero ground truth).
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kim_qa.io.centroid import parse_centroid_file
from kim_qa.io.marker_locations import (
    FALLBACK_KIM_FILENAME, KIM_FILENAME, read_kim_segments,
)
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



# Sentinel prefix marking a hex_override that names a baseline KIM-log folder
# (under baselines_root) instead of a hexamotion trace file. ":" cannot occur
# in a filename, so the sentinel never collides with real trace overrides.
BASELINE_PREFIX = "baseline:"

@dataclass
class Session:
    id: str
    folder: Path
    kim_file: Path
    kind: str                      # "motion" | "static"
    hex_file: Optional[Path]
    has_frames: bool
    has_couch_shifts: bool
    centroid_file: Optional[Path] = None
    error: Optional[str] = None
    offline_dirs: list = field(default_factory=list)   # extra KIM-log folders
    baseline_dir: Optional[Path] = None    # KIM-log folder used as ground truth
    log_dirs: list = field(default_factory=list)       # test-trace candidates


def _holds_kim_log(folder: Path) -> bool:
    return ((folder / KIM_FILENAME).exists()
            or (folder / FALLBACK_KIM_FILENAME).exists()
            or next(folder.rglob(KIM_FILENAME), None) is not None
            or next(folder.rglob(FALLBACK_KIM_FILENAME), None) is not None)


def _direct_kim_log(folder: Path) -> Optional[Path]:
    for name in (KIM_FILENAME, FALLBACK_KIM_FILENAME):
        if (folder / name).exists():
            return folder / name
    return None


def find_log_dirs(folder: Path) -> list:
    """Candidate test-trace folders: the session folder itself when it holds a
    KIM log directly, plus every immediate subfolder holding one. Recognised by
    contents, not naming conventions."""
    out = [folder] if _direct_kim_log(folder) is not None else []
    for sub in sorted(folder.iterdir()):
        if (sub.is_dir() and not sub.name.startswith(("_", "."))
                and _holds_kim_log(sub)):
            out.append(sub)
    return out


def find_offline_dirs(folder: Path, primary_parent: Path) -> list:
    """Every candidate log folder except the one the primary (test) trace was
    read from — shown as toggleable overlays."""
    return [d for d in find_log_dirs(folder) if d != primary_parent]


def list_baselines(baselines_root: Path) -> list[str]:
    """Baseline candidates: immediate child folders of baselines_root that
    hold a KIM log, by name."""
    if not baselines_root.is_dir():
        return []
    return sorted(d.name for d in baselines_root.iterdir()
                  if d.is_dir() and _holds_kim_log(d))


def _norm(name: str) -> str:
    return name.lower().replace(" ", "")


def find_centroid_file(*folders: Optional[Path]) -> Optional[Path]:
    """First *.txt whose name contains 'centroid' (case-insensitive),
    searching each folder in order — so a session-local file wins over a
    shared one at the results root."""
    for base in folders:
        if base is None or not base.is_dir():
            continue
        cands = sorted(p for p in base.iterdir()
                       if p.is_file() and p.suffix.lower() == ".txt"
                       and "centroid" in p.name.lower())
        if cands:
            return cands[0]
    return None


def list_centroid_files(root: Path) -> list[str]:
    """Every *.txt directly under the results root, by name — the candidates
    offered for a manual pick. Naming conventions are not enforced (as with
    list_traces): roots hold centroid files under assorted names, and the
    auto-detect 'centroid'-substring rule is exactly what a manual pick is
    there to escape."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_file() and p.suffix.lower() == ".txt")


def resolve_centroid_override(root: Path, name: Optional[str]) -> Optional[Path]:
    """The manually chosen centroid file, or None to fall back to auto-detect.

    `name` is either a bare filename / relative path (resolved against the
    results root) or an absolute path anywhere on disk — centroid files are
    often kept in a shared folder beside the results root rather than inside
    it. A pick that no longer resolves (file moved, share offline) falls back
    to auto-detection rather than blanking the expected offset, matching how a
    stale hex_override is handled; POST /api/config rejects a bad path up
    front so the fallback only ever covers later breakage.
    """
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        path = Path(root) / path
    return path if path.is_file() else None


def find_trace(traces_root: Path, filename: str) -> Optional[Path]:
    if not traces_root.exists():
        return None
    for p in traces_root.rglob(filename):
        return p
    return None


def list_traces(traces_root: Path) -> list[str]:
    """Every *.txt under the traces root, by basename. Naming conventions are
    not enforced — robot files and arbitrarily named traces are selectable;
    the reader auto-detects the format."""
    if not traces_root.exists():
        return []
    return sorted({p.name for p in traces_root.rglob("*.txt") if p.is_file()})


def _classify(name: str, config: ServerConfig,
              override: Optional[str]) -> tuple[str, Optional[Path], Optional[Path]]:
    """Returns (kind, hex_file, baseline_dir). An override naming a baseline
    (``baseline:<folder>``) or trace that no longer resolves falls through to
    the PAIR_MAP name matching, same as no override."""
    if override and override.startswith(BASELINE_PREFIX):
        d = config.baselines_root / override[len(BASELINE_PREFIX):]
        if d.is_dir() and _holds_kim_log(d):
            return "motion", None, d
    elif override:
        p = find_trace(config.traces_root, override)
        if p is not None:
            return "motion", p, None
    key = _norm(name)
    for subs, trace_name in PAIR_MAP:
        if all(s in key for s in subs):
            p = find_trace(config.traces_root, trace_name)
            if p is not None:
                return "motion", p, None
            return "static", None, None   # matched but trace file missing
    return "static", None, None


def _pick_kim_file(folder: Path, log_dirs: list,
                   chosen: Optional[str]) -> Optional[Path]:
    """The primary (test) trace's log file. `chosen` names a candidate folder
    from log_dirs ("." = the session folder itself); unknown or absent falls
    back to the automatic direct-then-recursive search."""
    if chosen:
        for d in log_dirs:
            if chosen == ("." if d == folder else d.name):
                direct = _direct_kim_log(d)
                if direct is not None:
                    return direct
                for name in (KIM_FILENAME, FALLBACK_KIM_FILENAME):
                    nested = sorted(d.rglob(name))
                    if nested:
                        return nested[0]
    direct = _direct_kim_log(folder)
    if direct is not None:
        return direct
    for name in (KIM_FILENAME, FALLBACK_KIM_FILENAME):
        nested = sorted(folder.rglob(name))
        if nested:
            return nested[0]
    return None


def discover_sessions(config: ServerConfig,
                      overrides: Optional[dict] = None,
                      test_logs: Optional[dict] = None) -> list[Session]:
    overrides = overrides or {}
    out: list[Session] = []
    if not config.root.exists():
        return out
    # Per-root manual pick, applied to every session; None keeps auto-detect.
    centroid_pick = resolve_centroid_override(config.root, config.centroid_file)
    for folder in sorted(config.root.iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", ".")):
            continue
        if folder in (config.traces_root, config.baselines_root):
            continue
        log_dirs = find_log_dirs(folder)
        kim_file = _pick_kim_file(folder, log_dirs,
                                  (test_logs or {}).get(folder.name))
        if kim_file is None:
            continue
        kind, hex_path, baseline_dir = _classify(folder.name, config,
                                                 overrides.get(folder.name))
        sess = Session(
            id=folder.name,
            folder=folder,
            kim_file=kim_file,
            kind=kind,
            hex_file=hex_path,
            has_frames=(kim_file.parent / "KIM-KV").is_dir(),
            has_couch_shifts=(kim_file.parent / "couchShifts.txt").exists(),
            centroid_file=centroid_pick or find_centroid_file(
                kim_file.parent, folder, config.root),
            offline_dirs=find_offline_dirs(folder, kim_file.parent),
            baseline_dir=baseline_dir,
            log_dirs=log_dirs,
        )
        try:
            # Parse eagerly enough to surface unreadable folders in the UI.
            # A missing centroid file is allowed: expected offset falls back
            # to zero (correct for test-vs-baseline where it cancels).
            if sess.centroid_file is not None:
                parse_centroid_file(sess.centroid_file)
            read_kim_segments(kim_file.parent)
        except Exception as e:  # noqa: BLE001 - surfaced to the client
            sess.error = str(e)
        out.append(sess)
    return out
