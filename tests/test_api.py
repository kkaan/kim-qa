"""API integration tests (FastAPI TestClient)."""
import base64
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from kim_qa.server.config import ServerConfig
from kim_qa.server.app import create_app
from kim_qa.server.state import load_state
from tests.fixtures import make_interrupt_session, make_motion_session, write_hex_trace


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


def test_post_config_vendor(tmp_path):
    client = make_client(tmp_path)
    r = client.post("/api/config", json={"vendor": "Varian"})
    assert r.status_code == 200
    assert client.get("/api/config").json()["vendor"] == "Varian"


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


def test_payload_and_couch_steps_roundtrip(tmp_path):
    client = full_client(tmp_path)
    r = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload")
    assert r.status_code == 200
    assert len(r.json()["shift_events"]) == 1
    r2 = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/couch-steps")
    assert r2.status_code == 200
    assert r2.json()["kind"] == "couch_shift"
    r3 = client.get(f"/api/experiments/{quote(MOTION_ID)}/couch-steps")
    assert r3.status_code == 404
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


def test_vendor_change_reflected_in_payload(tmp_path):
    client = full_client(tmp_path)
    ap1 = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload").json()[
        "shift_events"][0]["ap"]
    client.post("/api/config", json={"vendor": "Varian"})
    ap2 = client.get(f"/api/experiments/{quote(INTERRUPT_ID)}/payload").json()[
        "shift_events"][0]["ap"]
    assert ap1 == -ap2


def test_cli_parse_args():
    from kim_qa.server.__main__ import parse_args
    ns = parse_args(["--root", "C:/data", "--vendor", "Varian", "--port", "9000"])
    assert ns.root == "C:/data" and ns.vendor == "Varian" and ns.port == 9000
    ns2 = parse_args([])
    assert ns2.root is None and ns2.vendor == "Elekta" and ns2.port == 0
