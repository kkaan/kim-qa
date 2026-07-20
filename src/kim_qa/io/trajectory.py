"""Parse a single KIM trajectory log into per-frame measured centroids."""
import numpy as np
import pandas as pd


def parse_trajectory_file(filepath):
    """
    Parses the trajectory file (CSV-like).
    Returns a pandas DataFrame with processed coordinates.
    """
    # Read the file, skipping the first line if it's just a header count or similar (MATLAB skips 1 line)
    # Based on the file content view, the first line IS the header.
    # "Frame No, Time (sec), ..."

    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        # Fallback for potential formatting issues or if header is on second line
        df = pd.read_csv(filepath, skiprows=1)

    # Clean column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Dynamically detect marker columns
    num_markers = 0
    for i in range(10):
        if f'Marker_{i}_AP' in df.columns:
            num_markers += 1
        else:
            break

    if num_markers < 1:
        raise ValueError(f"Need at least 1 marker in trajectory file, found {num_markers}.")

    processed_data = []

    for index, row in df.iterrows():
        # Extract all available markers
        markers = []
        for i in range(num_markers):
            markers.append({
                'ap': row[f'Marker_{i}_AP'],
                'lr': row[f'Marker_{i}_LR'],
                'si': row[f'Marker_{i}_SI']
            })

        # Sort by SI (descending) for consistent ordering
        markers.sort(key=lambda x: x['si'], reverse=True)

        # Calculate Centroid of measured markers
        avg_lr = np.mean([m['lr'] for m in markers])
        avg_si = np.mean([m['si'] for m in markers])
        avg_ap = np.mean([m['ap'] for m in markers])

        processed_data.append({
            'time': row['Time (sec)'],
            'gantry': row['Gantry'],
            'meas_x': avg_lr,
            'meas_y': avg_si,
            'meas_z': avg_ap
        })

    return pd.DataFrame(processed_data)
