"""Unified PRM* roadmap loading and sharing.

Both the GUI and the RL training wrapper call load_and_share_roadmap() rather
than implementing their own caching.  The module-level cache means:

  - Within one Python process the file is read exactly once per scenario,
    regardless of how many sim resets happen.
  - Resetting the GUI and reloading the same scenario is instant — the cached
    PlannerRoadmap object is re-injected into the fresh agents.
  - RL training workers (separate processes via multiprocessing spawn) each
    get their own cache, so each worker also loads once.

Thread-safety: the cache is protected by a lock.  Concurrent calls for the
same scenario block until the first load completes, then all share the result.
"""

from __future__ import annotations

import os
import threading

_roadmap_cache: dict = {}       # scenario_name → PlannerRoadmap
_cache_lock = threading.Lock()

_ROADMAPS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), 'roadmaps'))


def roadmap_filepath(scenario_name: str, roadmap_dir: str | None = None) -> str:
    """Canonical path for a scenario's saved PRM* roadmap file."""
    return os.path.join(roadmap_dir or _ROADMAPS_DIR, f"{scenario_name}.npy")


def load_and_share_roadmap(sim, scenario_name: str,
                           roadmap_dir: str | None = None) -> bool:
    """Load the PRM* roadmap once per process and share it to all sim agents.

    On the first call for *scenario_name* the .npy file is read and the
    PlannerRoadmap object is stored in the module-level cache.  All subsequent
    calls (e.g. after a sim reset) skip the file I/O and inject the cached
    object directly — this makes repeated episodes cheap.

    Args:
        sim:           A FRODO_Universal_Simulation whose agents will receive
                       the roadmap via sim.share_roadmap().
        scenario_name: Scenario identifier, used to locate the .npy file and
                       as the cache key.
        roadmap_dir:   Override the default roadmaps directory.

    Returns:
        True  — roadmap file exists and was shared to all agents.
        False — no roadmap file found; callers should build or warn accordingly.
    """
    filepath = roadmap_filepath(scenario_name, roadmap_dir)
    if not os.path.exists(filepath):
        return False

    with _cache_lock:
        if scenario_name not in _roadmap_cache:
            from master_thesis.modules.motion_planning.ompl_trajectory_planner import (
                OMPLTrajectoryPlanner,
            )
            loader = next(
                (a.planner for a in sim.agents.values()
                 if isinstance(a.planner, OMPLTrajectoryPlanner)),
                None,
            )
            if loader is None:
                return False
            _roadmap_cache[scenario_name] = loader.load_roadmap_from_file(filepath)

    sim.share_roadmap(_roadmap_cache[scenario_name])
    return True


def is_roadmap_cached(scenario_name: str) -> bool:
    """Return True if the roadmap for *scenario_name* is already in memory."""
    with _cache_lock:
        return scenario_name in _roadmap_cache


def cache_built_roadmap(scenario_name: str, roadmap) -> None:
    """Store a freshly-built roadmap in the cache.

    Call this after buildRoadmap() completes so that subsequent
    load_and_share_roadmap() calls use the in-memory object rather than
    re-reading the file that was just written.
    """
    with _cache_lock:
        _roadmap_cache[scenario_name] = roadmap
