# RT_Plot Race Condition Bug Fix

## Problem Summary

**Symptoms:**
- ALL plots suddenly start jumping between only two values (e.g., 93.1 and 0.2)
- Occurs unpredictably (sometimes after 10 seconds, sometimes after minutes)
- DigitalNumberWidgets show correct values (data is fine)
- Refreshing the browser page doesn't help
- Restarting the robot doesn't help
- **Only restarting the Python application fixes it**

## Root Cause

**Race condition in `RT_Plot_Backend` between the background update thread and the main thread.**

### The Issue

1. `RT_Plot_Backend` runs a background thread (`_task()`) that continuously reads `self.time_series` dict:
   ```python
   def _task(self) -> None:
       while not self._exit:
           self._send_value_update()  # Calls get_data()
           self.interval_timer.sleep_until_next()

   def get_data(self) -> dict:
       data = {k: ts.get_data() for k, ts in self.time_series.items()}  # ⚠️ UNSAFE!
       return data
   ```

2. The main thread modifies `self.time_series` when adding/removing timeseries:
   ```python
   def add_timeseries(self, timeseries, config=None):
       self.time_series[id] = timeseries  # ⚠️ UNSAFE!

   def remove_timeseries(self, timeseries):
       del self.time_series[timeseries_id]  # ⚠️ UNSAFE!
   ```

3. **When these operations happen concurrently**, Python's dict can return corrupted data during iteration, causing:
   - Wrong values to be returned
   - The dict comprehension to access stale object references
   - Data to appear to "jump" between values

### Why ALL Plots Fail Together

The race condition corrupts the dict iteration itself, not individual timeseries. Once the dict is corrupted, ALL subsequent reads return wrong data until the application is restarted.

### Why It's Non-Deterministic

Race conditions depend on exact timing. The bug triggers when:
- The background thread is inside the dict comprehension in `get_data()`
- AND the main thread modifies `self.time_series` at the same moment
- This timing varies based on system load, number of plots, update rate, etc.

## The Fix

Added **thread-safe access** using a `threading.Lock()`:

### 1. Added Lock in `__init__`
```python
# Thread lock to protect concurrent access to time_series and y_axes dicts
self._lock = threading.Lock()
```

### 2. Protected `get_data()` (Called by Background Thread)
```python
def get_data(self) -> dict:
    with self._lock:
        # Create a snapshot of the dict to avoid holding lock during iteration
        time_series_snapshot = dict(self.time_series)

    # Now iterate over the snapshot without holding the lock
    data = {k: ts.get_data() for k, ts in time_series_snapshot.items()}
    return data
```

**Why snapshot?** We create a shallow copy inside the lock, then release it. This minimizes lock contention while ensuring we iterate over a consistent view.

### 3. Protected All Modification Operations

- `add_timeseries()` - Wraps dict write in lock
- `remove_timeseries()` - Wraps dict delete in lock
- `remove_all_timeseries()` - Takes snapshot before iterating
- `add_y_axis()` - Wraps dict write in lock
- `remove_y_axis()` - Wraps dict delete in lock
- `get_payload()` - Takes snapshots of both dicts

## Performance Impact

**Minimal.** The lock is held very briefly (microseconds) only during dict operations. The actual data processing happens outside the lock.

## Testing Recommendations

1. **Stress test**: Run multiple robots with many plots for extended periods
2. **Dynamic plots**: Add/remove timeseries while plots are running
3. **High update rate**: Test with Ts=0.01 (100Hz updates) to increase race probability
4. **Monitor**: Look for any plots showing identical/frozen values

## Related Files Modified

- `/extensions/gui/src/lib/plot/realtime/rt_plot.py` - Added threading lock protection

## Notes

- This is a **critical bug fix** for production use
- The bug was subtle because Python's GIL provides *some* protection, but not enough for dict iteration
- Similar patterns should be reviewed in other threaded code (map.py, data streaming, etc.)

---
**Fixed:** 2026-01-19
**Identified by:** Analysis of symptoms and code inspection
**Severity:** High (data corruption, unpredictable failures)
