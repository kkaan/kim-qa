from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import (
    discover_sessions, find_trace, list_baselines, list_traces,
)
from tests.fixtures import (
    make_baseline_pair, make_interrupt_session, make_motion_session,
    make_static_session, write_ga_file, write_hex_trace,
)
import numpy as np


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


def test_list_traces_includes_any_txt(tmp_path):
    """Naming conventions are not enforced: robot traces and arbitrarily named
    files must be selectable, not just t_*/LiverTraj_* matches."""
    cfg = build_root(tmp_path)
    from tests.fixtures import write_robot_trace
    write_robot_trace(cfg.traces_root / "Trace 1-Large AP motion.txt")
    write_robot_trace(cfg.traces_root / "nested" / "LiverTraj_BreathHold1_robot.txt")
    names = list_traces(cfg.traces_root)
    assert "Trace 1-Large AP motion.txt" in names
    assert "LiverTraj_BreathHold1_robot.txt" in names
    assert "t_Lung_Typical.txt" in names


def test_baselines_root_excluded_from_sessions_and_listed(tmp_path):
    make_baseline_pair(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    assert cfg.baselines_root == tmp_path / "Baselines"
    sessions = {s.id for s in discover_sessions(cfg)}
    assert sessions == {"2026-08-07-Pat03"}          # Baselines is not a session
    assert list_baselines(cfg.baselines_root) == ["2026_06_17-pat03"]


def test_list_baselines_ignores_folders_without_kim_log(tmp_path):
    d = tmp_path / "Baselines" / "not-a-log"
    d.mkdir(parents=True)
    (d / "readme.txt").write_text("no log here")
    assert list_baselines(tmp_path / "Baselines") == []
    assert list_baselines(tmp_path / "missing") == []


def test_baseline_override_sentinel_gives_motion_session(tmp_path):
    make_baseline_pair(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    overrides = {"2026-08-07-Pat03": "baseline:2026_06_17-pat03"}
    s = {s.id: s for s in discover_sessions(cfg, overrides)}["2026-08-07-Pat03"]
    assert s.kind == "motion"
    assert s.hex_file is None
    assert s.baseline_dir is not None
    assert s.baseline_dir.name == "2026_06_17-pat03"


def test_unknown_baseline_override_falls_back_to_static(tmp_path):
    make_baseline_pair(tmp_path)
    cfg = ServerConfig(root=tmp_path)
    overrides = {"2026-08-07-Pat03": "baseline:no-such-folder"}
    s = {s.id: s for s in discover_sessions(cfg, overrides)}["2026-08-07-Pat03"]
    assert s.kind == "static" and s.baseline_dir is None


def test_missing_centroid_is_not_an_error(tmp_path):
    make_baseline_pair(tmp_path)                     # writes no centroid file
    s = discover_sessions(ServerConfig(root=tmp_path))[0]
    assert s.centroid_file is None
    assert s.error is None


def _add_sibling_log(sess_dir, name):
    sib = sess_dir / name
    sib.mkdir()
    t = np.arange(20) * 0.15
    write_ga_file(sib / "MarkerLocationsGA_CouchShift_0.txt",
                  t, t * 0, t * 0, t * 0, np.linspace(180, 100, 20))
    return sib


def test_log_version_sibling_becomes_offline_dir(tmp_path):
    make_baseline_pair(tmp_path)
    _add_sibling_log(tmp_path / "2026-08-07-Pat03", "log-version-125")
    s = discover_sessions(ServerConfig(root=tmp_path))[0]
    names = [d.name for d in s.offline_dirs]
    assert "log-version-125" in names
    assert "log-version-124" not in names            # primary parent excluded


def test_any_named_sibling_log_becomes_offline_dir(tmp_path):
    """Log folders are recognised by contents, not naming conventions."""
    make_baseline_pair(tmp_path)
    _add_sibling_log(tmp_path / "2026-08-07-Pat03", "reprocessed with fix")
    s = discover_sessions(ServerConfig(root=tmp_path))[0]
    assert "reprocessed with fix" in [d.name for d in s.offline_dirs]


def test_test_log_override_swaps_primary(tmp_path):
    make_baseline_pair(tmp_path)
    _add_sibling_log(tmp_path / "2026-08-07-Pat03", "log-version-125")
    s = discover_sessions(
        ServerConfig(root=tmp_path),
        test_logs={"2026-08-07-Pat03": "log-version-125"})[0]
    assert s.kim_file.parent.name == "log-version-125"
    # The previous primary is demoted to an offline overlay
    assert "log-version-124" in [d.name for d in s.offline_dirs]
    assert "log-version-125" not in [d.name for d in s.offline_dirs]


def test_unknown_test_log_falls_back_to_auto(tmp_path):
    make_baseline_pair(tmp_path)
    s = discover_sessions(
        ServerConfig(root=tmp_path),
        test_logs={"2026-08-07-Pat03": "no-such-folder"})[0]
    assert s.kim_file.parent.name == "log-version-124"


