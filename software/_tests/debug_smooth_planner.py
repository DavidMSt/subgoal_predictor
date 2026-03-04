"""
Standalone debug script for OMPLSmoothPathPlanner.

Replicates the CollisionWallScenario exactly (agent at (0,-2.5,pi/2),
task at (0,2.5), vertical wall at x=0, y=0, psi=pi/2, 4x0.2m) but runs
only the planner code — no GUI, no simulation loop.

Run from the repo root:
    source .venv/bin/activate
    python -m _tests.debug_smooth_planner
"""

import math
import numpy as np

# ── 1. Minimal container stubs ──────────────────────────────────────────────

from dataclasses import dataclass, field
from collections import OrderedDict
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import (
    AgentMPPlannerConfig, AgentMPPlannerContainer,
)
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import (
    MPPhaseContainer, MPPhaseConfig,
)

# -- Agent container (real one from codebase) --------------------------------
from master_thesis.containers.general_containers.frodo_agent_container import (
    FRODOAgentContainer, FRODO_Agent_Config, FRODO_AgentState,
)

# -- LocalWorldContainer (real one) ------------------------------------------
from master_thesis.containers.general_containers.local_world_container import (
    LocalWorldContainer, LocalWorldConfig, LocalWorldState,
)

# -- ObstacleContainer --------------------------------------------------------
from master_thesis.containers.general_containers.obstacle_container import (
    ObstacleContainer, Obstacle_Config,
)

# ── 2. Build containers for CollisionWallScenario ───────────────────────────

LIMITS = ((-4.0, 4.0), (-4.0, 4.0))
DT = 0.01

# Agent: start at (0, -2.5), heading up (pi/2)
agent_config = FRODO_Agent_Config(
    length=0.155, width=0.155, height=0.15,
    color=(1, 1, 1), Ts=DT,
)
agent_state = FRODO_AgentState(x=0.0, y=-2.5, psi=math.pi / 2, v=0.0, psi_dot=0.0)
agent_cont = FRODOAgentContainer(config=agent_config, state=agent_state, agent_id='dbg_agent')

# Wall: x=0, y=0, psi=pi/2, 4m long x 0.2m wide  (vertical wall)
wall_config = Obstacle_Config(
    x=0.0, y=0.0, psi=math.pi / 2,
    length=4.0, width=0.2, height=1.0,
    shape='box',
)
wall_cont = ObstacleContainer(config=wall_config, state=None, object_id='wall')

# LocalWorldContainer with the wall visible
lwr_state = LocalWorldState()
lwr_state.obstacles = {'wall': wall_cont}
lwr_state.neighbors = {}
lwr_cont = LocalWorldContainer(
    config=LocalWorldConfig(limits=LIMITS),
    state=lwr_state,
)

# MP planner container
from core.utils.logging_utils import Logger
logger = Logger('debug_smooth_planner', 'DEBUG')
mp_config = AgentMPPlannerConfig(timelimit=10.0, planner='rrt')
mp_cont = AgentMPPlannerContainer(config=mp_config, logger=logger)

# Goal: (0, 2.5)
mp_cont.start = np.array([0.0, -2.5, math.pi / 2])
mp_cont.goal  = np.array([0.0,  2.5,  math.pi / 2])

# ── 3. Instantiate the planner ───────────────────────────────────────────────

from master_thesis.modules.motion_planning.helper.ompl_planner import OMPLSmoothPathPlanner
from master_thesis.modules.motion_planning.helper.opt_safe import (
    FRODOFlatOpt, OptimizationData,
)

planner = OMPLSmoothPathPlanner(
    mp_container=mp_cont,
    agent_container=agent_cont,
    lwr_container=lwr_cont,
)

# ── 4. Run OMPL geometric solve ─────────────────────────────────────────────

print("\n" + "="*60)
print("STEP 1: OMPL geometric solve")
print("="*60)

from ompl import geometric as og

planner._pdef = planner._create_pdef()
planner._planner = planner.create_planner()
planner._planner.setProblemDefinition(planner._pdef)
planner.check_pdef_validity()

