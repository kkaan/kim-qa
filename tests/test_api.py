"""API integration tests (FastAPI TestClient)."""
import base64
from pathlib import Path
from urllib.parse import quote

import numpy as np
from fastapi.testclient import TestClient

from kim_qa.server.config import ServerConfig
from kim_qa.server.app import create_app
from kim_qa.server.state import load_state
from tests.fixtures import (
    make_interrupt_session, make_motion_session, write_centroid_file,
    write_ga_file, write_hex_trace,
)


def make_client(tmp_path: Path) -> TestClient:
    (tmp_path / "Motion traces").mkdir(exist_ok=True)
    cfg = ServerConfig(root=tmp_path)
    return TestClient(create_app(cfg))


def test_get_config(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "Elekta"
    assert body["root"] == str(tmp_path)
    assert body["traces_root"] == str(tmp_path / "Motion traces")
    assert body["baselines_root"] == str(tmp_path / "Baselines")


def test_post_config_vendor(tmp_path):
    client = make_client(tmp_path)
    r = client.post("/api/config", json={"vendor": "Varian"})
    assert r.status_code == 200
    assert client.get("/api/config").json()["vendor"] == "Varian"
    # Choice persists per root, under the reserved _config state key
    assert load_state(tmp_path)["_config"]["vendor"] == "Varian"


def test_manifest_lists_baselines(tmp_path):
    from tests.fixtures import make_baseline_pair
    make_baseline_pair(tmp_path)
    client = make_client(tmp_path)
    m = client.get("/api/manifest").json()
    assert m["baselines"] == ["2026_06_17-pat03"]
    assert {e["id"] for e in m["experiments"]} == {"2026-08-07-Pat03"}


def test_baseline_override_round_trip(tmp_path):
    from tests.fixtures import make_baseline_pair
    make_baseline_pair(tmp_path)
    client = make_client(tmp_path)
    sid = quote("2026-08-07-Pat03", safe="")

    p = client.get(f"/api/experiments/{sid}/payload").json()
    assert p["kind"] == "static" and "hex" not in p

    r = client.post(f"/api/experiments/{sid}/state",
                    json={"offset": 0.0, "ranges": [],
                          "hex_override": "baseline:2026_06_17-pat03"})
    assert r.status_code == 200
    assert "offset" not in r.json()          # override change drops offset

    p = client.get(f"/api/experiments/{sid}/payload").json()
    assert p["kind"] == "motion"
    assert p["hex"]["source"]["name"] == "2026_06_17-pat03"
    assert abs(p["saved_offset"] - 0.5) < 0.1     # refit against baseline

    client.post(f"/api/experiments/{sid}/state",
                json={"offset": 0.0, "ranges": [], "hex_override": None})
    p = client.get(f"/api/experiments/{sid}/payload").json()
    assert p["kind"] == "static" and "hex" not in p


def test_test_log_round_trip(tmp_path):
    from tests.fixtures import make_baseline_pair, write_ga_file as wga
    import numpy as np2
    make_baseline_pair(tmp_path)
    sib = tmp_path / "2026-08-07-Pat03" / "log-version-125"
    sib.mkdir()
    t = np2.arange(20) * 0.15
    wga(sib / "MarkerLocationsGA_CouchShift_0.txt",
        t, t * 0 + 5.0, t * 0, t * 0, np2.linspace(180, 100, 20))
    client = make_client(tmp_path)
    sid = quote("2026-08-07-Pat03", safe="")

    m = client.get("/api/manifest").json()
    entry = m["experiments"][0]
    assert entry["test_log"] == "log-version-124"
    assert set(entry["test_logs"]) == {"log-version-124", "log-version-125"}

    r = client.post(f"/api/experiments/{sid}/state",
                    json={"offset": 3.0, "ranges": [],
                          "test_log": "log-version-125"})
    assert r.status_code == 200
    assert "offset" not in r.json()          # test-trace change drops offset

    p = client.get(f"/api/experiments/{sid}/payload").json()
    # The chosen log's AP is a constant +5 raw; it is now the primary trace
    assert abs(p["kim"]["ap"][0] - 5.0) < 1e-6
    assert "log-version-124" in [o["folder"] for o in p["kim_offline"]]


def test_gantry_remap_round_trip(tmp_path):
    from tests.fixtures import make_baseline_pair
    make_baseline_pair(tmp_path)
    client = make_client(tmp_path)
    sid = quote("2026-08-07-Pat03", safe="")
    client.post(f"/api/experiments/{sid}/state",
                json={"offset": 0.0, "ranges": [],
                      "hex_override": "baseline:2026_06_17-pat03"})
    client.post(f"/api/experiments/{sid}/state",
                json={"offset": 1.5, "ranges": [],
                      "hex_override": "baseline:2026_06_17-pat03",
                      "offset_origin": "manual"})

    r = client.post(f"/api/experiments/{sid}/state",
                    json={"offset": 1.5, "ranges": [],
                          "hex_override": "baseline:2026_06_17-pat03",
                          "gantry_remap": True})
    assert "offset" not in r.json()          # remap toggle drops saved offset
    p = client.get(f"/api/experiments/{sid}/payload").json()
    assert p["hex"]["remapped"] is True
    assert p["offset_origin"] == "gantry remap"
    entry = next(e for e in client.get("/api/manifest").json()["experiments"]
                 if e["id"] == "2026-08-07-Pat03")
    assert entry["gantry_remap"] is True

    client.post(f"/api/experiments/{sid}/state",
                json={"offset": 0.0, "ranges": [],
                      "hex_override": "baseline:2026_06_17-pat03",
                      "gantry_remap": False})
    p = client.get(f"/api/experiments/{sid}/payload").json()
    assert "remapped" not in p["hex"]


def test_vendor_persists_across_restart(tmp_path):
    client = full_client(tmp_path)
    client.post("/api/config", json={"vendor": "Varian"})
    # _config never leaks into the manifest as an experiment
    ids = {e["id"] for e in client.get("/api/manifest").json()["experiments"]}
    assert "_config" not in ids

    from kim_qa.server.state import load_vendor
    assert load_vendor(tmp_path) == "Varian"

    # Resolution order used by __main__: flag > persisted > Elekta
    def resolve(flag):
        return flag or load_vendor(tmp_path) or "Elekta"
    assert resolve("Elekta") == "Elekta"    # explicit flag wins
    assert resolve(None) == "Varian"        # persisted choice picked up


def test_load_vendor_tolerates_missing_or_junk(tmp_path):
    from kim_qa.server.state import load_vendor, save_vendor
    assert load_vendor(tmp_path) is None                       # no state file
    (tmp_path / "_overlay_state.json").write_text("not json", encoding="utf-8")
    assert load_vendor(tmp_path) is None                       # corrupt file
    (tmp_path / "_overlay_state.json").write_text(
        '{"_config": {"vendor": "Siemens"}}', encoding="utf-8")
    assert load_vendor(tmp_path) is None                       # unknown vendor
    save_vendor(tmp_path, "Elekta")
    assert load_vendor(tmp_path) == "Elekta"


def test_post_config_rejects_unknown_vendor(tmp_path):
    client = make_client(tmp_path)
    assert client.post("/api/config", json={"vendor": "Siemens"}).status_code == 422


def full_client(tmp_path):
    traces = tmp_path / "Motion traces"
    make_motion_session(tmp_path, traces)
    make_interrupt_session(tmp_path)
    write_hex_trace(traces / "t_Prostate_Continuous_Drift.txt")
    cfg = ServerConfig(root=tmp_path)
    return TestClient(create_app(cfg))


INTERRUPT_ID = "Prostate-Continuous-interrupt,Test_1350"
MOTION_ID = "lung-typical,Test_1518"


def test_manifest(tmp_path):
    client = full_client(tmp_path)
    body = client.get("/api/manifest").json()
    ids = {e["id"] for e in body["experiments"]}
    assert {INTERRUPT_ID, MOTION_ID} <= ids
    intr = next(e for e in body["experiments"] if e["id"] == INTERRUPT_ID)
    assert intr["has_couch_shifts"] is True
    assert "t_Lung_Typical.txt" in body["traces"]


def test_payload_roundtrip(tmp_path):
    client = full_client(tmp_path)
    r = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload")
    assert r.status_code == 200
    assert len(r.json()["shift_events"]) == 1
    assert client.get("/api/experiments/nope/payload").status_code == 404


def test_frames_404_when_unavailable(tmp_path):
    client = full_client(tmp_path)
    r = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/frames/index.json")
    assert r.status_code == 404


def test_state_and_save(tmp_path):
    client = full_client(tmp_path)
    r = client.post(f"/api/experiments/{quote(MOTION_ID)}/state",
                    json={"offset": 3.1, "ranges": [[4.0, 8.0]], "y_range": 10})
    assert r.status_code == 200
    assert load_state(tmp_path)[MOTION_ID]["offset"] == 3.1

    png = base64.b64encode(b"\x89PNG\r\n\x1a\nfakepng").decode()
    r2 = client.post(f"/api/experiments/{quote(MOTION_ID)}/save",
                     json={"offset": 3.1, "ranges": [], "png_base64": png})
    assert r2.status_code == 200
    assert (tmp_path / MOTION_ID / "overlay.png").exists()
    assert (tmp_path / "summary.md").exists()


def test_x_range_persists_to_payload(tmp_path):
    """The time-axis zoom (x_range, true time) round-trips state -> payload."""
    client = full_client(tmp_path)
    r = client.post(f"/api/experiments/{quote(MOTION_ID)}/state",
                    json={"offset": 0.0, "ranges": [], "x_range": [2.5, 18.0]})
    assert r.status_code == 200
    assert load_state(tmp_path)[MOTION_ID]["x_range"] == [2.5, 18.0]
    p = client.get(f"/api/experiments/{quote(MOTION_ID)}/payload").json()
    assert p["saved_x_range"] == [2.5, 18.0]

    # Clearing it (double-click autorange on the client) returns the default view.
    client.post(f"/api/experiments/{quote(MOTION_ID)}/state",
                json={"offset": 0.0, "ranges": [], "x_range": None})
    p2 = client.get(f"/api/experiments/{quote(MOTION_ID)}/payload").json()
    assert p2["saved_x_range"] is None


def test_vendor_change_reflected_in_payload(tmp_path):
    client = full_client(tmp_path)
    ap1 = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload").json()[
        "shift_events"][0]["ap"]
    client.post("/api/config", json={"vendor": "Varian"})
    ap2 = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload").json()[
        "shift_events"][0]["ap"]
    assert ap1 == -ap2


