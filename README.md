# KIM QA Analysis

A desktop tool for KIM (Kilovoltage Intrafraction Monitoring) motion-management QA.
Point it at a results folder and it discovers every session, classifies it
(static localisation, dynamic motion trace, or interrupted acquisition), and
serves an interactive browser overlay that compares KIM's reported marker
positions against the known robot / HexaMotion trajectory and reports the
per-axis tracking error that decides pass or fail.

**Landing page:** https://kkaan.github.io/kim-qa/

## Download

Grab the standalone Windows executable from the
**[latest release](https://github.com/kkaan/kim-qa/releases/latest)**: download
`KIM-QA-Analysis-Windows.zip`, extract, and run `KIM-QA-Server.exe`. No installer
and no Python needed. Your browser opens the app automatically.

```bash
KIM-QA-Server.exe --root "D:\KIM\2026-06-23"
```

Omit `--root` to pick the folder from a dialog. Add `--vendor Varian` for Varian
machines (flips the vertical-to-AP couch-shift sign; default Elekta). The vendor
choice persists per results root, so the flag can be omitted on later runs.
`--version` prints which release you are running.

## Run from source

Requires Python 3.11+ and the [uv](https://docs.astral.sh/uv/) package manager.

```bash
uv sync --extra server
uv run python -m kim_qa.server --root <results root>
```

## Using the app

1. **Pick a session** from the sidebar. It is classified static, motion, or
   interrupt; motion sessions auto-match their HexaMotion trace by folder name.
2. **Align**: the time offset is auto-fitted by RMSE. Refine it with the slider
   and nudge buttons.
3. **Select ranges** by dragging on a panel; the per-axis metrics
   (mean, SD, 5th and 95th percentiles, plus 3D) update live.
4. **Save**: writes `overlay.png` into the session folder, persists the tuned
   state, and regenerates a combined `summary.md` at the root.

A dynamic session passes when `|mean| <= 1 mm` and `SD <= 2 mm` per axis.

## What it reads

The app parses standard KIM session folders live; nothing needs pre-processing.
Point it at one results root containing a folder per session, with the
ground-truth traces in a `Motion traces` folder alongside them:

```
D:\KIM\2026-06-23\                          <- the results root you pick at launch
├─ PHANTOM_ROBOT_Centroid.txt               <- shared centroid file (a session-local copy overrides it)
├─ Motion traces\                           <- ground-truth traces (any nesting inside)
│  └─ hexamotion-prostate\t_Prostate_Continuous_Drift.txt
├─ Prostate-Continuous-interrupt, ...\      <- one folder per session; the name picks the trace
│  ├─ MarkerLocationsGA_CouchShift_0.txt       primary log: positions + gantry (_1, _2, ... after interrupts)
│  ├─ MarkerLocations_CouchShift_0.txt         fallback when the GA log is absent
│  ├─ couchShifts.txt                          optional - interrupt sessions
│  ├─ KIM-KV\                                  optional - kV frames for hover preview
│  └─ kim-log-pdf480\                          optional - offline reprocessing, overlaid as a legend toggle
└─ lung-typical, ...\
```

Session folder names drive classification: a name containing e.g. `prostate` +
`erratic` is matched (case-insensitively, spaces ignored) to
`t_Prostate_Erratic.txt`, searched anywhere under `Motion traces`; unmatched
folders are treated as static. The match can be overridden per session in the
app, and a different traces location can be given with `--traces-root`.

Offline-reprocessed runs are overlaid as legend toggles when their folder name
starts with `kim-log` (e.g. `kim-log-pdf480`) and holds its own KIM log. Unlike
the primary log, these overlay folders must be **immediate children of the
session folder** — one nested deeper (e.g. inside `KIM-KV/`) is not picked up.
Move it up to the session root to have it plotted.

| Path | Purpose |
| --- | --- |
| `MarkerLocationsGA_CouchShift_*.txt` | KIM trajectory logs, primary source (positions + gantry). |
| `MarkerLocations_CouchShift_*.txt` | Fallback trajectory logs (same marker data, no gantry). |
| `*centroid*.txt` (required) | 1–3 seed/marker lines + isocentre, in cm. Per session or shared at the root; the expected centroid offset from iso is subtracted before analysis (all-zero file for a marker at isocentre). |
| `couchShifts.txt` (optional) | Commanded couch movements (VRT, LNG, LAT). |
| `KIM-KV/` (optional) | kV frames, shown on hover behind each detection. |
| `kim-log-*/` (optional) | Offline-reprocessed run, overlaid as a legend toggle. Must be an immediate child of the session folder. |
| `Motion traces/` (motion sessions) | HexaMotion / 6DoF-robot ground-truth traces. |

Coordinate convention: centroid files use `(X, Y, Z)` in cm; the app works
internally in LR/SI/AP millimetres.

## Also here

An interactive [kV imaging simulator](https://kkaan.github.io/kim-qa/kv-simulator.html)
visualising depth-dependent magnification, geometric penumbra, and divergent
beam geometry, with adjustable SAD, SID, focal spot, and gantry angle.
