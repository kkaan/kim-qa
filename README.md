# KIM QA Analysis

A browser-based application for analyzing KIM (Kilo-voltage Imaging for Motion management) QA
data against HexaMotion/6DoF-robot ground truth. Point it at a results root and it discovers
every session folder, classifies it (static, motion, or interrupted acquisition), and serves an
interactive overlay view for QA sign-off.

Public landing page: https://kkaan.github.io/kim-qa/

## Download

Grab the standalone Windows executable from the
**[latest release](https://github.com/kkaan/kim-qa/releases/latest)** -
download `KIM-QA-Analysis-Windows.zip`, extract, run `KIM-QA-Server.exe`. No install, no
Python.

## Quick start

Run from source:
```bash
uv sync --extra server
uv run python -m kim_qa.server --root <results root>
```

Or run the built executable (`python_app/dist/KIM-QA-Server.exe`):
```bash
KIM-QA-Server.exe --root <results root>
```

Omit `--root` to pick the folder from a dialog. Use `--vendor Varian` for Varian machines
(flips the vertical-to-AP couch-shift sign; default Elekta). The vendor choice persists
per results root (in `_overlay_state.json`), so after the first run — or after switching
vendor in the UI — the flag can be omitted. `--version` prints the build's release tag
(local/source builds report `dev`).

Other flags: `--traces-root` (ground-truth traces folder; default `<root>/Motion traces`),
`--baselines-root` (baseline KIM-log folders; default `<root>/Baselines`), `--port`
(default 0 = a random free port, printed at startup — pass `--port 8765` for the webapp
dev proxy), `--no-browser`.

Verified end-to-end against real Bluey phantom data (metrics cross-checked against the
canonical Python implementation).

## Features

- **Session sidebar** - batch discovery of every session under the root, with kind badges
  (static / motion / interrupt / kV), saved-state checkmarks, and greyed rows for unparsable
  folders. New folders appear on browser refresh.
- **Overlay view** - three stacked LR/SI/AP panels (default ±10 mm, editable), KIM detections
  vs the ground truth, time-offset slider with nudge buttons and RMSE auto-fit (on the ground
  truth's most active axis, with a low-confidence warning when the fit cannot localise),
  drag-to-select analysis ranges, live metrics card (mean/std/p5/p95 + 3D), error-residual
  mode, and a gantry-angle top axis. Pass/fail per axis: |mean| ≤ 1 mm and SD ≤ 2 mm;
  out-of-tolerance values are flagged red in `summary.md`. Time-axis zoom persists per session.
- **Any ground truth** - the "ground truth" picker lists every `*.txt` under the traces root
  (HexaMotion 3-column traces, whitespace or comma-delimited robot files with explicit
  timestamps — format auto-detected) plus **baseline KIM logs** from the `Baselines/` folder,
  for comparing a reprocessed/new-RTF-version log against a baseline acquisition. Trajectories
  with 1–3+ markers are averaged into a centroid trajectory on both sides.
- **Gantry remap** - same-fraction replays carry processing-speed-warped time columns that no
  single time shift can align; the "gantry remap" button (shown when the ground truth is a
  baseline and both logs carry gantry angles) places the baseline on the test run's timebase
  via the shared gantry angle. Recorded as "(gantry-remapped)" in `summary.md`.
- **Test-trace picker** - when a session folder holds several KIM logs (any folder holding a
  log counts — no naming convention), a "test trace" dropdown chooses which one is the primary
  trace; the others overlay as legend toggles, each with its own persisted time offset.
- **Interrupt handling** - multi-segment acquisitions are stitched with vendor-signed couch
  corrections; dead-time gaps compress visually with per-panel couch-delta annotations. The
  orange trace is KIM as recorded (the quantity the metrics describe); the shift-removed
  counterfactual - where the target would have been had the couch not moved - overlays in
  translucent grey by default ("Hide shift-removed" toggles it off).
- **kV frame preview** - hovering a KIM point shows the actual kV crop with crosshair and
  detected-marker ring (when a `KIM-KV/` folder is present).
- **Centroid correction** - a centroid file (1-3 seeds/markers + isocentre) sets the expected
  centroid offset from iso, subtracted before analysis; the applied file is recorded in the UI
  and `summary.md`. Without one the expected offset falls back to zero — correct for
  test-vs-baseline comparisons, where the shared centroid cancels in the residuals.
- **QA outputs** - Save writes `overlay.png` per session, persists tuned offsets/ranges to
  `_overlay_state.json`, and regenerates a combined `summary.md` with canonical Python
  metrics, stamped with the app version that produced it.

## Installation

### Requirements
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

1. Install [uv](https://docs.astral.sh/uv/). It manages the Python interpreter, the
   virtual environment, and dependencies for you — there is no separate `pip install` step.
2. From the repo root, sync the environment:
   ```bash
   uv sync --extra server
   ```
   This reads `pyproject.toml`, creates a `.venv/` if one doesn't exist, and installs the
   exact versions pinned in `uv.lock` (a reproducible install). The core dependencies
   (`numpy`, `pandas`, `scipy`) install the `kim_qa` analysis package; `--extra server` adds
   the web server dependencies (`fastapi`, `uvicorn`, `pillow`). Omit the flag if you only
   need the analysis library. Use `--extra tools` for the matplotlib-based scripts in
   `tools/`.

Frontend development additionally needs Node 20+: `cd webapp && npm install && npm run dev`
(the Vite dev server proxies `/api` to `127.0.0.1:8765`).

## Usage

1. **Launch** the server against a results root (see Quick start); your browser opens the UI.
2. **Pick a session** from the sidebar. Motion sessions auto-match their HexaMotion trace by
   folder name when the naming convention fits; the "ground truth" dropdown overrides with any
   trace file under the traces root or any baseline KIM log under `Baselines/`. A "test trace"
   dropdown appears when the session holds several KIM logs.
3. **Align**: the time offset is auto-fitted by RMSE on the ground truth's most active axis;
   refine with the slider and nudge buttons. For same-fraction baseline comparisons, toggle
   "gantry remap" instead — it aligns via the shared gantry angle and needs no offset.
4. **Select ranges** by dragging on a panel; the metrics card updates live.
5. **Save**: writes `overlay.png` into the session folder, persists the tuned state, and
   regenerates the root-level `summary.md`.

## Application Architecture

### Main Components

- **`src/kim_qa/server/`**: FastAPI app - session discovery, live `OverlayPayload`
  assembly (vendor-signed couch corrections, raw-timebase interrupts), on-the-fly
  kV frame crops, state persistence, and `summary.md` generation.

- **`webapp/`**: Vite + React + Plotly frontend - vendored `kim-overlay`
  widget from the presentation deck, recomputing metrics client-side (`webapp/src/lib.ts`,
  kept numerically identical to the Python metrics and guarded by a golden-file test).

- **`src/kim_qa/`**: Installable analysis package (imported by the server and tools)
  - `io/marker_locations.py` — `read_kim_segments()`: canonical trajectory reader (GA logs
    by header name, multi-marker averaging, non-GA positional fallback)
  - `io/centroid.py` — `parse_centroid_file()`: Extract seed and isocenter coordinates
  - `io/trajectory.py` — `parse_trajectory_file()`: Process KIM trajectory data
  - `io/couch.py` — `parse_couch_shifts()`: Extract couch shift values (Elekta/Varian AP-sign logic)
  - `io/kim_batch.py` — `parse_kim_data()`: Parse multiple KIM data files
  - `io/robot.py` — `parse_robot_file()`: Load robot trace data
  - `io/hexamotion.py` — `parse_hexamotion_trace()`: HexaMotion / 6DoF-robot ground-truth traces (3-column commanded `trajectory` traces and 7-column `_robot` traces)
  - `io/ground_truth.py` — `parse_ground_truth_file()`: auto-detecting ground-truth loader (HexaMotion trace or comma-delimited robot file)
  - `coords.py` — coordinate transforms (centroid → LR/SI/AP in mm)
  - `metrics.py` — `calculate_metrics()`: Compute statistical metrics
  - `interrupt.py` — `process_interrupt_data()`: Align and compare KIM vs Robot data
  - `dynamic.py` — `align_trajectory_to_truth()`: KIM vs moving ground-truth alignment + deviation metrics

### Data Flow

**Static Analysis:**
```
Centroid File → Expected Centroid Calculation
                        ↓
Trajectory File → Deviation Calculation → Metrics → Results
```

**Interrupt Analysis:**
```
Trajectory Folder → KIM Data Parsing
Couch Shifts File → Shift Extraction        → Data Alignment → Comparison → Metrics
Ground-truth trace (HexaMotion/robot) → Parsing
```

## File Formats

### Folder layout

The app parses standard KIM session folders live; nothing needs pre-processing. Point it
at one results root containing a folder per session, with the ground-truth traces in a
`Motion traces` folder alongside them:

```
D:\KIM\2026-06-23\                          <- the results root you pass to --root
├─ PHANTOM_ROBOT_Centroid.txt               <- shared centroid file (a session-local copy overrides it)
├─ Motion traces\                           <- ground-truth traces (any nesting inside; --traces-root overrides)
│  └─ hexamotion-prostate\t_Prostate_Continuous_Drift.txt
├─ Baselines\                               <- baseline KIM acquisitions (--baselines-root overrides)
│  └─ 2026_06_17-pat03\MarkerLocationsGA_CouchShift_0.txt
├─ Prostate-Continuous-interrupt, ...\      <- one folder per session; the name picks the trace
│  ├─ MarkerLocationsGA_CouchShift_0.txt       primary log: positions + gantry (_1, _2, ... after interrupts)
│  ├─ MarkerLocations_CouchShift_0.txt         fallback when the GA log is absent
│  ├─ couchShifts.txt                          optional - interrupt sessions
│  ├─ KIM-KV\                                  optional - kV frames for hover preview
│  └─ kim-log-pdf480\                          optional - extra KIM log, overlaid as a legend toggle
└─ lung-typical, ...\
```

Session folder names drive the automatic trace match: a name containing e.g. `prostate` +
`erratic` is matched (case-insensitively, spaces ignored) to `t_Prostate_Erratic.txt`,
searched anywhere under `Motion traces`; unmatched folders open as static until a ground
truth is picked in the app — nothing *requires* the naming convention. The KIM log may sit
nested deeper inside the session folder (it is found recursively), and folders starting
with `_` or `.` are skipped.

Any immediate subfolder of a session that holds its own KIM log — recognised by contents,
not by name (`kim-log-pdf480`, `log-version-125`, `reprocessed with fix`, ...) — is
overlaid as a legend toggle with its own persisted time offset, and can be promoted to the
primary trace via the "test trace" dropdown. A log nested deeper (e.g. inside `KIM-KV\`)
is not picked up as an overlay; move it up to the session root to have it plotted.

### Input Files

- **Centroid Files**: any `*centroid*.txt` with 1–3 seed/marker lines plus the isocentre
  (cm). Optional (session folder preferred, results root fallback); the seed-centroid
  offset from iso is subtracted from all trajectories. Without one the expected offset is
  zero — fine for test-vs-baseline comparisons where the shared centroid cancels. Use an
  all-zero file for a marker at isocentre.
- **KIM Trajectory Logs**: `MarkerLocationsGA_CouchShift_*.txt` (primary: positions +
  gantry, marker columns resolved by header name) with `MarkerLocations_CouchShift_*.txt`
  as fallback — both carry identical marker rows. 1–3+ markers are averaged into a
  centroid trajectory.
- **Couch Shifts**: `couchShifts.txt` with VRT, LNG, LAT shifts
- **Ground-truth traces**: format auto-detected — HexaMotion 3-column trajectory (20 ms
  step, optional header), whitespace ≥4-column robot files (col 0 = time), or
  comma-delimited robot files. Every `*.txt` under the traces root is selectable.
- **Baseline KIM logs**: folders under `Baselines\` holding a KIM log; selectable as
  ground truth from the same dropdown. The baseline's own `couchShifts.txt` is removed
  and the session's centroid subtracted before comparison.

### Output Files

- **`overlay.png`** (per session): the saved overlay figure
- **`_overlay_state.json`** (root): persisted offsets, ranges, and per-session settings
  (ground-truth/test-trace picks, gantry remap, zoom, per-overlay offsets, vendor)
- **`summary.md`** (root): combined per-axis + 3D statistics for every reviewed session
  and offline overlay, out-of-tolerance values flagged red

## Technical Details

- **UI**: React + Plotly in the browser, served by FastAPI/uvicorn on localhost
- **Data Processing**: NumPy/Pandas in Python; metrics mirrored in TypeScript for live updates
- **Coordinate System**: LR (Left-Right), SI (Superior-Inferior), AP (Anterior-Posterior)

## Building the executable

To build the executable locally:

1. Build the frontend, then sync the environment with server and dev extras:
```bash
cd webapp && npm ci && npm run build && cd ..
uv sync --extra server --extra dev
```

2. Build using the spec file (from the `python_app` directory, matching CI):
```bash
cd python_app
uv run pyinstaller KIM-QA-Server.spec
```

3. The executable will be in `python_app/dist/KIM-QA-Server.exe`

## Interactive kV Imaging Simulator

An interactive browser-based simulator demonstrating depth-dependent magnification, geometric penumbra, and divergent beam geometry in kV imaging:

**[Launch kV Imaging Simulator](https://kkaan.github.io/kim-qa/kv-simulator.html)**

Features adjustable SAD, SID, focal spot size, gantry angle, and target translation controls with real-time BEV scene and detector projection views.
