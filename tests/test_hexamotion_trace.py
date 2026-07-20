"""parse_hexamotion_trace: 3-column (implicit dt) and 7-column (explicit time) layouts."""
import os
import sys
import tempfile

import numpy as np

from kim_qa import parse_hexamotion_trace


def _write(content):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    return path


def test_three_column_uses_dt():
    path = _write("trajectory\n0.0\t1.0\t2.0\n3.0\t4.0\t5.0\n6.0\t7.0\t8.0\n")
    try:
        df = parse_hexamotion_trace(path, dt=0.02)
        assert list(df.columns) == ["time", "x", "y", "z"], list(df.columns)
        assert np.allclose(df["time"], [0.0, 0.02, 0.04]), df["time"].tolist()
        assert np.allclose(df["x"], [0.0, 3.0, 6.0])
        assert np.allclose(df["y"], [1.0, 4.0, 7.0])
        assert np.allclose(df["z"], [2.0, 5.0, 8.0])
    finally:
        os.remove(path)


def test_three_column_custom_dt():
    path = _write("trajectory\n0\t0\t0\n0\t0\t0\n0\t0\t0\n")
    try:
        df = parse_hexamotion_trace(path, dt=0.05)
        assert np.allclose(df["time"], [0.0, 0.05, 0.10]), df["time"].tolist()
    finally:
        os.remove(path)


def test_seven_column_uses_col0_time():
    path = _write(
        "0 0.05 0.31 0.10 0 0 0\n"
        "0.2 0.23 0.26 0.16 0 0 0\n"
        "0.4 0.21 0.15 0.19 0 0 0\n"
    )
    try:
        df = parse_hexamotion_trace(path, dt=0.02)
        assert np.allclose(df["time"], [0.0, 0.2, 0.4]), df["time"].tolist()  # col0, not dt
        assert np.allclose(df["x"], [0.05, 0.23, 0.21])
        assert np.allclose(df["y"], [0.31, 0.26, 0.15])
        assert np.allclose(df["z"], [0.10, 0.16, 0.19])
    finally:
        os.remove(path)


def test_sign_flip_ap_only():
    path = _write("trajectory\n0\t0\t5.0\n0\t0\t5.0\n")
    try:
        df = parse_hexamotion_trace(path, signs=(1, 1, -1))
        assert np.allclose(df["z"], [-5.0, -5.0]), df["z"].tolist()
    finally:
        os.remove(path)


def test_comma_delimited_raises_value_error():
    # A multi-row comma-delimited file is not whitespace-numeric -> ValueError,
    # which the ground-truth loader relies on to fall back to parse_robot_file.
    path = _write("1.0,2.0,3.0\n4.0,5.0,6.0\n")
    try:
        raised = False
        try:
            parse_hexamotion_trace(path)
        except ValueError:
            raised = True
        assert raised, "expected ValueError on comma-delimited input"
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
