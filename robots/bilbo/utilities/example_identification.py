"""Example: Complete System Identification Pipeline for BILBO
=============================================================

Demonstrates the full workflow:
1. Linearize the known nonlinear BILBO dynamics at equilibrium
2. Design a stabilizing discrete LQR controller
3. Generate training data from the nonlinear model under closed-loop control
4. Identify both linear and nonlinear models from data
5. Generate new test trajectories for validation
6. Create comparison plots

Run from the robots/bilbo/utilities/ directory:
    python example_identification.py
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.linalg import solve_discrete_are
import logging

from system_identification import (
    TrajectoryData, IdentificationConfig, identify_system,
    simulate_linear, simulate_hybrid, print_model,
    IX, IY, IV, ITHETA, ITHETA_DOT, IPSI, IPSI_DOT,
    N_STATES, N_INPUTS, STATE_NAMES, INPUT_NAMES, DYNAMIC_ROWS,
)
from nonlinear_identification import (
    identify_nonlinear, NonlinearConfig, get_default_parameter_specs,
    generate_synthetic_data, simulate_nonlinear, bilbo_dynamics_3d,
    print_result, TRUE_PARAMS, PARAM_NAMES,
)

logging.basicConfig(level=logging.INFO, format='%(message)s')

# Ground truth parameters (DEFAULT_BILBO_MODEL from bilbo_model.py)
PARAMS = dict(TRUE_PARAMS)
DT = 0.01  # 100 Hz control rate


# ===========================================================================
# Step 1: Linearize the nonlinear dynamics at theta=0
# ===========================================================================

def linearize_bilbo(params, dt):
    """Linearize BILBO 3D dynamics at theta=0 equilibrium.

    Returns continuous A_c, B_c and Euler-discretized A_d, B_d
    for the full 7-state system [x, y, v, theta, theta_dot, psi, psi_dot].

    Includes the dissipative tau_theta and tau_x terms (which the existing
    linear model classes in bilbo_model.py omit).
    """
    g = 9.81
    p = params
    m_b, m_w, l, d_w = p['m_b'], p['m_w'], p['l'], p['d_w']
    I_w, I_y, I_x, I_z = p['I_w'], p['I_y'], p['I_x'], p['I_z']
    c_a, r_w = p['c_alpha'], p['r_w']
    tau_t, tau_v = p['tau_theta'], p['tau_x']

    # Effective masses and inertias
    M = m_b + 2 * m_w + 2 * I_w / r_w**2
    J = I_y + m_b * l**2
    ml = m_b * l

    # Denominators at theta=0 (cos=1, sin=0)
    V_1 = M * J - ml**2
    V_2 = I_z + 2 * I_w + (m_w + I_w / r_w**2) * d_w**2 / 2

    # Damping coefficients (at theta=0)
    D_11 = J * 2 * c_a / r_w**2 - ml * 2 * c_a / r_w
    D_12 = J * 2 * c_a / r_w - ml * 2 * c_a
    D_21 = M * 2 * c_a / r_w + ml * 2 * c_a / r_w**2
    D_22 = M * 2 * c_a + ml * 2 * c_a / r_w
    D_33 = d_w**2 / (2 * r_w**2) * c_a

    # Gravity coupling
    C_11 = ml**2
    C_21 = M * ml

    # Input coupling (at theta=0)
    B_1 = J / r_w + ml
    B_2 = ml / r_w + M
    B_3 = d_w / (2 * r_w)

    # Continuous-time state matrix (7x7)
    A_c = np.zeros((N_STATES, N_STATES))
    B_c = np.zeros((N_STATES, N_INPUTS))

    # Kinematics (at psi=0: x_dot = v, y_dot = 0)
    A_c[IX, IV] = 1.0
    A_c[ITHETA, ITHETA_DOT] = 1.0
    A_c[IPSI, IPSI_DOT] = 1.0

    # v dynamics (including dissipative tau_x)
    A_c[IV, IV] = -D_11 / V_1 - tau_v
    A_c[IV, ITHETA] = -C_11 * g / V_1
    A_c[IV, ITHETA_DOT] = D_12 / V_1
    B_c[IV, :] = [B_1 / V_1, B_1 / V_1]

    # theta_dot dynamics (including dissipative tau_theta)
    A_c[ITHETA_DOT, IV] = D_21 / V_1
    A_c[ITHETA_DOT, ITHETA] = C_21 * g / V_1
    A_c[ITHETA_DOT, ITHETA_DOT] = -D_22 / V_1 - tau_t
    B_c[ITHETA_DOT, :] = [-B_2 / V_1, -B_2 / V_1]

    # psi_dot dynamics
    A_c[IPSI_DOT, IPSI_DOT] = -D_33 / V_2
    B_c[IPSI_DOT, :] = [-B_3 / V_2, B_3 / V_2]

    # Euler discretization
    A_d = np.eye(N_STATES) + dt * A_c
    B_d = dt * B_c

    print("\nLinearized continuous-time model at theta=0:")
    print(f"  V_1 = {V_1:.6f}  (pitch/velocity coupling denominator)")
    print(f"  V_2 = {V_2:.6f}  (yaw denominator)")
    print(f"  B_1/V_1 = {B_1/V_1:.2f}   (input -> v_dot gain)")
    print(f"  B_2/V_1 = {B_2/V_1:.2f}  (input -> theta_ddot gain)")
    print(f"  B_3/V_2 = {B_3/V_2:.4f}   (input -> psi_ddot gain)")
    print(f"  C_21*g/V_1 = {C_21*g/V_1:.2f}  (gravity -> theta_ddot)")

    # Print dynamics equations
    for row in DYNAMIC_ROWS:
        name = STATE_NAMES[row]
        terms = []
        for j in range(N_STATES):
            if abs(A_c[row, j]) > 1e-6:
                terms.append(f"{A_c[row, j]:+.4f}*{STATE_NAMES[j]}")
        for j in range(N_INPUTS):
            if abs(B_c[row, j]) > 1e-6:
                terms.append(f"{B_c[row, j]:+.4f}*{INPUT_NAMES[j]}")
        print(f"  d({name})/dt = {' '.join(terms)}")

    return A_c, B_c, A_d, B_d


# ===========================================================================
# Step 2: Design a stabilizing LQR controller
# ===========================================================================

def design_lqr(A_d, B_d, dt):
    """Design discrete LQR on the controllable subsystem [v, theta, theta_dot, psi_dot].

    x, y, psi don't affect the dynamics and are not fed back.

    Returns:
        K: (2, 7) full state-feedback gain for u_actual = u_ext - K @ x
        info: dict with LQR details
    """
    # Controllable subsystem: [v, theta, theta_dot, psi_dot]
    ctrl_idx = [IV, ITHETA, ITHETA_DOT, IPSI_DOT]
    ctrl_names = [STATE_NAMES[i] for i in ctrl_idx]

    A_red = A_d[np.ix_(ctrl_idx, ctrl_idx)]
    B_red = B_d[np.ix_(ctrl_idx, range(N_INPUTS))]

    # LQR cost weights
    # theta is penalized most (unstable mode); R is large to keep gains moderate
    # (the high B_2/V_1 ≈ 233 means even small K_theta gives large loop gain)
    Q = np.diag([2.0, 100.0, 2.0, 2.0])  # [v, theta, theta_dot, psi_dot]
    R = np.diag([50.0, 50.0])             # [u_l, u_r]

    # Solve discrete algebraic Riccati equation
    P = solve_discrete_are(A_red, B_red, Q, R)
    K_red = np.linalg.solve(R + B_red.T @ P @ B_red, B_red.T @ P @ A_red)

    # Embed into full 7-state gain
    K = np.zeros((N_INPUTS, N_STATES))
    for j, idx in enumerate(ctrl_idx):
        K[:, idx] = K_red[:, j]

    # Verify closed-loop stability
    A_cl_full = A_d - B_d @ K
    eigs = np.linalg.eigvals(A_cl_full)
    max_eig = np.max(np.abs(eigs))

    print("\nLQR Controller Design (discrete):")
    print(f"  Q = diag({', '.join(f'{q:.0f}' for q in np.diag(Q))})  [{', '.join(ctrl_names)}]")
    print(f"  R = diag({', '.join(f'{r:.0f}' for r in np.diag(R))})  [{', '.join(INPUT_NAMES)}]")
    print(f"\n  Feedback gains per wheel:")
    for j, (idx, name) in enumerate(zip(ctrl_idx, ctrl_names)):
        print(f"    K_{name:>9s} = {K[0, idx]:+.6f}  (left),  {K[1, idx]:+.6f}  (right)")
    print(f"\n  Closed-loop eigenvalues: {', '.join(f'{e.real:+.4f}{e.imag:+.4f}j' for e in sorted(eigs, key=lambda x: -abs(x)))}")
    print(f"  Max |eigenvalue| = {max_eig:.6f}  ({'STABLE' if max_eig < 1.0 else 'UNSTABLE'})")

    if max_eig >= 1.0:
        print("\n  Increasing R to reduce gains...")
        for R_scale in [200, 500, 1000]:
            R_new = np.diag([float(R_scale)] * 2)
            P = solve_discrete_are(A_red, B_red, Q, R_new)
            K_red = np.linalg.solve(R_new + B_red.T @ P @ B_red, B_red.T @ P @ A_red)
            K = np.zeros((N_INPUTS, N_STATES))
            for j, idx in enumerate(ctrl_idx):
                K[:, idx] = K_red[:, j]
            eigs = np.linalg.eigvals(A_d - B_d @ K)
            max_eig = np.max(np.abs(eigs))
            if max_eig < 1.0:
                print(f"  R = {R_scale}: K_theta = {K[0, ITHETA]:.6f}, max|eig| = {max_eig:.6f} (stable)")
                R = R_new
                break
        else:
            raise RuntimeError("Could not find stabilizing LQR gains")

    return K, {'Q': Q, 'R': R, 'eigs': eigs, 'ctrl_idx': ctrl_idx}


# ===========================================================================
# Plotting functions
# ===========================================================================

def fig1_training_overview(train_data):
    """Plot a sample of training trajectories."""
    fig, axes = plt.subplots(3, 2, figsize=(12, 8), sharex='col')
    fig.suptitle('Training Data Overview (3 sample trajectories)', fontsize=13, fontweight='bold')

    colors = ['#2196F3', '#FF5722', '#4CAF50']
    for i, traj in enumerate(train_data[:3]):
        t = np.arange(traj.T) * traj.dt
        c = colors[i]
        lbl = f'Traj {i + 1}'

        axes[0, 0].plot(t, traj.states[:, ITHETA], color=c, alpha=0.8, label=lbl)
        axes[0, 1].plot(t, traj.states[:, IV], color=c, alpha=0.8)
        axes[1, 0].plot(t, traj.states[:, ITHETA_DOT], color=c, alpha=0.8)
        axes[1, 1].plot(t, traj.states[:, IPSI_DOT], color=c, alpha=0.8)
        axes[2, 0].plot(t, traj.inputs[:, 0], color=c, alpha=0.6, linewidth=0.7)
        axes[2, 1].plot(traj.states[:, IX], traj.states[:, IY], color=c, alpha=0.8)

    axes[0, 0].set_ylabel(r'$\theta$ [rad]')
    axes[0, 1].set_ylabel('v [m/s]')
    axes[1, 0].set_ylabel(r'$\dot{\theta}$ [rad/s]')
    axes[1, 1].set_ylabel(r'$\dot{\psi}$ [rad/s]')
    axes[2, 0].set_ylabel(r'$u_\mathrm{ext,L}$ [Nm]')
    axes[2, 0].set_xlabel('Time [s]')
    axes[2, 1].set_xlabel('x [m]')
    axes[2, 1].set_ylabel('y [m]')
    axes[2, 1].set_aspect('equal')

    axes[0, 0].legend(fontsize=8, loc='upper right')
    fig.tight_layout()
    return fig


def fig2_rollout_comparison(test_data, lin_result, nl_result, K):
    """Multi-step rollout: Actual vs Linear vs Hybrid vs Nonlinear."""
    traj = test_data[0]
    n_steps = min(500, traj.T - 1)
    x0 = traj.states[0]
    u_seg = traj.inputs[:n_steps]
    actual = traj.states[:n_steps + 1]

    # Simulate all three models
    pred_lin = simulate_linear(lin_result, x0, u_seg)
    pred_hyb = simulate_hybrid(lin_result, x0, u_seg)
    pred_nl = simulate_nonlinear(nl_result.params, x0, u_seg, K, DT)

    # Clip nonlinear prediction at first NaN
    valid_nl = n_steps + 1
    for k in range(n_steps + 1):
        if not np.all(np.isfinite(pred_nl[k])):
            valid_nl = k
            break

    t = np.arange(n_steps + 1) * DT

    fig, axes = plt.subplots(4, 2, figsize=(14, 10), sharex='col')
    fig.suptitle(
        f'Model Comparison \u2014 {n_steps}-step ({n_steps * DT:.1f}s) Rollout on Test Trajectory',
        fontsize=13, fontweight='bold',
    )

    specs = [
        (0, 0, ITHETA,     r'$\theta$ [rad]'),
        (0, 1, IV,          'v [m/s]'),
        (1, 0, ITHETA_DOT, r'$\dot{\theta}$ [rad/s]'),
        (1, 1, IPSI_DOT,   r'$\dot{\psi}$ [rad/s]'),
        (2, 0, IX,          'x [m]'),
        (2, 1, IY,          'y [m]'),
        (3, 0, IPSI,        r'$\psi$ [rad]'),
    ]

    for r, c, idx, label in specs:
        ax = axes[r, c]
        ax.plot(t, actual[:, idx], 'k-', linewidth=1.5, label='Actual (NL truth)')
        ax.plot(t, pred_lin[:, idx], color='#2196F3', linestyle='--',
                linewidth=1.0, alpha=0.85, label='Linear')
        ax.plot(t, pred_hyb[:, idx], color='#FF9800', linestyle='--',
                linewidth=1.0, alpha=0.85, label='Hybrid (lin dyn + NL kin)')
        ax.plot(t[:valid_nl], pred_nl[:valid_nl, idx], color='#F44336', linestyle='-.',
                linewidth=1.0, alpha=0.85, label='Nonlinear (identified)')
        ax.set_ylabel(label)
        if r == 0 and c == 0:
            ax.legend(fontsize=7, loc='best')

    # XY path in bottom-right
    ax = axes[3, 1]
    ax.plot(actual[:, IX], actual[:, IY], 'k-', linewidth=1.5, label='Actual')
    ax.plot(pred_lin[:, IX], pred_lin[:, IY], color='#2196F3', linestyle='--',
            linewidth=1.0, alpha=0.85, label='Linear')
    ax.plot(pred_hyb[:, IX], pred_hyb[:, IY], color='#FF9800', linestyle='--',
            linewidth=1.0, alpha=0.85, label='Hybrid')
    ax.plot(pred_nl[:valid_nl, IX], pred_nl[:valid_nl, IY], color='#F44336',
            linestyle='-.', linewidth=1.0, alpha=0.85, label='Nonlinear')
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    ax.set_aspect('equal')
    ax.legend(fontsize=7)

    for c in range(2):
        axes[-1, c].set_xlabel('Time [s]')

    fig.tight_layout()

    # Print RMSE table
    vl = min(valid_nl, n_steps + 1)
    print(f"\n  {n_steps}-step rollout RMSE (over {vl} valid steps):")
    print(f"  {'State':>12s}  {'Linear':>12s}  {'Hybrid':>12s}  {'Nonlinear':>12s}")
    for i, name in enumerate(STATE_NAMES):
        rmse_lin = np.sqrt(np.mean((actual[:vl, i] - pred_lin[:vl, i])**2))
        rmse_hyb = np.sqrt(np.mean((actual[:vl, i] - pred_hyb[:vl, i])**2))
        rmse_nl = np.sqrt(np.mean((actual[:vl, i] - pred_nl[:vl, i])**2))
        print(f"  {name:>12s}  {rmse_lin:12.2e}  {rmse_hyb:12.2e}  {rmse_nl:12.2e}")

    return fig


def fig3_parameter_comparison(nl_result, true_params):
    """Bar chart comparing true vs estimated parameters."""
    free = nl_result.free_params
    if not free:
        return None

    true_vals = np.array([true_params[n] for n in free])
    est_vals = np.array([nl_result.params[n] for n in free])

    x = np.arange(len(free))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle('Nonlinear Identification \u2014 Parameter Recovery', fontsize=13, fontweight='bold')

    # Absolute values
    ax1.bar(x - width / 2, true_vals, width, label='True', color='#2196F3', alpha=0.8, edgecolor='white')
    ax1.bar(x + width / 2, est_vals, width, label='Estimated', color='#FF5722', alpha=0.8, edgecolor='white')
    ax1.set_xticks(x)
    ax1.set_xticklabels(free, fontsize=9)
    ax1.set_ylabel('Value')
    ax1.legend(fontsize=9)
    ax1.set_title('Absolute Parameter Values', fontsize=11)

    # Relative error
    rel_err = np.array([
        abs(e - t) / abs(t) * 100 if abs(t) > 1e-12 else 0
        for t, e in zip(true_vals, est_vals)
    ])
    bar_colors = ['#4CAF50' if r < 5 else '#FF9800' if r < 20 else '#F44336' for r in rel_err]
    bars = ax2.bar(x, rel_err, 0.6, color=bar_colors, alpha=0.85, edgecolor='white')
    ax2.set_xticks(x)
    ax2.set_xticklabels(free, fontsize=9)
    ax2.set_ylabel('Relative Error [%]')
    ax2.set_title('Estimation Error', fontsize=11)
    ax2.axhline(y=5, color='#9E9E9E', linestyle='--', alpha=0.6, label='5% threshold')
    ax2.legend(fontsize=8)

    # Add error labels on bars
    for bar, err in zip(bars, rel_err):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                 f'{err:.1f}%', ha='center', va='bottom', fontsize=8)

    fig.tight_layout()
    return fig


def fig4_one_step_derivatives(test_data, lin_result, nl_result, K):
    """Scatter plots: observed vs predicted one-step derivatives."""
    dt = DT

    # Stack all test data
    s_k_list, s_kp1_list, u_k_list = [], [], []
    for traj in test_data:
        T = min(traj.T, traj.inputs.shape[0])
        s_k_list.append(traj.states[:T - 1])
        s_kp1_list.append(traj.states[1:T])
        u_k_list.append(traj.inputs[:T - 1])

    s_k = np.vstack(s_k_list)
    s_kp1 = np.vstack(s_kp1_list)
    u_ext = np.vstack(u_k_list)

    # Filter by theta
    mask = np.abs(s_k[:, ITHETA]) <= 0.3
    s_k, s_kp1, u_ext = s_k[mask], s_kp1[mask], u_ext[mask]

    # Observed derivatives
    s_dot_obs = (s_kp1 - s_k) / dt

    # Linear model: predicted next state via closed-loop
    A_cl = lin_result.A_d_cl
    s_kp1_lin = (A_cl @ s_k.T).T + (lin_result.B_d @ u_ext.T).T + lin_result.bias
    s_dot_lin = (s_kp1_lin - s_k) / dt

    # Nonlinear model: direct derivative evaluation
    u_actual = u_ext - (K @ s_k.T).T
    s_dot_nl = bilbo_dynamics_3d(s_k, u_actual, nl_result.params)

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle('One-Step Derivative Prediction on Test Data', fontsize=13, fontweight='bold')

    deriv_specs = [
        (IV,         r'$\dot{v}$ [m/s$^2$]'),
        (ITHETA_DOT, r'$\ddot{\theta}$ [rad/s$^2$]'),
        (IPSI_DOT,   r'$\ddot{\psi}$ [rad/s$^2$]'),
    ]

    for col, (idx, label) in enumerate(deriv_specs):
        obs = s_dot_obs[:, idx]

        # Linear (top row)
        ax = axes[0, col]
        pred = s_dot_lin[:, idx]
        ax.scatter(obs, pred, s=1.5, alpha=0.25, color='#2196F3', rasterized=True)
        lims = [min(obs.min(), pred.min()), max(obs.max(), pred.max())]
        margin = (lims[1] - lims[0]) * 0.05
        lims = [lims[0] - margin, lims[1] + margin]
        ax.plot(lims, lims, 'k--', linewidth=0.8, alpha=0.5)
        ss_res = np.sum((obs - pred)**2)
        ss_tot = np.sum((obs - obs.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0
        ax.set_title(f'Linear \u2014 {label}\nR\u00b2 = {r2:.6f}', fontsize=10)
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        if col == 0:
            ax.set_ylabel('Predicted')

        # Nonlinear (bottom row)
        ax = axes[1, col]
        pred_nl = s_dot_nl[:, idx]
        ax.scatter(obs, pred_nl, s=1.5, alpha=0.25, color='#FF5722', rasterized=True)
        lims_nl = [min(obs.min(), pred_nl.min()), max(obs.max(), pred_nl.max())]
        margin = (lims_nl[1] - lims_nl[0]) * 0.05
        lims_nl = [lims_nl[0] - margin, lims_nl[1] + margin]
        ax.plot(lims_nl, lims_nl, 'k--', linewidth=0.8, alpha=0.5)
        ss_res_nl = np.sum((obs - pred_nl)**2)
        r2_nl = 1 - ss_res_nl / ss_tot if ss_tot > 1e-12 else 0
        ax.set_title(f'Nonlinear \u2014 {label}\nR\u00b2 = {r2_nl:.6f}', fontsize=10)
        ax.set_xlabel('Observed')
        ax.set_xlim(lims_nl)
        ax.set_ylim(lims_nl)
        if col == 0:
            ax.set_ylabel('Predicted')

    fig.tight_layout()
    return fig


# ===========================================================================
# Main pipeline
# ===========================================================================

def main():
    print("=" * 72)
    print("  BILBO System Identification \u2014 Complete Example")
    print("=" * 72)

    # ── Step 1: Linearize ────────────────────────────────────────────────
    print("\n[Step 1] Linearizing nonlinear dynamics at theta=0...")
    A_c, B_c, A_d_true, B_d_true = linearize_bilbo(PARAMS, DT)

    # ── Step 2: Design LQR controller ────────────────────────────────────
    print("\n[Step 2] Designing discrete LQR controller...")
    K, lqr_info = design_lqr(A_d_true, B_d_true, DT)

    # ── Step 3: Generate training data ───────────────────────────────────
    print("\n[Step 3] Generating training data from nonlinear model...")
    train_data = generate_synthetic_data(
        PARAMS, K, dt=DT,
        n_trajectories=30, T=800,
        noise_std=0.001, input_std=0.08,
        seed=42, max_theta=0.8,
    )
    n_train = sum(t.T for t in train_data)
    print(f"  {len(train_data)} trajectories, {n_train} total samples")

    # ── Step 4a: Linear identification ───────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 4a] Linear System Identification")
    print("=" * 72)
    lin_config = IdentificationConfig(alpha=1e-3, theta_max=0.3)
    lin_result = identify_system(train_data, lin_config, K=K)
    print_model(lin_result)

    # Compare identified vs true linearized matrices
    print("\nTrue linearization vs identified A_d (dynamic rows):")
    print(f"  {'Row':>12s}  {'Max |A err|':>14s}  {'Max |B err|':>14s}")
    for row in DYNAMIC_ROWS:
        a_err = np.max(np.abs(lin_result.A_d[row] - A_d_true[row]))
        b_err = np.max(np.abs(lin_result.B_d[row] - B_d_true[row]))
        print(f"  {STATE_NAMES[row]:>12s}  {a_err:14.2e}  {b_err:14.2e}")
    print("  (Errors reflect linearization mismatch: data comes from the")
    print("   nonlinear model, but we identify a linear model)")

    # ── Step 4b: Nonlinear identification ────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 4b] Nonlinear Parameter Estimation")
    print("=" * 72)
    specs = get_default_parameter_specs()

    # Perturb initial guesses away from truth to test convergence
    specs['l'].value = 0.04          # true: 0.026
    specs['I_y'].value = 0.01        # true: 0.005
    specs['I_x'].value = 0.015       # true: 0.02
    specs['I_z'].value = 0.025       # true: 0.03
    specs['I_w'].value = 3e-4        # true: 2e-4
    specs['c_alpha'].value = 5e-4    # true: 4.63e-4
    specs['tau_theta'].value = 0.2   # true: 0.4
    specs['tau_x'].value = 0.6       # true: 0.4

    print("\nInitial guesses (perturbed from truth):")
    for name in PARAM_NAMES:
        if not specs[name].fixed:
            err_pct = abs(specs[name].value - PARAMS[name]) / PARAMS[name] * 100
            print(f"  {name:>12s}: {specs[name].value:.6g}  (true: {PARAMS[name]:.6g}, {err_pct:.0f}% off)")

    nl_config = NonlinearConfig(theta_max=0.5, verbose=1)
    nl_result = identify_nonlinear(train_data, specs, K, nl_config)
    print_result(nl_result, true_params=PARAMS)

    # ── Step 5: Generate test data ───────────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 5] Validation on New Test Trajectories")
    print("=" * 72)
    test_data = generate_synthetic_data(
        PARAMS, K, dt=DT,
        n_trajectories=5, T=1000,
        noise_std=0.0005, input_std=0.06,
        seed=999, max_theta=0.8,
    )
    n_test = sum(t.T for t in test_data)
    print(f"  {len(test_data)} test trajectories, {n_test} total samples")
    print("  (different seed, different initial conditions, lower noise)")

    # ── Step 6: Create plots ─────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 6] Creating Plots")
    print("=" * 72)

    plt.rcParams.update({
        'font.size': 10,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'figure.facecolor': 'white',
    })

    fig1 = fig1_training_overview(train_data)
    fig2 = fig2_rollout_comparison(test_data, lin_result, nl_result, K)
    fig3 = fig3_parameter_comparison(nl_result, PARAMS)
    fig4 = fig4_one_step_derivatives(test_data, lin_result, nl_result, K)

    print("\n" + "=" * 72)
    print("  Done! Close plot windows to exit.")
    print("=" * 72)
    plt.show()


if __name__ == '__main__':
    main()
