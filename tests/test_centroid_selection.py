"""Centroid-file formats and the per-root manual override.

Two real-world formats did not parse:

1. The native KIM export labels its isocentre line "Centroid (cm)", not
   "Isocenter"/"Isocentre". No file on the Lyrebird share uses the latter.
2. The MATLAB QA codes were fed a hand-stripped bare-numeric variant (one
   "x y z" row per seed, isocentre last). Elekta/Staticloc.m:23-37 reads it
   with fscanf('%f %f %f') and subtracts row 4 from the seed mean, which is
   exactly the role parse_centroid_file calls the isocentre.

Both encode the same numbers, so they must yield the same expected centroid.
A results root can hold several variants side by side (the 2024-11-06 CTRO
root has three), so the pick is also overridable per root.
"""
import tempfile
from pathlib import Path

from kim_qa.io.centroid import parse_centroid_file
from kim_qa.server.config import ServerConfig
from kim_qa.server.discovery import discover_sessions, list_centroid_files
from kim_qa.server.state import (
    load_centroid_file, load_vendor, save_centroid_file, save_vendor,
)
from tests.fixtures import make_static_session

# The real Centroid_210119.txt from the 2024-11-06 CTRO root: patient id,
# name line, three seeds, isocentre labelled "Centroid (cm)" with a trailing
# space. Seed mean = (-0.11, -0.39667, -0.30) cm; iso = (-0.13, 0.0, -0.40).
NATIVE_TXT = (
    "210119\n"
    "zzKIMe2e,zzKIMe2e\n"
    "Seed 1, X= -1.63, Y= -1.18, Z= 0.69\n"
    "Seed 2, X= -0.09, Y= 1.25, Z= -0.28\n"
    "Seed 3, X= 1.39, Y= -1.26, Z= -1.31\n"
    "Centroid (cm), X= -0.13, Y= 0.00, Z= -0.40 \n"
)

# The matching Centroid_210119 -forQAcode.txt: same numbers, labels stripped.
BARE_TXT = (
    "-1.63 -1.18 0.69\n"
    "-0.09 1.25 -0.28\n"
    "1.39 -1.26 -1.31\n"
    "-0.13 0.00 -0.40\n"
)


def _parse(text: str, suffix: str = "_centroid.txt") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"sample{suffix}"
        path.write_text(text, encoding="utf-8")
        return parse_centroid_file(path)


def test_native_kim_export_parses():
    """"Centroid (cm)" is accepted as the isocentre label."""
    data = _parse(NATIVE_TXT)
    assert len(data["seeds"]) == 3, data["seeds"]
    assert data["isocenter"] == [-0.13, 0.0, -0.40], data["isocenter"]


def test_bare_numeric_parses():
    """Label-free rows: all but the last are seeds, the last is the isocentre."""
    data = _parse(BARE_TXT)
    assert data["seeds"] == [[-1.63, -1.18, 0.69], [-0.09, 1.25, -0.28],
                             [1.39, -1.26, -1.31]], data["seeds"]
    assert data["isocenter"] == [-0.13, 0.0, -0.40], data["isocenter"]


def test_both_formats_agree():
    """The two encodings of one measurement give the same expected centroid."""
    native = _parse(NATIVE_TXT)["expected_centroid"]
    bare = _parse(BARE_TXT)["expected_centroid"]
    for axis in ("x", "y", "z"):
        assert abs(native[axis] - bare[axis]) < 1e-9, (axis, native, bare)


def test_bare_numeric_expected_centroid_matches_matlab():
    """Staticloc.m:27-37 by hand: 10*(seed_mean - iso), then x, z, -y."""
    ec = _parse(BARE_TXT)["expected_centroid"]
    # seed mean = (-0.11, -0.396667, -0.30); iso-relative*10 = (0.2, -3.96667, 1.0)
    assert abs(ec["x"] - 0.2) < 1e-6, ec
    assert abs(ec["y"] - 1.0) < 1e-6, ec        # y <- z_iso
    assert abs(ec["z"] - 3.966667) < 1e-6, ec   # z <- -y_iso


def test_ragged_numeric_file_rejected():
    """A 7-column robot trace must not be mistaken for a bare centroid file,
    even when its float count happens to divide by three."""
    robot = "".join("0.0 1.0 2.0 3.0 4.0 5.0 6.0\n" for _ in range(3))
    try:
        _parse(robot)
    except ValueError:
        return
    raise AssertionError("7-column trace parsed as a centroid file")


def test_text_file_still_rejected():
    """A file with no coordinates at all still raises, not silently zeroes."""
    try:
        _parse("hello world\nnothing to see here\n")
    except ValueError:
        return
    raise AssertionError("non-coordinate file parsed as a centroid file")


