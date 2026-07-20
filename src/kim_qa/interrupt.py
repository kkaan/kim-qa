"""Interrupt analysis: align KIM trajectories to robot ground truth."""
import numpy as np
from scipy.interpolate import interp1d


def apply_couch_shifts(lr, si, ap, file_index, shifts):
    """Subtract cumulative applied couch shift from each post-shift segment.

    Sign convention (kim-reporter): recorded_post = recorded_pre + applied_shift,
    so the no-shift counterfactual is recorded_post - applied_shift. For N file
    segments we have N-1 shifts (one between each pair of files).

    shifts: list of dicts {"ap", "si", "lr"} as returned by parse_couch_shifts.
    """
    n_segs = int(file_index.max()) + 1
    cum = np.zeros((n_segs, 3))   # rows: [lr, si, ap]
    for i, sh in enumerate(shifts[: n_segs - 1]):
        cum[i + 1] = cum[i] + np.array([sh["lr"], sh["si"], sh["ap"]])
    return (
        lr - cum[file_index, 0],
        si - cum[file_index, 1],
        ap - cum[file_index, 2],
    )


def process_interrupt_data(kim_df, robot_df, shifts, params=None):
    """
    Processes the data for interrupt analysis.
    """
    if kim_df.empty or robot_df.empty:
        return None, None

    # --- Step 1: Undo Couch Shifts from KIM Data ---
    # We need to know WHEN the shifts happened in the KIM data.
    # MATLAB uses 'shiftIndex' based on file lengths.
    # We have 'file_index' in kim_df.

    kim_df_processed = kim_df.copy()

    # Iterate through shifts
    # Shift 0 corresponds to transition from File 0 to File 1?
    # MATLAB: shiftIndex(n) = length(rawDataKIM{n}) + ...
    # So Shift 1 applies to everything AFTER File 0?
    # MATLAB loop:
    # for n = 1:noOfShifts
    #   dataKIM.yCent(shiftIndex(n):end) = dataKIM.yCent(...) - shiftsSI(n);

    # It seems shifts accumulate?
    # Or is it one shift per file transition?
    # "MarkerLocationsGA_CouchShift_0.txt" -> Initial
    # "MarkerLocationsGA_CouchShift_1.txt" -> After 1st shift?

    current_shift_ap = 0
    current_shift_si = 0
    current_shift_lr = 0

    # We assume shifts[i] happens before file[i+1]?
    # Let's assume shifts list length matches (num_files - 1).

    # Create a cumulative shift array for each row
    # But wait, MATLAB subtracts shiftsSI(n) from shiftIndex(n) to END.
    # This implies cumulative subtraction of EACH shift.

    # Let's identify the start index of each file > 0
    file_indices = sorted(kim_df['file_index'].unique())

    # Undo shifts
    for i, shift in enumerate(shifts):
        if i + 1 < len(file_indices):
            # Find index where file (i+1) starts
            file_idx = file_indices[i+1]
            mask = kim_df_processed['file_index'] >= file_idx

            kim_df_processed.loc[mask, 'meas_y'] -= shift['si']
            kim_df_processed.loc[mask, 'meas_x'] -= shift['lr']
            kim_df_processed.loc[mask, 'meas_z'] -= shift['ap']

    # --- Step 2: Time Alignment ---
    # Align KIM SI (y) with Robot Y (y)
    # MATLAB: findClosestSI(dataHexa, dataKIM)

    # Interpolate Robot Y to KIM timestamps

    # Ensure robot timestamps are sorted
    robot_df = robot_df.sort_values('time')

    # Create interpolator
    f_robot_y = interp1d(robot_df['time'], robot_df['y'], kind='linear', fill_value="extrapolate")

    # Search for optimal shift
    # MATLAB range: paramData(1):paramData(2):paramData(3) -> -400:0.01:20 ??
    # Let's use a reasonable range: -10s to +10s? Or larger if needed.
    # MATLAB default seems to be large.

    best_rmse = float('inf')
    best_shift = 0

    # Coarse search then fine search?
    # Let's try -50 to 50 seconds in 0.1s steps
    search_range = np.arange(-50, 50, 0.1)

    kim_si = kim_df_processed['meas_y'].values
    kim_time = kim_df_processed['time'].values

    for shift_val in search_range:
        shifted_time = kim_time + shift_val
        # Only compare where times overlap
        # But simpler to just interpolate robot at shifted times

        # We need robot_y at (kim_time + shift)
        # Wait, MATLAB: interp1(dataHexa.timestamps, dataHexa.y, dataKIM.timestamps + shiftValues(n))
        # So we shift KIM time to match Robot time?
        # If KIM starts at 0, and Robot starts at 0, but there is latency/offset.

        interp_robot_y = f_robot_y(kim_time + shift_val)

        # RMSE
        rmse = np.sqrt(np.mean((kim_si - interp_robot_y)**2))

        if rmse < best_rmse:
            best_rmse = rmse
            best_shift = shift_val

    # Apply best shift + latency (0.350 from MATLAB)
    latency = 0.350
    total_shift = best_shift + latency
    kim_df_processed['time'] = kim_df_processed['time'] + total_shift

    # --- Step 3: Reapply Shifts ---
    # Add shifts back to KIM
    for i, shift in enumerate(shifts):
        if i + 1 < len(file_indices):
            file_idx = file_indices[i+1]
            mask = kim_df_processed['file_index'] >= file_idx

            kim_df_processed.loc[mask, 'meas_y'] += shift['si']
            kim_df_processed.loc[mask, 'meas_x'] += shift['lr']
            kim_df_processed.loc[mask, 'meas_z'] += shift['ap']

            # Add shifts to Robot data at corresponding times
            # We need to find WHEN this shift happens in Robot time
            # MATLAB: hexaShiftIndex = find(abs((dataHexa.timestamps - dataKIM.timestamps(shiftIndex(n)))) < ...)

            # Find timestamp of the first point of the file in KIM (shifted time)
            shift_time = kim_df_processed.loc[kim_df_processed['file_index'] == file_idx, 'time'].iloc[0]

            robot_mask = robot_df['time'] >= shift_time
            robot_df.loc[robot_mask, 'y'] += shift['si']
            robot_df.loc[robot_mask, 'x'] += shift['lr']
            robot_df.loc[robot_mask, 'z'] += shift['ap']

    # --- Step 4: Calculate Metrics ---
    # Interpolate Robot to KIM time (final)
    f_robot_x = interp1d(robot_df['time'], robot_df['x'], kind='linear', fill_value="extrapolate")
    f_robot_y = interp1d(robot_df['time'], robot_df['y'], kind='linear', fill_value="extrapolate")
    f_robot_z = interp1d(robot_df['time'], robot_df['z'], kind='linear', fill_value="extrapolate")

    kim_time_final = kim_df_processed['time']

    robot_interp_x = f_robot_x(kim_time_final)
    robot_interp_y = f_robot_y(kim_time_final)
    robot_interp_z = f_robot_z(kim_time_final)

    # Differences (KIM - Robot)
    diff_x = kim_df_processed['meas_x'] - robot_interp_x
    diff_y = kim_df_processed['meas_y'] - robot_interp_y
    diff_z = kim_df_processed['meas_z'] - robot_interp_z

    metrics = {
        'mean_lr': np.mean(diff_x),
        'mean_si': np.mean(diff_y),
        'mean_ap': np.mean(diff_z),
        'std_lr': np.std(diff_x),
        'std_si': np.std(diff_y),
        'std_ap': np.std(diff_z),
        'p5_lr': np.percentile(diff_x, 5),
        'p95_lr': np.percentile(diff_x, 95),
        'p5_si': np.percentile(diff_y, 5),
        'p95_si': np.percentile(diff_y, 95),
        'p5_ap': np.percentile(diff_z, 5),
        'p95_ap': np.percentile(diff_z, 95),
    }

    # Add interpolated robot data to dataframe for plotting
    kim_df_processed['robot_x'] = robot_interp_x
    kim_df_processed['robot_y'] = robot_interp_y
    kim_df_processed['robot_z'] = robot_interp_z

    return kim_df_processed, metrics