def test_hex_override_drops_stale_offset_and_refits_si(tmp_path):
    """Selecting a trace for a session that had no match must re-run the SI
    RMSE auto-fit, not keep the static offset of 0."""
    traces = tmp_path / "Motion traces"
    traces.mkdir(exist_ok=True)
    write_hex_trace(traces / "t_Prostate_Continuous_Drift.txt", n=2500)

    # Name matches no PAIR_MAP entry -> classified static, but the KIM data is
    # actually sampled from the trace above at a +3.0 s offset.
    name = "liver-transient,Test_1619"
    sess = tmp_path / name
    sess.mkdir()
    t = np.arange(120) * 0.25
    u = t + 3.0
    si = 2.0 * np.sin(2 * np.pi * 0.2 * u) + 0.1 * u
    lr = 0.2 * np.sin(2 * np.pi * 0.1 * u)
    ap = 0.5 * np.sin(2 * np.pi * 0.15 * u)
    g = np.linspace(180.0, 100.0, len(t))
    write_ga_file(sess / "MarkerLocationsGA_CouchShift_0.txt", t, ap, lr, si, g)
    write_centroid_file(sess / "Phantom_Centroid.txt")

    client = TestClient(create_app(ServerConfig(root=tmp_path)))
    ident = quote(name)

    # Starts static: no trace paired, offset 0.
    assert client.get(f"/api/experiments/{ident}/payload").json()["kind"] == "static"

    # A no-op state save (no override change) keeps the offset.
    client.post(f"/api/experiments/{ident}/state",
                json={"offset": 0.0, "ranges": [], "hex_override": None})
    assert load_state(tmp_path)[name]["offset"] == 0.0

    # Now select the trace: the override changes -> the stale offset is dropped.
    client.post(f"/api/experiments/{ident}/state",
                json={"offset": 0.0, "ranges": [], "offset_origin": "manual",
                      "hex_override": "t_Prostate_Continuous_Drift.txt"})
    entry = load_state(tmp_path)[name]
    assert "offset" not in entry and "offset_origin" not in entry
    assert entry["hex_override"] == "t_Prostate_Continuous_Drift.txt"

    # The rebuilt payload is now motion and re-fit on SI, recovering ~+3 s.
    p = client.get(f"/api/experiments/{ident}/payload").json()
    assert p["kind"] == "motion"
    assert "SI" in p["offset_origin"]
    assert abs(p["saved_offset"] - 3.0) < 0.3


