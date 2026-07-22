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
machines (flips the vertical-to-AP couch-shift sign; default Elekta).

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

| Path | Purpose |
| --- | --- |
| `MarkerLocationsGA_CouchShift_*.txt` | KIM trajectory logs, primary source (positions + gantry). |
| `MarkerLocations_CouchShift_*.txt` | Fallback trajectory logs (same marker data, no gantry). |
| `*centroid*.txt` (required) | 1–3 seed/marker lines + isocentre, in cm. Per session or shared at the root; the expected centroid offset from iso is subtracted before analysis (all-zero file for a marker at isocentre). |
| `couchShifts.txt` (optional) | Commanded couch movements (VRT, LNG, LAT). |
| `KIM-KV/` (optional) | kV frames, shown on hover behind each detection. |
| `Motion traces/` (motion sessions) | HexaMotion / 6DoF-robot ground-truth traces. |

Coordinate convention: centroid files use `(X, Y, Z)` in cm; the app works
internally in LR/SI/AP millimetres.

## Also here

An interactive [kV imaging simulator](https://kkaan.github.io/kim-qa/kv-simulator.html)
visualising depth-dependent magnification, geometric penumbra, and divergent
beam geometry, with adjustable SAD, SID, focal spot, and gantry angle.