solved = planner._planner.solve(10.0)
print(f"  solved = {solved}")
print(f"  hasExactSolution = {planner._pdef.hasExactSolution()}")

if not solved or not planner._pdef.hasExactSolution():
    print("  OMPL failed — stopping here.")
    exit(1)

path = planner._pdef.getSolutionPath()
simplifier = og.PathSimplifier(planner._si)
simplifier.reduceVertices(path)
simplifier.collapseCloseVertices(path)

n = path.getStateCount()
waypoints = [[path.getState(i).getX(), path.getState(i).getY()] for i in range(n)]
print(f"  Waypoints ({n}):")
for i, wp in enumerate(waypoints):
    print(f"    [{i}] ({wp[0]:.3f}, {wp[1]:.3f})")

# ── 5. Build OptimizationData ────────────────────────────────────────────────

print("\n" + "="*60)
print("STEP 2: _build_opt_data()")
print("="*60)

opt_data = planner._build_opt_data(waypoints)
print(f"  bound_min  = {opt_data.bound_min}")
print(f"  bound_high = {opt_data.bound_high}")
print(f"  start      = {opt_data.start}")
print(f"  goal       = {opt_data.goal}")
print(f"  start_psi  = {opt_data.start_psi:.4f} rad = {math.degrees(opt_data.start_psi):.1f} deg")
print(f"  obstacles ({len(opt_data.obstacles)}):")
for i, obs in enumerate(opt_data.obstacles):
    print(f"    [{i}] xmin={obs[0]:.3f} xmax={obs[1]:.3f} ymin={obs[2]:.3f} ymax={obs[3]:.3f}")

# Check: does each waypoint satisfy each obstacle AABB constraint?
print("\n  Waypoint / obstacle clearance check:")
for i, wp in enumerate(waypoints):
    for j, obs in enumerate(opt_data.obstacles):
        xmin, xmax, ymin, ymax = obs
        inside = (xmin <= wp[0] <= xmax) and (ymin <= wp[1] <= ymax)
        flag = " *** INSIDE ***" if inside else ""
        print(f"    wp[{i}]=({wp[0]:.2f},{wp[1]:.2f}) vs obs[{j}]: "
              f"x in [{xmin:.2f},{xmax:.2f}] y in [{ymin:.2f},{ymax:.2f}]{flag}")

# ── 6. Run FRODOFlatOpt pipeline ─────────────────────────────────────────────

print("\n" + "="*60)
print("STEP 3: FRODOFlatOpt.find_hyperplanes()")
print("="*60)

_, v_hi = mp_cont.v_bounds
_, w_hi = mp_cont.theta_dot_bounds
opt = FRODOFlatOpt(opt_data, dt=agent_cont.Ts or DT,
                   v_max=v_hi, psi_dot_max=w_hi)

opt.find_hyperplanes()
print(f"  feasible after find_hyperplanes = {opt.feasible}")
print(f"  Number of segments: {len(opt.hyperplanes)}")
for i, seg_hps in enumerate(opt.hyperplanes):
    pa = waypoints[i]
    pb = waypoints[i + 1]
    print(f"  Segment [{i}] ({pa[0]:.2f},{pa[1]:.2f}) → ({pb[0]:.2f},{pb[1]:.2f}): "
          f"{len(seg_hps)} hyperplanes")
    for j, hp in enumerate(seg_hps):
        w, b = hp
        # Check each waypoint satisfies the constraint: w·p + b >= 0
        va = float(np.array(w) @ np.array(pa) + b)
        vb = float(np.array(w) @ np.array(pb) + b)
        ok_a = "OK" if va >= 0 else f"VIOLATED (={va:.4f})"
        ok_b = "OK" if vb >= 0 else f"VIOLATED (={vb:.4f})"
        print(f"    hp[{j}]: w={np.round(w,2)} b={b:.3f}  "
              f"pa→{ok_a}  pb→{ok_b}")

print("\n" + "="*60)
print("STEP 4: create_bezier()")
print("="*60)

opt.create_optimization_vars()
opt.create_bezier()
print(f"  feasible after create_bezier = {opt.feasible}")
if not opt.feasible:
    print("  Bézier optimization failed — stopping here.")
    exit(1)