def test_offline_overlay_detected_and_in_payload(tmp_path):
    """A nested kim-log* folder is auto-overlaid: the payload carries a
    kim_offline entry, labelled by the folder, sharing the primary timebase."""
    traces = tmp_path / "Motion traces"
    traces.mkdir(exist_ok=True)
    make_motion_session(tmp_path, traces)          # -> MOTION_ID, no overlay yet

    off = tmp_path / MOTION_ID / "kim-log-pdf480"
    off.mkdir()
    t = np.arange(120) * 0.25
    u = t + 3.0
    write_ga_file(off / "MarkerLocationsGA_CouchShift_0.txt", t,
                  0.5 * np.sin(2 * np.pi * 0.15 * u), 0.2 * np.sin(2 * np.pi * 0.1 * u),
                  2.0 * np.sin(2 * np.pi * 0.2 * u) + 0.1 * u, np.linspace(180, 100, 120))

    client = TestClient(create_app(ServerConfig(root=tmp_path)))
    p = client.get(f"/api/experiments/{quote(MOTION_ID)}/payload").json()
    assert len(p.get("kim_offline", [])) == 1
    ov = p["kim_offline"][0]
    assert ov["label"] == "pdf480" and ov["folder"] == "kim-log-pdf480"
    assert len(ov["t"]) == 120 and "gantry" in ov
    assert {"t", "lr", "si", "ap"} <= ov.keys()


