# KIM QA Analysis

A desktop tool for KIM (Kilovoltage Intrafraction Monitoring) motion-management QA.
Point it at a results folder and it discovers every session, classifies it
(static localisation, dynamic motion trace, or interrupted acquisition), and
serves an interactive browser overlay that compares KIM's reported marker
positions against a known ground truth — a robot / HexaMotion trajectory, or a
**baseline KIM acquisition** for software-version QA — and reports the per-axis
tracking error that decides pass or fail.

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
   interrupt; motion sessions auto-match their HexaMotion trace by folder name
   when the naming convention fits — nothing requires it. The **ground truth**
   dropdown lists every trace file under `Motion traces` (HexaMotion or robot
   format, auto-detected) plus baseline KIM logs from `Baselines/`. When a
   session folder holds several KIM logs, a **test trace** dropdown chooses
   which one is the primary; the others overlay as legend toggles, each with
   its own time offset.
2. **Align**: the time offset is auto-fitted by RMSE on the ground truth's most
   active axis. Refine it with the slider and nudge buttons.
3. **Select ranges** by dragging on a panel; the per-axis metrics
   (mean, SD, 5th and 95th percentiles, plus 3D) update live.
4. **Save**: writes `overlay.png` into the session folder, persists the tuned
   state, and regenerates a combined `summary.md` at the root.

A dynamic session passes when `|mean| <= 1 mm` and `SD <= 2 mm` per axis.

## Compare against a baseline KIM trace

For RTF software-version QA, put baseline acquisitions in a `Baselines/` folder
at the results root (one subfolder per baseline, holding its KIM log) and pick
the baseline from the ground-truth dropdown. The comparison works exactly like
a motion-trace overlay: same metrics, same pass criterion. Logs with 1–3+
markers are averaged into a centroid trajectory on both sides, the baseline's
own couch shifts are removed, and no centroid file is needed (the shared
centroid cancels in the residuals).

Same-fraction replays carry processing-speed-warped time columns that no single
time shift can align — click **gantry remap** to place the baseline on the test
run's timebase via the shared gantry angle instead. The remap is recorded in
`summary.md` as "(gantry-remapped)".

## What it reads

The app parses standard KIM session folders live; nothing needs pre-processing.
Point it at one results root containing a folder per session, with the
ground-truth traces in a `Motion traces` folder alongside them:

```
D:\KIM\2026-06-23\                          <- the results root you pick at launch
├─ PHANTOM_ROBOT_Centroid.txt               <- shared centroid file (a session-local copy overrides it)
├─ Motion traces\                           <- ground-truth traces (any nesting inside)
│  └─ hexamotion-prostate\t_Prostate_Continuous_Drift.txt
├─ Baselines\                               <- baseline KIM acquisitions (ground truth for version QA)
│  └─ 2026_06_17-pat03\MarkerLocationsGA_CouchShift_0.txt
├─ Prostate-Continuous-interrupt, ...\      <- one folder per session; the name picks the trace
│  ├─ MarkerLocationsGA_CouchShift_0.txt       primary log: positions + gantry (_1, _2, ... after interrupts)
│  ├─ MarkerLocations_CouchShift_0.txt         fallback when the GA log is absent
│  ├─ couchShifts.txt                          optional - interrupt sessions
│  ├─ KIM-KV\                                  optional - kV frames for hover preview
│  └─ kim-log-pdf480\                          optional - extra KIM log, overlaid as a legend toggle
└─ lung-typical, ...\
```

Session folder names drive the automatic trace match: a name containing e.g.
`prostate` + `erratic` is matched (case-insensitively, spaces ignored) to
`t_Prostate_Erratic.txt`, searched anywhere under `Motion traces`; unmatched
folders open as static until a ground truth is picked in the app. A different
traces location can be given with `--traces-root`, and a different baselines
location with `--baselines-root`.

Any immediate subfolder of a session that holds its own KIM log — recognised by
contents, not by name — is overlaid as a legend toggle with its own time
offset, and can be promoted to the primary trace via the "test trace" dropdown.
A log nested deeper (e.g. inside `KIM-KV/`) is not picked up; move it up to the
session root to have it plotted.

| Path | Purpose |
| --- | --- |
| `MarkerLocationsGA_CouchShift_*.txt` | KIM trajectory logs, primary source (positions + gantry). |
| `MarkerLocations_CouchShift_*.txt` | Fallback trajectory logs (same marker data, no gantry). |
| `*centroid*.txt` (optional) | 1–3 seed/marker lines + isocentre, in cm. Per session or shared at the root; the expected centroid offset from iso is subtracted before analysis (all-zero file for a marker at isocentre). Absent = expected offset 0, fine for baseline comparisons. |
| `couchShifts.txt` (optional) | Commanded couch movements (VRT, LNG, LAT). |
| `KIM-KV/` (optional) | kV frames, shown on hover behind each detection. |
| any subfolder with a KIM log (optional) | Extra run (offline reprocess, other RTF version, ...), overlaid as a legend toggle or promoted to the primary trace. Must be an immediate child of the session folder. |
| `Motion traces/` | Ground-truth traces: HexaMotion 3-column, or robot files (whitespace or comma-delimited, explicit timestamps) — every `*.txt` is selectable, format auto-detected. |
| `Baselines/<name>/` | Baseline KIM acquisitions, selectable as ground truth. |

Coordinate convention: centroid files use `(X, Y, Z)` in cm; the app works
internally in LR/SI/AP millimetres.

## Also here

An interactive [kV imaging simulator](https://kkaan.github.io/kim-qa/kv-simulator.html)
visualising depth-dependent magnification, geometric penumbra, and divergent
beam geometry, with adjustable SAD, SID, focal spot, and gantry angle.