print(f"  Number of control-point sets: {len(opt.control_points)}")
for i, ctrl_pts in enumerate(opt.control_points):
    print(f"  Segment [{i}] control points:")
    for j, p in enumerate(ctrl_pts):
        print(f"    P{j} = ({p[0]:.4f}, {p[1]:.4f})")

# ── 7. bezier_to_configurations + trajectory ─────────────────────────────────

print("\n" + "="*60)
print("STEP 5: bezier_to_configurations() + get_trajectory() + pre-rotation")
print("="*60)

dt = DT
opt.dt = dt
opt.bezier_to_configurations()
print(f"  T_guess after scaling = {opt.T_guess:.3f}s")

states, actions = opt.get_trajectory(dt)
print(f"  states.shape  = {states.shape}")
print(f"  actions.shape = {actions.shape}")

# First few states + actions
print("\n  First 5 and last 5 states [x, y, psi]:")
for idx in list(range(5)) + list(range(-5, 0)):
    s = states[idx]
    print(f"    [{idx:4d}] x={s[0]:.4f} y={s[1]:.4f} psi={math.degrees(s[2]):.1f}°")

print("\n  First 5 and last 5 actions [v, psi_dot]:")
for idx in list(range(5)) + list(range(-5, 0)):
    a = actions[idx]
    print(f"    [{idx:4d}] v={a[0]:.4f} psi_dot={math.degrees(a[1]):.2f}°/s")

print(f"\n  v range:       [{actions[:,0].min():.4f}, {actions[:,0].max():.4f}] (max allowed: {v_hi})")
print(f"  psi_dot range: [{math.degrees(actions[:,1].min()):.2f}, {math.degrees(actions[:,1].max()):.2f}] °/s (max allowed: {math.degrees(w_hi):.1f}°/s)")

# Check pre-rotation
flat_psi_0 = float(states[0, 2])
agent_psi = math.pi / 2
delta_psi = (flat_psi_0 - agent_psi + math.pi) % (2 * math.pi) - math.pi
psi_dot_max = w_hi
if abs(delta_psi) > 0.05:
    n_rot = math.ceil(abs(delta_psi) / (psi_dot_max * dt))
    print(f"\n  PRE-ROTATION NEEDED:")
    print(f"    flat_psi_0 = {math.degrees(flat_psi_0):.1f}°")
    print(f"    agent_psi  = {math.degrees(agent_psi):.1f}°")
    print(f"    delta_psi  = {math.degrees(delta_psi):.1f}°")
    print(f"    n_rot steps = {n_rot} ({n_rot*dt:.3f}s)")
else:
    print(f"\n  No pre-rotation needed (delta_psi = {math.degrees(delta_psi):.1f}°)")

# Verify start matches agent position + heading
print(f"\n  Start check:")
print(f"    Expected  x={0.0:.4f} y={-2.5:.4f} psi={math.degrees(math.pi/2):.1f}°")
print(f"    Actual    x={states[0,0]:.4f} y={states[0,1]:.4f} psi={math.degrees(states[0,2]):.1f}°")
print(f"    Initial action: v={actions[0,0]:.4f}  psi_dot={math.degrees(actions[0,1]):.2f}°/s")

# Simulate what executor would do for first 10 steps
print(f"\n  Simulated execution (Euler, dt={dt}):")
x, y, psi = states[0, 0], states[0, 1], states[0, 2]
print(f"    t=0.00  x={x:.4f} y={y:.4f} psi={math.degrees(psi):.1f}°")
for k in range(min(10, len(actions))):
    v_k = actions[k, 0]
    w_k = actions[k, 1]
    x   += v_k * math.cos(psi) * dt
    y   += v_k * math.sin(psi) * dt
    psi += w_k * dt
    print(f"    t={dt*(k+1):.2f}  x={x:.4f} y={y:.4f} psi={math.degrees(psi):.1f}°  "
          f"(traj: x={states[k+1,0]:.4f} y={states[k+1,1]:.4f} psi={math.degrees(states[k+1,2]):.1f}°)")

print("\n" + "="*60)
print("DEBUG COMPLETE")
print("="*60)
