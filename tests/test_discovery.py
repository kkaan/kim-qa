from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import (
    align_axis_for, discover_sessions, find_trace, list_traces,
)
from tests.fixtures import (
    make_interrupt_session, make_motion_session, make_static_session,
    write_hex_trace,
)


def build_root(tmp_path):
    traces = tmp_path / "Motion traces" / "nested"
    make_motion_session(tmp_path, traces)              # motion (lung-typical)
    make_static_session(tmp_path)                      # static
    make_interrupt_session(tmp_path)                   # motion via prostate map
    write_hex_trace(traces / "t_Prostate_Continuous_Drift.txt")
    (tmp_path / "empty-folder").mkdir()
    bad = tmp_path / "lung-highfrequency,Broken_0000"
    bad.mkdir()
    (bad / "MarkerLocations_CouchShift_0.txt").write_text("Frame No\ngarbage")
    return ServerConfig(root=tmp_path, traces_root=tmp_path / "Motion traces")


def test_discovery_classifies_and_matches(tmp_path):
    cfg = build_root(tmp_path)
    sessions = {s.id: s for s in discover_sessions(cfg)}
    lung = sessions["lung-typical,Test_1518"]
    assert lung.kind == "motion"
    assert lung.hex_file is not None and lung.hex_file.name == "t_Lung_Typical.txt"
    assert lung.has_frames is False
    static = sessions["Static,Test_1207"]
    assert static.kind == "static" and static.hex_file is None
    intr = sessions["Prostate-Continuous-interrupt,Test_1350"]
    assert intr.kind == "motion"
    assert intr.hex_file.name == "t_Prostate_Continuous_Drift.txt"
    assert intr.has_couch_shifts is True
    assert "empty-folder" not in sessions  # no KIM file -> skipped entirely


def test_unreadable_folder_surfaces_error(tmp_path):
    cfg = build_root(tmp_path)
    sessions = {s.id: s for s in discover_sessions(cfg)}
    bad = sessions["lung-highfrequency,Broken_0000"]
    assert bad.error is not None


def test_hex_override_wins(tmp_path):
    cfg = build_root(tmp_path)
    overrides = {"Static,Test_1207": "t_Lung_Typical.txt"}
    sessions = {s.id: s for s in discover_sessions(cfg, overrides)}
    s = sessions["Static,Test_1207"]
    assert s.kind == "motion" and s.hex_file.name == "t_Lung_Typical.txt"


def test_find_trace_recursive_and_list(tmp_path):
    cfg = build_root(tmp_path)
    assert find_trace(cfg.traces_root, "t_Lung_Typical.txt") is not None
    assert find_trace(cfg.traces_root, "t_Missing.txt") is None
    assert "t_Lung_Typical.txt" in list_traces(cfg.traces_root)


def test_align_axis():
    assert align_axis_for("lung-predominant,Bluey_6x_260623_1514") == "LR"
    assert align_axis_for("lung-typical,Bluey_6x_260623_1518") == "SI"
