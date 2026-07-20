# Webapp GUI revamp: real-data verification (Bluey 2026-06-23)

Verified against the real results root
`C:\Users\kankean.kandasamy\Repo\Staging02\Bluey_2026-06-23`, launched both via
`uv run python -m kim_qa.server --root ...` and the PyInstaller-built
`python_app/dist/KIM-QA-Server.exe`. All 59 backend tests
(`uv run pytest tests/ -v`, excluding `test_logic.py` which needs the
git-ignored `Lyrebird-Data/` fixture) and all 6 frontend tests
(`npm test` in `webapp/`) pass before and after this verification pass.

Verification method: the environment has no browser-automation package
installed (no Playwright/Selenium). A throwaway Chrome DevTools Protocol
driver script (headless Chrome, not committed) was used to click sidebar rows
and buttons and capture real screenshots of the running app, alongside direct
`GET`/`POST` calls against the live `/api/...` routes and small `uv run
python` snippets that call `kim_qa.metrics.overlay_residuals` /
`overlay_metrics_table` directly on payloads pulled from the running server,
so every numeric claim below is a live number from real data, not a read of
the source.

- [x] **Discovery**: all session folders listed; `Motion traces` excluded;
      liver/static/lung/prostate kinds correct; `lung-baselinshift`
      (misspelled) matched to `t_Lung_Baseline_Shifts.txt`.

      `GET /api/manifest` against the real root returned 8 sessions:
      `lung-highfrequency,...1510` / `lung-predominant,...1514` /
      `lung-typical,...1518` (all `motion`, matched to the correct
      `t_Lung_*.txt` trace), `Prostate-Continuous-interrupt,...1350` /
      `Prostate-Erratic,...1456` / `Prostate-HighFrequency,...1447` /
      `prostate-stable-end,...1633 reupload` (all `motion`, matched to the
      correct `t_Prostate_*.txt` trace), and `static-offset,...1541 reupload`
      (`static`, no hex). `Motion traces` itself never appears as a session.

      Four folders in this staging copy of the root are present but empty on
      disk (`Prostate-Continuous,...1324`, `Static,...1207`,
      `StaticISO04CouchShift,...1249`, and `lung-baselinshift,...1503` — the
      last has its data only in the adjacent, unextracted
      `lung-baselinshift,Bluey_6x_260623_1503.zip`), so they correctly do not
      appear in the manifest (no `MarkerLocations_CouchShift_0.txt` found,
      nested or not) rather than surfacing as errors. This is a data-staging
      gap in `Staging02`, not a discovery bug: `discover_sessions()` was
      re-run directly (not through the live server, to avoid writing into
      `Staging02`) against the zip's extracted contents in a scratch temp
      directory and correctly matched the *real* misspelled folder name:
      ```
      lung-baselinshift,Bluey_6x_260623_1503  motion
        -> .../hexamotion-lung/t_Lung_Baseline_Shifts.txt   error=None
      ```
      No liver session exists in the Bluey root, so the liver `PAIR_MAP`
      entries could not be exercised against real data; they are covered by
      `tests/test_discovery.py`.

- [x] **Metrics parity**: Prostate-Erratic,...1456, offset set to the deck's
      37.4 s (slide 29). Computed with `kim_qa.metrics.overlay_residuals` /
      `overlay_metrics_table` directly on the live payload:

      | Axis | Mean (mm), no si-shift | Mean (mm), deck si-shift +0.5 | Std (mm) |
      |---|---|---|---|
      | LR | -0.2747 | -0.2747 (unchanged) | 1.7745 |
      | SI | -0.4254 | **+0.0746** | 0.1552 |
      | AP | +0.6792 | +0.6792 (unchanged) | 2.2373 |

      SI mean differs from the no-shift value by exactly +0.5000 mm
      (-0.4254 + 0.5 = 0.0746); LR and AP are bit-identical since the deck's
      `data-si-shift` only perturbs the SI channel. Matches the brief's
      expectation exactly.

- [x] **Interrupt** (Prostate-Continuous-interrupt,...1350): raw timebase
      confirmed (`GET .../payload` returns 433 raw, uncompressed points;
      `shift_events` carries `t_after: 47.957` matching the KIM log's own
      segment-boundary timestamp). Dead-time band compressed in the UI
      ("186 s dead time compressed" label — the true acquisition pause is an
      interior gap inside the *second* log file, not at the file-boundary
      itself; confirmed by inspecting the raw `MarkerLocations_CouchShift_1.txt`
      timestamps: row 1 at t=48.020 s, row 2 jumps to t=233.881 s). Per-panel
      couch annotations read from `couchShifts.txt`
      (`VRT 21.70->21.53 cm, LNG 108.84->108.96 cm, LAT 999.06->999.09 cm`):
      with Varian selected, `shift_events` = `{lr: 0.3, si: 1.2, ap: 1.7}`,
      matching the brief's LR +0.3 / SI +1.2 / AP +1.7 mm exactly. A single
      offset (auto-fit +129.29 s, "RMSE minimisation on SI") aligns both
      acquisition segments to the continuous hex drift in the screenshot
      (`docs/webapp-overlay.png`).

