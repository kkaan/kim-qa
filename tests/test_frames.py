import numpy as np
from PIL import Image

from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import discover_sessions
from kim_qa.server.frames import build_frame_index, render_frame_png
from tests.fixtures import make_motion_session, make_static_session


def motion_with_kv(tmp_path, n_missing=1):
    # 16 points is plenty here: this test never runs the auto-fit.
    sess_dir = make_motion_session(tmp_path, tmp_path / "Motion traces",
                                   n_points=16, dt=0.5)
    kv = sess_dir / "KIM-KV"
    kv.mkdir()
    # GA fixture names frames Ch1_0_{i:04d}.tiff; write all but the last
    # n_missing as 1024x768 uint16 gradients.
    arr = (np.arange(768 * 1024, dtype=np.uint16).reshape(768, 1024) % 4096)
    for i in range(16 - n_missing):
        Image.fromarray(arr, mode="I;16").save(kv / f"Ch1_0_{i:04d}.tiff")
    cfg = ServerConfig(root=tmp_path)
    return {s.id: s for s in discover_sessions(cfg)}["lung-typical,Test_1518"]


def test_index_maps_points_in_order(tmp_path):
    sess = motion_with_kv(tmp_path)
    idx = build_frame_index(sess)
    assert idx is not None
    assert idx["crop"] == {"x0": 384, "y0": 256, "size": 256}
    assert idx["count"] == 16
    f0 = idx["frames"][0]
    assert f0["i"] == 0 and f0["file"] == "Ch1_0_0000.png"
    assert np.isclose(f0["gantry"], 180.0)
    assert f0["mx"] == 512 - 384 and f0["my"] == 384 - 256
    assert idx["frames"][15].get("missing") is True


def test_no_kv_dir_returns_none(tmp_path):
    make_static_session(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    sess = {s.id: s for s in discover_sessions(cfg)}["Static,Test_1207"]
    assert build_frame_index(sess) is None


def test_render_crop_windows_and_caches(tmp_path):
    sess = motion_with_kv(tmp_path)
    p = render_frame_png(sess, "Ch1_0_0000.png")
    assert p is not None and p.exists()
    img = np.asarray(Image.open(p))
    assert img.shape == (256, 256) and img.dtype == np.uint8
    assert img.max() == 255                     # windowed to full scale
    mtime = p.stat().st_mtime
    assert render_frame_png(sess, "Ch1_0_0000.png").stat().st_mtime == mtime


def test_render_missing_tiff_returns_none(tmp_path):
    sess = motion_with_kv(tmp_path)
    assert render_frame_png(sess, "Ch1_0_0015.png") is None