def test_single_row_rejected():
    """One row is a marker with no isocentre — not enough to compute an offset."""
    try:
        _parse("1.0 2.0 3.0\n")
    except ValueError:
        return
    raise AssertionError("single-row file parsed as a centroid file")


def _root_with_two_centroids(tmp: Path) -> Path:
    """Static session carrying its own Phantom_Centroid.txt, plus two
    root-level files — the auto-pick order is alphabetical, so 'A_...' wins."""
    make_static_session(tmp)
    (tmp / "A_centroid_wrong.txt").write_text(BARE_TXT, encoding="utf-8")
    (tmp / "Z_centroid_right.txt").write_text(NATIVE_TXT, encoding="utf-8")
    return tmp


def test_list_centroid_files_lists_root_txt():
    """The dropdown offers every root-level .txt, not just 'centroid'-named ones."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        names = list_centroid_files(root)
        assert "A_centroid_wrong.txt" in names, names
        assert "Z_centroid_right.txt" in names, names
        # Session-local files are not root-level candidates.
        assert "Phantom_Centroid.txt" not in names, names


def test_override_wins_over_session_local_file():
    """A manual pick beats auto-detection everywhere, including session-local files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        cfg = ServerConfig(root=root, centroid_file="Z_centroid_right.txt")
        sess = discover_sessions(cfg)[0]
        assert sess.error is None, sess.error
        assert sess.centroid_file.name == "Z_centroid_right.txt", sess.centroid_file


def test_no_override_keeps_session_local_auto_pick():
    """Existing roots are unaffected: auto still prefers the session's own file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        sess = discover_sessions(ServerConfig(root=root))[0]
        assert sess.centroid_file.name == "Phantom_Centroid.txt", sess.centroid_file


def test_missing_override_falls_back_to_auto():
    """A stale override (file deleted or renamed) must not blank the centroid."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        cfg = ServerConfig(root=root, centroid_file="gone.txt")
        sess = discover_sessions(cfg)[0]
        assert sess.centroid_file.name == "Phantom_Centroid.txt", sess.centroid_file


def test_override_accepts_absolute_path_outside_the_root():
    """Centroid files are often kept in a shared folder beside the results
    root (the share has a standalone 'Centroid 248687/'), so an absolute path
    anywhere on disk is a valid pick — not just a name under the root."""
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "elsewhere"
        outside.mkdir()
        far = outside / "Centroid_248687.txt"
        far.write_text(NATIVE_TXT, encoding="utf-8")
        root = _root_with_two_centroids(Path(tmp) / "results")
        cfg = ServerConfig(root=root, centroid_file=str(far))
        sess = discover_sessions(cfg)[0]
        assert sess.error is None, sess.error
        assert sess.centroid_file == far, sess.centroid_file


def test_relative_override_resolves_against_the_root():
    """A relative path is interpreted from the results root, so a sibling
    folder can be named without spelling out the whole UNC path."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp) / "results")
        sibling = root.parent / "shared"
        sibling.mkdir()
        (sibling / "c.txt").write_text(NATIVE_TXT, encoding="utf-8")
        cfg = ServerConfig(root=root, centroid_file="../shared/c.txt")
        sess = discover_sessions(cfg)[0]
        assert sess.centroid_file.name == "c.txt", sess.centroid_file


def test_missing_absolute_override_falls_back_to_auto():
    """An unreachable path (share offline, file moved) reverts to auto rather
    than blanking the expected offset, which would silently skew every metric."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        cfg = ServerConfig(root=root,
                           centroid_file=str(Path(tmp) / "nope" / "gone.txt"))
        sess = discover_sessions(cfg)[0]
        assert sess.centroid_file.name == "Phantom_Centroid.txt", sess.centroid_file


def test_directory_override_falls_back_to_auto():
    """A directory is not a centroid file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _root_with_two_centroids(Path(tmp))
        cfg = ServerConfig(root=root, centroid_file=str(root))
        sess = discover_sessions(cfg)[0]
        assert sess.centroid_file.name == "Phantom_Centroid.txt", sess.centroid_file


def test_state_roundtrip_preserves_vendor():
    """Both per-root settings share the reserved _config entry."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        save_vendor(root, "Varian")
        save_centroid_file(root, "Z_centroid_right.txt")
        assert load_centroid_file(root) == "Z_centroid_right.txt"
        assert load_vendor(root) == "Varian"
        save_centroid_file(root, None)          # back to auto
        assert load_centroid_file(root) is None
        assert load_vendor(root) == "Varian"