- [x] **Couch steps view** on the interrupt session: `GET .../couch-steps`
      returns `expected_steps` whose row-to-row delta
      (`[0.3, 1.2, -1.7]`, Elekta) equals `shifts[0]` exactly, and the
      commanded-shift side card in the UI shows the same `LR +0.30 / SI +1.20
      / AP -1.70` (Elekta) values read straight from `couchShifts.txt`. Step
      lines (cyan) and dashed couch-move markers render at the segment
      boundary. Screenshot captured.

- [x] **As-recorded ghost**: toggling "Show as-recorded" renders translucent
      post-shift ghost dots offset from the main (shift-removed) trace by
      exactly the couch delta, pulled *away* from zero (confirmed visually —
      SI ghost sits ~1.2 mm below the main trace, AP ghost sits ~1.7 mm above
      it — and numerically: payload point at t=48.02 s, file_index 1, has
      corrected `lr=0.0865, si=-3.268, ap=-0.1799`; the raw KIM log at the
      same row has `LR=0.386546, SI=-2.068009, AP=-1.87994`; corrected + shift
      (`{lr:0.3, si:1.2, ap:-1.7}`) reproduces the raw values to 4 dp).

- [x] **kV hover** on lung-typical,...1518 (`has_frames: true`): frame index
      returns 636 entries, 0 missing, crop `{x0: 384, y0: 256, size: 256}`
      (centred on (512, 384) as specced); fetched a real frame PNG
      (`Ch1_0_2065_184.98.png`), 200 OK, correctly windowed 8-bit crop showing
      the phantom marker. `GET .../frames/index.json` on a session without
      `KIM-KV` (Prostate-Erratic) returns 404, which the widget renders as
      "Images unavailable" / "Hover a KIM point to preview its kV frame."
      (screenshot).

- [x] **Gantry top axis**: present on GA sessions (payload `kim.gantry`
      populated, e.g. lung-typical); the top "Gantry (deg)" axis with tick
      marks renders in the screenshot, and the hover-tooltip code path
      includes `gantry {value} deg` (`KimOverlay.tsx:405`).

- [x] **y-range**: default ±10 mm confirmed in the UI (input shows `10` on
      first load of every motion session); code review confirms blank ->
      no `range`/`autorange` props set on the yaxis (Plotly default
      autorange applies) and `uirevision: experiment` keeps the current
      Plotly zoom/pan state stable across offset-slider re-renders of the
      same session. Zoom / double-click-unzoom themselves are Plotly.js's
      own modebar behaviour (`displaylogo:false`, default double-click reset
      is enabled, no custom override) — verified by code review rather than
      simulated drag-zoom, since no browser-automation tool in this
      environment can perform a Plotly drag-select/zoom gesture; this is the
      one checklist item not exercised by an actual interaction.

- [x] **Save**: `POST .../save` on Prostate-Erratic,...1456 (offset 37.4 s)
      wrote `Prostate-Erratic,Bluey_6x_260623_1456/overlay.png` (146 KB),
      updated `_overlay_state.json`, and regenerated `summary.md` at the
      root with the saved session's row and per-session detail section; the
      table's `SI mean±std = -0.43±0.16` matches the Python-canonical
      metrics computed above. Confirmed via `Get-Item` and reading the
      regenerated `summary.md`. (This writes into the real
      `Staging02\Bluey_2026-06-23` results root — the app's intended output
      location for Save, per the design spec — not into this repo.)

- [x] **Vendor toggle**: `POST /api/config {"vendor":"Varian"}` flips
      `shift_events[0].ap` from `-1.7` (Elekta) to `+1.7` (Varian) on the
      interrupt session's overlay payload, with LR/SI unchanged; the
      couch-steps `shifts`/`expected_steps` and the ghost reconstruction all
      derive from the same signed values, so all four surfaces flip
      together by construction (single source of truth in
      `kim_qa.io.couch.parse_couch_shifts`). Reverted to Elekta after the
      check.

- [x] **Exe run** (Task 16 build): rebuilt
      `python_app/dist/KIM-QA-Server.exe` (`uv run pyinstaller
      KIM-QA-Server.spec --noconfirm`) to pick up the freshly-built
      `webapp/dist`, ran it against the same root on a second port, and
      confirmed byte-for-byte-identical rendered UI (same sidebar, same
      metrics, same dead-time band, same saved-session checkmark) via a
      second CDP screenshot.

## Fixes made during this pass

None — every checklist item passed against real data on the first run; no
code changes were needed in `src/kim_qa/` or `webapp/src/`.

## Notes / deviations

- The Bluey staging root has four session folders with no data on disk yet
  (three empty, one only in an unextracted zip); this is a data-availability
  gap in `Staging02`, not an app defect, and doesn't block any checklist item
  since the sessions that do have data cover every discovery/classification
  path the brief asks about (motion + static, one PAIR_MAP misspelling
  match verified against the real zipped folder).
- No liver session exists in this Bluey batch, so liver classification was
  not exercised against real data (covered by `tests/test_discovery.py`).
- Zoom/double-click-unzoom persistence across slider moves was verified by
  code review (`uirevision`, Plotly default double-click behaviour, no
  environment browser-automation tool available to simulate a drag-zoom
  gesture) rather than by a live interaction.
