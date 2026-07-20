"""Load a ground-truth motion trace as a time/x/y/z frame, auto-detecting format."""
from kim_qa.io.hexamotion import parse_hexamotion_trace
from kim_qa.io.robot import parse_robot_file


def parse_ground_truth_file(filepath, dt=0.020, signs=(1.0, 1.0, 1.0)):
    """Return a ground-truth trace as a DataFrame[time, x, y, z] (mm).

    Delegates to parse_hexamotion_trace, which self-detects the 3-column
    (implicit dt) vs >=4-column (explicit col0 time) whitespace layouts and
    applies per-axis signs. A comma-delimited robot file makes the whitespace
    parser raise ValueError; in that case fall back to parse_robot_file.
    """
    try:
        return parse_hexamotion_trace(filepath, dt=dt, signs=signs)
    except ValueError:
        return parse_robot_file(filepath)
