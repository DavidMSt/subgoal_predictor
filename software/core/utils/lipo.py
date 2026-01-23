def lipo_soc(voltage, cells):
    """
    Approximate LiPo state of charge (percent) from pack voltage and cell count.

    Args:
        voltage (float): Measured pack voltage (V).
        cells (int): Number of series cells (S count).

    Returns:
        float: Estimated SOC in percent (0–100).

    Notes:
        - Uses a typical open-circuit per-cell discharge curve with piecewise-linear interpolation.
        - Assumes resting voltage (let the pack rest ~1–5 minutes after load/charge for best results).
        - Under load, voltage sag will make SOC appear lower than actual.
        - Do NOT use this to set safety cutoffs for flight/vehicles—use cell-level monitoring and margins.
    """
    if cells <= 0:
        raise ValueError("cells must be >= 1")

    # Per-cell voltage waypoints (V) mapped to SOC (%) for a *typical* LiPo.
    # Source: consolidated hobby/RC references + common manufacturer curves (approximate).
    # Tweak points if your cells behave differently.
    # curve = [
    #     (4.20, 100.0),
    #     (4.15, 95.0),
    #     (4.10, 90.0),
    #     (4.05, 85.0),
    #     (4.00, 80.0),
    #     (3.95, 75.0),
    #     (3.92, 70.0),
    #     (3.90, 65.0),
    #     (3.87, 60.0),
    #     (3.85, 55.0),
    #     (3.83, 50.0),
    #     (3.80, 45.0),
    #     (3.78, 40.0),
    #     (3.76, 35.0),
    #     (3.74, 30.0),
    #     (3.72, 25.0),
    #     (3.70, 20.0),
    #     (3.66, 15.0),
    #     (3.60, 10.0),
    #     (3.50, 5.0),
    #     (3.00, 0.0),   # treat ~3.0 V/cell as "empty" for this rough estimate
    # ]

    curve = [
        (4.20, 100.0),
        (4.15, 95.0),
        (4.10, 90.0),
        (4.05, 85.0),
        (4.00, 80.0),
        (3.95, 75.0),
        (3.92, 70.0),
        (3.90, 65.0),
        (3.87, 60.0),
        (3.85, 55.0),
        (3.83, 50.0),
        (3.80, 45.0),
        (3.78, 40.0),
        (3.76, 35.0),
        (3.74, 30.0),
        (3.72, 25.0),
        (3.70, 23.0),
        (3.66, 22.0),
        (3.60, 21.0),
        (3.50, 20.0),
        (3.30, 10.0),
        (3.00, 0.0),  # treat ~3.0 V/cell as "empty"
    ]

    v_per_cell = voltage / cells

    # Clamp outside range
    if v_per_cell >= curve[0][0]:
        return 1
    if v_per_cell <= curve[-1][0]:
        return 0.0

    # Find the segment and interpolate
    for i in range(len(curve) - 1):
        v_hi, soc_hi = curve[i]
        v_lo, soc_lo = curve[i + 1]
        if v_lo <= v_per_cell <= v_hi:
            # Linear interpolation between (v_hi, soc_hi) and (v_lo, soc_lo)
            t = (v_per_cell - v_lo) / (v_hi - v_lo)
            return (soc_lo + t * (soc_hi - soc_lo)) / 100

    # Fallback (shouldn't hit due to clamping and loop logic)
    return 0.0

# --- examples ---
# 4S pack at 15.2 V (3.80 V/cell) ~ ~45-50%
# print(lipo_soc(15.2, 4))  # -> about 47%
# 3S pack at 12.0 V (4.00 V/cell) ~ ~80%
# print(lipo_soc(12.0, 3))  # -> about 80%
