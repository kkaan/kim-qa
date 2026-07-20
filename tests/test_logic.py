import sys

import pandas as pd

from kim_qa import parse_centroid_file, parse_trajectory_file, calculate_metrics

def test_parsing():
    centroid_file = r"Lyrebird Data\Centroid_248687_BeamID_3.1_3.2.txt"
    trajectory_file = r"Lyrebird Data\Static Test\MarkerLocationsGA_CouchShift_0.txt"

    print(f"Testing Centroid Parsing: {centroid_file}")
    try:
        centroid_data = parse_centroid_file(centroid_file)
        print("Centroid Data Extracted Successfully:")
        print(f"Seeds: {centroid_data['seeds']}")
        print(f"Isocenter: {centroid_data['isocenter']}")
        print(f"Expected Centroid (Iso): {centroid_data['expected_centroid']}")
    except Exception as e:
        print(f"FAILED to parse centroid file: {e}")
        return

    print(f"\nTesting Trajectory Parsing: {trajectory_file}")
    try:
        df = parse_trajectory_file(trajectory_file)
        print("Trajectory Data Parsed Successfully:")
        print(df.head())
        print(f"Shape: {df.shape}")
    except Exception as e:
        print(f"FAILED to parse trajectory file: {e}")
        return

    print("\nTesting Metrics Calculation")
    try:
        # Test with a small interval
        df_res, metrics = calculate_metrics(df, centroid_data['expected_centroid'], time_interval=(10, 20))
        print("Metrics Calculated Successfully:")
        for k, v in metrics.items():
            print(f"{k}: {v}")
    except Exception as e:
        print(f"FAILED to calculate metrics: {e}")

if __name__ == "__main__":
    test_parsing()
