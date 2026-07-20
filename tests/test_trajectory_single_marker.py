"""parse_trajectory_file accepts a single-marker (Marker_0 only) KIM trajectory."""
import os
import sys
import tempfile

from kim_qa import parse_trajectory_file

# One Marker_0 group; meas_x=LR, meas_y=SI, meas_z=AP (single marker => avg == itself)
SINGLE_MARKER_CSV = (
    "Frame No, Time (sec), Gantry, Marker_0_AP, Marker_0_LR, Marker_0_SI\n"
    "0, 0.000, 90.0, 1.0, 2.0, 3.0\n"
    "1, 0.500, 89.0, 1.1, 2.1, 3.1\n"
)


def test_single_marker_trajectory_parses():
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(SINGLE_MARKER_CSV)
    try:
        df = parse_trajectory_file(path)
        assert len(df) == 2, len(df)
        row0 = df.iloc[0]
        assert row0["meas_x"] == 2.0, row0["meas_x"]   # LR
        assert row0["meas_y"] == 3.0, row0["meas_y"]   # SI
        assert row0["meas_z"] == 1.0, row0["meas_z"]   # AP
        assert row0["time"] == 0.0, row0["time"]
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
