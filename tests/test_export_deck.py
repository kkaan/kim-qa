"""Smoke test for the rich deck exporter (tools/export_server_payloads_to_deck)."""
import importlib.util
import json
from pathlib import Path

import numpy as np

from tests.fixtures import make_baseline_pair, make_motion_session, write_ga_file

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load_exporter():
    """Import the tool by file path (tools/ is not an installed package)."""
    path = TOOLS / "export_server_payloads_to_deck.py"
    spec = importlib.util.spec_from_file_location("export_deck_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_writes_rich_payloads_and_manifest(tmp_path):
    traces = tmp_path / "Motion traces"
    traces.mkdir()
    make_motion_session(tmp_path, traces)          # -> lung-typical,Test_1518
    motion_id = "lung-typical,Test_1518"

    # A nested offline overlay so the rich kim_offline path is exercised.
    off = tmp_path / motion_id / "kim-log-pdf480"
    off.mkdir()
    t = np.arange(120) * 0.25
    write_ga_file(off / "MarkerLocationsGA_CouchShift_0.txt", t,
                  0.5 * np.sin(t), 0.2 * np.sin(t), 2.0 * np.sin(t),
                  np.linspace(180, 100, 120))

    mod = _load_exporter()
    out = tmp_path / "_deck_assets"
    res = mod.export(tmp_path, out, vendor="Elekta", log=lambda *a: None)
    assert res["exported"] >= 1

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["vendor"] == "Elekta"
    entry = next(e for e in manifest["experiments"] if e["id"] == motion_id)
    # Manifest carries the widget's ManifestEntry fields + a file pointer.
    assert entry["file"] == f"experiments/{mod.slugify(motion_id)}.json"
    assert {"y_range", "hex_override", "offset_origin", "kind"} <= entry.keys()

    payload = json.loads((out / entry["file"]).read_text(encoding="utf-8"))
    # Rich ServerPayload keys the deck's kim-overlay-rich widget needs.
    assert {"kim", "shift_events", "centroid", "file_index"} <= payload.keys()
    assert len(payload.get("kim_offline", [])) == 1
    assert payload["kim_offline"][0]["label"] == "pdf480"


def test_export_baseline_gt_session(tmp_path):
    make_baseline_pair(tmp_path)
    (tmp_path / "_overlay_state.json").write_text(json.dumps({
        "2026-08-07-Pat03": {"offset": 0.5, "ranges": [],
                             "hex_override": "baseline:2026_06_17-pat03"}}),
        encoding="utf-8")
    mod = _load_exporter()
    out = tmp_path / "_deck_assets"
    res = mod.export(tmp_path, out, vendor="Elekta", log=lambda *a: None)
    assert res["exported"] == 1

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["experiments"][0]
    assert entry["baseline"] == "2026_06_17-pat03"

    payload = json.loads((out / entry["file"]).read_text(encoding="utf-8"))
    assert payload["hex"]["source"]["type"] == "baseline"
    assert len(payload["hex"]["t"]) == payload["hex"]["n"]
