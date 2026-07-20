"""parse_centroid_file: no invalid-escape warning + behaviour preserved.

The seed regex in parse_centroid_file used a non-raw f-string, so backslash
regex tokens (\\s, \\d) triggered "SyntaxWarning: invalid escape sequence".
Fixing it to a raw f-string must not change parsing behaviour.

Run as a script:  python tests/test_centroid_escape.py
"""
import os
import sys
import tempfile
import warnings

import kim_qa.io.centroid as centroid_mod

LOGIC_PATH = centroid_mod.__file__

# Non-trivial sample: exercises the avg-of-seeds and the AP/SI axis swap.
# seeds avg = [2,4,6]; iso = [1,1,1]; iso-relative*10 = [10,30,50]
# expected_centroid = {x: 10, y: 50 (=z_iso), z: -30 (=-y_iso)}
CENTROID_TXT = (
    "Seed 1, X=  1.0, Y=  2.0, Z=  3.0\n"
    "Seed 2, X=  3.0, Y=  6.0, Z=  9.0\n"
    "Isocenter (cm), X=  1.0, Y=  1.0, Z=  1.0\n"
)

# Single-marker phantom/robot file: "Marker_<label>" instead of "Seed N",
# British "Isocentre" spelling, no "(cm)" suffix, spaces before the commas.
# marker = [2,4,6]; iso = [1,1,1]; iso-relative*10 = [10,30,50]
# expected_centroid = {x: 10, y: 50 (=z_iso), z: -30 (=-y_iso)}
PHANTOM_TXT = (
    "ZZROBPHAN\n"
    "ROBOT, PHANTOM (ZZROBPHAN)\n"
    "Marker_GTV, X= 2.0, Y= 4.0, Z= 6.0\n"
    "Isocentre , X=1.0 , Y=1.0 , Z=1.0\n"
)


def test_no_invalid_escape_warning():
    """Compiling the module source emits no invalid-escape warning."""
    with open(LOGIC_PATH, "r", encoding="utf-8") as fh:
        src = fh.read()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile(src, LOGIC_PATH, "exec")
    offenders = [str(w.message) for w in caught
                 if "invalid escape sequence" in str(w.message)]
    assert not offenders, offenders


def test_parse_centroid_characterization():
    """Seeds, isocenter and transformed expected_centroid match known values."""
    from kim_qa.io.centroid import parse_centroid_file
    fd, path = tempfile.mkstemp(suffix="_centroid.txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(CENTROID_TXT)
    try:
        data = parse_centroid_file(path)
        assert data["seeds"] == [[1.0, 2.0, 3.0], [3.0, 6.0, 9.0]], data["seeds"]
        assert data["isocenter"] == [1.0, 1.0, 1.0], data["isocenter"]
        ec = data["expected_centroid"]
        assert ec["x"] == 10.0, ec
        assert ec["y"] == 50.0, ec
        assert ec["z"] == -30.0, ec
    finally:
        os.remove(path)


def test_parse_single_marker_phantom():
    """Single-marker phantom file (Marker_GTV / Isocentre / loose spacing) parses."""
    from kim_qa.io.centroid import parse_centroid_file
    fd, path = tempfile.mkstemp(suffix="_centroid.txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(PHANTOM_TXT)
    try:
        data = parse_centroid_file(path)
        assert data["seeds"] == [[2.0, 4.0, 6.0]], data["seeds"]
        assert data["isocenter"] == [1.0, 1.0, 1.0], data["isocenter"]
        ec = data["expected_centroid"]
        assert ec["x"] == 10.0, ec
        assert ec["y"] == 50.0, ec
        assert ec["z"] == -30.0, ec
    finally:
        os.remove(path)


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
