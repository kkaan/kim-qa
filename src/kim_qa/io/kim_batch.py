"""Batch-parse MarkerLocationsGA_CouchShift_*.txt files from a folder."""
import glob
import os
import re

import numpy as np
import pandas as pd


def parse_kim_data(folder_path):
    """
    Parses all MarkerLocationsGA_CouchShift_*.txt files in the folder.
    Returns a combined DataFrame with timestamps, gantry, and calculated centroids.
    """
    # Find all matching files
    files = glob.glob(os.path.join(folder_path, "MarkerLocationsGA_CouchShift_*.txt"))

    # Sort files by index (MarkerLocationsGA_CouchShift_0.txt, _1.txt, etc.)
    # Extract number from filename to sort correctly
    def get_file_index(filepath):
        match = re.search(r"MarkerLocationsGA_CouchShift_(\d+)\.txt", filepath)
        return int(match.group(1)) if match else -1

    files.sort(key=get_file_index)

    all_data = []

    for filepath in files:
        try:
            # Read file
            # Format: Frame No, Time, Gantry, ...
            df = pd.read_csv(filepath)
            df.columns = df.columns.str.strip()

            # Dynamically detect marker columns
            num_markers = 0
            for i in range(10):
                if f'Marker_{i}_AP' in df.columns:
                    num_markers += 1
                else:
                    break

            for index, row in df.iterrows():
                # Extract all available markers
                markers = []
                for i in range(num_markers):
                    markers.append({
                        'ap': row[f'Marker_{i}_AP'],
                        'lr': row[f'Marker_{i}_LR'],
                        'si': row[f'Marker_{i}_SI']
                    })

                # Sort by SI (descending)
                markers.sort(key=lambda x: x['si'], reverse=True)

                avg_lr = np.mean([m['lr'] for m in markers])
                avg_si = np.mean([m['si'] for m in markers])
                avg_ap = np.mean([m['ap'] for m in markers])

                all_data.append({
                    'time': row['Time (sec)'],
                    'gantry': row['Gantry'],
                    'meas_x': avg_lr, # LR
                    'meas_y': avg_si, # SI
                    'meas_z': avg_ap, # AP
                    'file_index': get_file_index(filepath)
                })

        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            continue

    if not all_data:
        return pd.DataFrame()

    combined_df = pd.DataFrame(all_data)

    # Normalize timestamps (start at 0)
    if not combined_df.empty:
        combined_df['time'] = combined_df['time'] - combined_df['time'].iloc[0]

    return combined_df
