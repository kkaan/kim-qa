"""parse_ground_truth_file routes trajectory / 7-column / comma-delimited files."""
import os
import sys
import tempfile

import numpy as np

from kim_qa import parse_ground_truth_file


def _write(content):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    return path


def test_routes_trajectory_header():
    path = _write("trajectory\n0\t1\t2\n0\t1\t2\n")
    try:
        df = parse_ground_truth_file(path, dt=0.02)
        assert list(df.columns) == ["time", "x", "y", "z"], list(df.columns)
        assert np.allclose(df["time"], [0.0, 0.02])
    finally:
        os.remove(path)


def test_routes_seven_column_whitespace():
    path = _write("0 1 2 3 0 0 0\n0.2 1 2 3 0 0 0\n")
    try:
        df = parse_ground_truth_file(path)
        assert np.allclose(df["time"], [0.0, 0.2])  # col0 timestamps
    finally:
        os.remove(path)


def test_falls_back_to_robot_for_comma_csv():
    path = _write("0,1,2,3,0,0,0\n0.2,1,2,3,0,0,0\n")
    try:
        df = parse_ground_truth_file(path)
        assert list(df.columns) == ["time", "x", "y", "z"], list(df.columns)
        assert np.allclose(df["time"], [0.0, 0.2])
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