def test_offline_offset_persists_to_overlay(tmp_path):
    """A per-overlay time offset round-trips: state.offline_offsets keyed by
    folder -> the overlay's `offset` in the payload. Unset stays null so the
    client falls back to the primary run's offset."""
    traces = tmp_path / "Motion traces"
    traces.mkdir(exist_ok=True)
    make_motion_session(tmp_path, traces)

    off = tmp_path / MOTION_ID / "kim-log-pdf480"
    off.mkdir()
    t = np.arange(120) * 0.25
    write_ga_file(off / "MarkerLocationsGA_CouchShift_0.txt", t,
                  0.5 * np.sin(t), 0.2 * np.sin(t), 2.0 * np.sin(t),
                  np.linspace(180, 100, 120))

    client = TestClient(create_app(ServerConfig(root=tmp_path)))
    ident = quote(MOTION_ID)

    # Unset: the overlay follows the primary offset (offset is null).
    p0 = client.get(f"/api/experiments/{ident}/payload").json()
    assert p0["kim_offline"][0]["offset"] is None

    # Save an independent offset for that folder; it lands in the payload.
    client.post(f"/api/experiments/{ident}/state",
                json={"offset": 0.0, "ranges": [],
                      "offline_offsets": {"kim-log-pdf480": 4.25}})
    assert load_state(tmp_path)[MOTION_ID]["offline_offsets"] == {
        "kim-log-pdf480": 4.25}
    p1 = client.get(f"/api/experiments/{ident}/payload").json()
    assert p1["kim_offline"][0]["offset"] == 4.25


def test_no_offline_overlay_without_kim_log_folder(tmp_path):
    client = full_client(tmp_path)
    p = client.get(f"/api/experiments/{quote(MOTION_ID)}/payload").json()
    assert "kim_offline" not in p


def test_cli_parse_args():
    from kim_qa.server.__main__ import parse_args
    ns = parse_args(["--root", "C:/data", "--vendor", "Varian", "--port", "9000"])
    assert ns.root == "C:/data" and ns.vendor == "Varian" and ns.port == 9000
    ns2 = parse_args([])
    assert ns2.root is None and ns2.vendor is None and ns2.port == 0


def test_cli_version_flag(capsys):
    import pytest
    from kim_qa.server.__main__ import parse_args
    from kim_qa.version import __version__
    with pytest.raises(SystemExit) as exc:
        parse_args(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"KIM-QA-Server {__version__}"
