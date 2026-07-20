"""Parse 7-column robot/hexa ground-truth trace files."""
import pandas as pd


def parse_robot_file(filepath):
    """
    Parses the Robot/Hexa trace file.
    Expects 7 columns. Returns DataFrame with time, x, y, z.
    """
    try:
        # Try reading with space delimiter
        df = pd.read_csv(filepath, sep=r'\s+', header=None, engine='python')

        # If only 1 column, maybe it's comma separated?
        if df.shape[1] < 4:
             df = pd.read_csv(filepath, header=None)

        # Rename columns (assuming first 4 are Time, X, Y, Z)
        # MATLAB: dataHexa.x = (1).*rawDataHexa{2}; y=3, z=4
        # Col 0: Time? MATLAB says rawDataHexa{1} is timestamps.

        df = df.iloc[:, :4]
        df.columns = ['time', 'x', 'y', 'z']

        return df

    except Exception as e:
        print(f"Error parsing robot file: {e}")
        return pd.DataFrame()
