import numpy as np
from matplotlib import pyplot as plt

from core.utils.control.lib_control.il.ilc import BILBO_STANDARD_REFERENCE_TRAJECTORY, getTransitionMatrixFromSystem, \
    getLearningMatricesOptimal
from core.utils.control.lib_control.il.iml import imlUpdateOptimal, getOptimalLearningMatrix, \
    getOptimalLearningMatrixFromMatrix
from core.utils.control.lib_control.lifted_systems import vec2liftedMatrix, liftedMatrix2Vec
from core.utils.data import generate_time_vector, generate_random_input
from simulation.src.objects.bilbo import BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL, \
    BILBO_Dynamics_2D_Linear, BILBO_2D_POLES, BILBO_MICHAEL_MODEL

def example_iitl():
    # Settings
    BILBO_CLASS = BILBO_Dynamics_2D

    MODEL_SOURCE = BILBO_MICHAEL_MODEL
    POLES_SOURCE = BILBO_2D_POLES

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = BILBO_2D_POLES

    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=0.01)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)

    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=0.01)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # First, compare their outputs to one and the same input
    t_vec = generate_time_vector(start=0, end=6, dt=0.01)
    N = len(t_vec)

    test_input = generate_random_input(t_vec, f_cutoff=2, sigma_I=1)

    states_bilbo_source_test = bilbo_source.simulate(input=test_input, reset=True, include_zero_step=False)
    states_bilbo_target_test = bilbo_target.simulate(input=test_input, reset=True, include_zero_step=False)
    theta_bilbo_source_test = np.asarray([state.theta for state in states_bilbo_source_test])
    theta_bilbo_target_test = np.asarray([state.theta for state in states_bilbo_target_test])

    plt.figure()
    plt.plot(theta_bilbo_source_test, label='Source')
    plt.plot(theta_bilbo_target_test, label='Target')
    plt.legend()
    plt.show()

    # Now lets do IITL

    # Generate a linear version of the target system for easy access to P
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=0.01)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=0.01)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)

    t_true = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # 1. Generate a set of input/output trajectories of the source system
    NL = 10

    frequency_min, frequency_max = 0.5, 8  # example values
    sigma_min, sigma_max = 0.5, 1.5  # example values

    learning_inputs = []
    learning_outputs = []
    for i in range(NL):
        f_cutoff = np.random.uniform(frequency_min, frequency_max)
        sigma_I = np.random.uniform(sigma_min, sigma_max)
        u = generate_random_input(t_vec, f_cutoff=f_cutoff, sigma_I=sigma_I)
        states = bilbo_source.simulate(input=u, reset=True, include_zero_step=False)
        theta = np.asarray([state.theta for state in states])
        learning_inputs.append(u)
        learning_outputs.append(theta)

    # 2. Do IITL on the target system
    J = 30
    t0 = np.zeros((N,))
    verification_error_norms = []
    learning_error_norms = []
    transfer_vector_error_norms = []

    tj = t0

    for j in range(J):
        uj_source = learning_inputs[j % NL]
        yj_source = learning_outputs[j % NL]

        # 1. Transfer the input to the target system
        uj_target = vec2liftedMatrix(tj) @ uj_source

        # 2. Apply the transferred input to the target system
        states_target = bilbo_target.simulate(input=uj_target, reset=True, include_zero_step=False)
        yj_target = np.asarray([state.theta for state in states_target])

        # 3. Calculate the learning matrix
        matrix_of_interest = P_target @ vec2liftedMatrix(uj_source)
        Lj = getOptimalLearningMatrixFromMatrix(matrix_of_interest)

        # 4. Calculate the learning error
        ej = yj_source - yj_target

        # 5. Calculate the verification error. For this, we transfer the verification trajectory and apply it
        u_verification_target = vec2liftedMatrix(tj) @ test_input
        states_verification_target = bilbo_target.simulate(input=u_verification_target, reset=True,
                                                           include_zero_step=False)
        theta_verification_target = np.asarray([state.theta for state in states_verification_target])
        e_verification_j = theta_verification_target - theta_bilbo_source_test

        verification_error_norms.append(np.linalg.norm(e_verification_j))
        learning_error_norms.append(np.linalg.norm(ej))

        transfer_vector_error_norms.append(np.linalg.norm(t_true - tj))
        # 4. Calculate the new transfer vector
        tj = tj + Lj @ ej

    plt.figure()
    plt.plot(transfer_vector_error_norms)
    plt.grid()
    plt.show()

    # # Plot the verification outputs
    fig = plt.figure()
    plt.plot(t_vec, theta_bilbo_source_test, label='Source')
    plt.plot(t_vec, theta_verification_target, label='Target')
    plt.legend()
    plt.show()

    # Try it with the linear perfect t
    u_target_perfect = vec2liftedMatrix(t_true) @ test_input
    states_verification_target_perfect = bilbo_target.simulate(input=u_target_perfect, reset=True,
                                                               include_zero_step=False)
    theta_verification_target_perfect = np.asarray([state.theta for state in states_verification_target_perfect])

    plt.figure()
    plt.plot(t_vec, theta_verification_target_perfect, label='Target perfect transfer')
    plt.plot(t_vec, theta_bilbo_source_test, label='Source')
    plt.legend()
    plt.show()


def example_iitl_A_features():
    """
    IITL with a mildly nonlinear transfer using feature blocks on the input:
      phi_1(u)=u, phi_2(u)=u**2, phi_3(u)=tanh(u)
    The transfer parameter is t_cat = [t1; t2; t3] (each length N).
    Update uses a stacked normal-equations step (ridge-regularized).
    """
    import numpy as np
    import matplotlib.pyplot as plt

    # --- Settings (same as your original) ---
    BILBO_CLASS = BILBO_Dynamics_2D
    MODEL_SOURCE = BILBO_MICHAEL_MODEL
    POLES_SOURCE = [0, -8, -2 + 1j, -2 - 1j]

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = BILBO_2D_POLES

    Ts = 0.01
    t_vec = generate_time_vector(start=0, end=6, dt=Ts)
    N = len(t_vec)

    # --- Systems ---
    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=Ts)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # For the verification trajectory
    test_input = generate_random_input(t_vec, f_cutoff=2, sigma_I=1.0)
    theta_src_test = np.asarray(
        [s.theta for s in bilbo_source.simulate(test_input, reset=True, include_zero_step=False)])
    theta_tgt_test_nom = np.asarray(
        [s.theta for s in bilbo_target.simulate(test_input, reset=True, include_zero_step=False)])

    # --- Linear references (to compare transfer-vector error when possible) ---
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=Ts)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)

    # "Linear-perfect" t (only used for reference plots)
    t_true_linear = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # --- Learning data from source ---
    NL = 10
    frequency_min, frequency_max = 0.5, 8.0
    sigma_min, sigma_max = 0.5, 1.5
    learning_inputs, learning_outputs = [], []
    rng = np.random.default_rng(0)

    for _ in range(NL):
        f_cutoff = rng.uniform(frequency_min, frequency_max)
        sigma_I = rng.uniform(sigma_min, sigma_max)
        u = generate_random_input(t_vec, f_cutoff=f_cutoff, sigma_I=sigma_I)
        theta = np.asarray([st.theta for st in bilbo_source.simulate(u, reset=True, include_zero_step=False)])
        learning_inputs.append(u)
        learning_outputs.append(theta)

    # --- Feature blocks and helpers ---
    def feature_list(u):
        # Keep features roughly normalized; add small eps to avoid huge squares if needed
        return [u, u ** 2, np.tanh(u)]

    n_feat = 3  # number of feature blocks

    def build_block_toeplitz_stack(u):
        # Returns list of (N,N) block-Toeplitz matrices, one per feature
        phis = feature_list(u)
        return [vec2liftedMatrix(phi) for phi in phis]

    def apply_transfer_to_input(t_cat, u):
        # t_cat is concatenated [t1; t2; ...; t_p]; each t_i length N
        blocks = build_block_toeplitz_stack(u)
        out = np.zeros_like(u)
        for i in range(n_feat):
            t_i = t_cat[i * N:(i + 1) * N]
            out += blocks[i] @ t_i
        return out

    # --- Optimization weights ---
    # Q acts on output error; since we only have outputs as time-series, use identity
    Q = np.eye(N)
    # Ridge on parameters: heavier on nonlinear blocks to avoid overfitting initially
    lam_lin = 1e-2
    lam_nl = 1.0
    S = np.diag(np.concatenate([
        lam_lin * np.ones(N),
        lam_nl * np.ones(N),
        lam_nl * np.ones(N),
    ]))

    # --- Iterations ---
    J = 30
    t_cat = np.zeros(n_feat * N)  # initial transfer parameters
    verification_error_norms = []
    learning_error_norms = []
    transfer_vector_error_norms_vs_linear = []

    for j in range(J):
        # Select a training pair
        u_src = learning_inputs[j % NL]
        y_src = learning_outputs[j % NL]

        # Build regression matrix for this input (stack features horizontally)
        blocks = build_block_toeplitz_stack(u_src)  # list of (N,N)
        # Map from parameters to the applied u_target is sum_i M_i(u_src) t_i
        # The output map is y_beta = F_beta(u_beta). We don't have an explicit F_beta linear map,
        # so we use *measured* y_beta after applying the transferred input.
        u_tgt = apply_transfer_to_input(t_cat, u_src)
        y_tgt = np.asarray([st.theta for st in bilbo_target.simulate(u_tgt, reset=True, include_zero_step=False)])
        e = y_src - y_tgt

        # Verification trajectory error with current t_cat
        u_ver = apply_transfer_to_input(t_cat, test_input)
        y_ver = np.asarray([st.theta for st in bilbo_target.simulate(u_ver, reset=True, include_zero_step=False)])
        e_ver = y_ver - theta_src_test

        verification_error_norms.append(np.linalg.norm(e_ver))
        learning_error_norms.append(np.linalg.norm(e))

        # Build a "learning matrix" via Gauss–Newton: linearize outputs w.r.t. params through input map
        # Approximate local sensitivity: dy/dt ≈ P_target @ [M_1 ... M_p]
        # Use linear target proxy to form the regressor; this stabilizes updates.
        Mi_list = [vec2liftedMatrix(u_src), vec2liftedMatrix(u_src ** 2), vec2liftedMatrix(np.tanh(u_src))]
        U = np.hstack([P_target @ Mi for Mi in Mi_list])  # shape (N, p*N)

        # Normal equations: Δt = (U^T Q U + S)^-1 U^T Q e
        A = U.T @ (Q @ U) + S
        g = U.T @ (Q @ e)
        delta_t = np.linalg.solve(A, g)

        # Optional small step size for safety
        mu = 0.8
        t_cat = t_cat + mu * delta_t

        # Track distance to the "linear-perfect" t (only for the first block, i.e., linear part)
        t_lin = t_cat[:N]
        transfer_vector_error_norms_vs_linear.append(np.linalg.norm(t_true_linear - t_lin))

    # --- Plots ---
    plt.figure();
    plt.plot(transfer_vector_error_norms_vs_linear);
    plt.title("‖t_linear - t_true_linear‖");
    plt.grid(True)

    # Final verification plot
    u_ver = apply_transfer_to_input(t_cat, test_input)
    y_ver = np.asarray([st.theta for st in bilbo_target.simulate(u_ver, reset=True, include_zero_step=False)])
    plt.figure()
    plt.plot(t_vec, theta_src_test, label='Source')
    plt.plot(t_vec, y_ver, label='Target (features transfer)')
    plt.legend();
    plt.title("Verification trajectory");
    plt.show()


def example_iitl_B_batch_LM():
    """
    IITL with a *linear* transfer but using:
      - batched Gauss–Newton normal equations (multi-trajectory stack)
      - Levenberg–Marquardt damping
      - simple backtracking line search on the parameter step
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from collections import deque

    # --- Settings ---
    BILBO_CLASS = BILBO_Dynamics_2D

    MODEL_SOURCE = BILBO_MICHAEL_MODEL
    POLES_SOURCE = [0, -8, -2 + 1j, -2 - 1j]

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = BILBO_2D_POLES

    Ts = 0.01
    t_vec = generate_time_vector(start=0, end=6, dt=Ts)
    N = len(t_vec)

    # --- Systems ---
    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=Ts)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # For verification
    test_input = generate_random_input(t_vec, f_cutoff=2, sigma_I=1.0)
    theta_src_test = np.asarray(
        [s.theta for s in bilbo_source.simulate(test_input, reset=True, include_zero_step=False)])

    # Linear proxies for learning matrix construction
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=Ts)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)
    t_true_linear = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # --- Learning data from source ---
    NL = 16
    frequency_min, frequency_max = 0.5, 8.0
    sigma_min, sigma_max = 0.5, 1.5
    learning_inputs, learning_outputs = [], []
    rng = np.random.default_rng(1)

    for _ in range(NL):
        f_cutoff = rng.uniform(frequency_min, frequency_max)
        sigma_I = rng.uniform(sigma_min, sigma_max)
        u = generate_random_input(t_vec, f_cutoff=f_cutoff, sigma_I=sigma_I)
        theta = np.asarray([st.theta for st in bilbo_source.simulate(u, reset=True, include_zero_step=False)])
        learning_inputs.append(u)
        learning_outputs.append(theta)

    # --- Buffers for batching ---
    K = 6  # batch size (recent trajectories)
    buf_u_src = deque(maxlen=K)
    buf_y_src = deque(maxlen=K)
    buf_y_tgt = deque(maxlen=K)

    # --- Optimization hyperparameters ---
    Q = np.eye(N)
    lam0 = 1e-2  # base LM damping factor (scaled by curvature)
    mu_init = 1.0
    backtrack_factor = 0.5
    min_mu = 1e-3

    # --- Iterations ---
    J = 40
    t = np.zeros(N)
    verification_error_norms = []
    learning_error_norms = []
    transfer_vector_error_norms = []

    for j in range(J):
        # Pick a source trajectory
        u_src = learning_inputs[j % NL]
        y_src = learning_outputs[j % NL]

        # Current transferred input (linear Toeplitz)
        u_tgt = vec2liftedMatrix(t) @ u_src
        y_tgt = np.asarray([st.theta for st in bilbo_target.simulate(u_tgt, reset=True, include_zero_step=False)])

        # Update buffers
        buf_u_src.append(u_src)
        buf_y_src.append(y_src)
        buf_y_tgt.append(y_tgt)

        # Build stacked regression U_stack and error e_stack
        U_blocks = []
        e_list = []
        for u_s, y_s, y_t in zip(buf_u_src, buf_y_src, buf_y_tgt):
            U = P_target @ vec2liftedMatrix(u_s)  # (N,N)
            U_blocks.append(U)
            e_list.append(y_s - y_t)
        U_stack = np.vstack(U_blocks)  # (K*N, N)
        e_stack = np.concatenate(e_list)  # (K*N, )

        # LM damping scaled by curvature
        H = U_stack.T @ U_stack
        lam = lam0 * np.linalg.norm(H, 2)
        A = H + lam * np.eye(N)
        g = U_stack.T @ e_stack

        # Candidate step
        delta_t_nom = np.linalg.solve(A, g)

        # Line search on mu using verification error
        def verif_err_norm(t_candidate):
            u_ver = vec2liftedMatrix(t_candidate) @ test_input
            y_ver = np.asarray([st.theta for st in bilbo_target.simulate(u_ver, reset=True, include_zero_step=False)])
            return np.linalg.norm(y_ver - theta_src_test), y_ver

        mu = mu_init
        base_err, y_ver_base = verif_err_norm(t)
        while True:
            t_candidate = t + mu * delta_t_nom
            err_cand, y_ver_cand = verif_err_norm(t_candidate)
            if err_cand <= base_err or mu <= min_mu:
                # accept (or give up if step is tiny)
                t = t_candidate
                y_ver_final = y_ver_cand
                break
            mu *= backtrack_factor

        verification_error_norms.append(np.linalg.norm(y_ver_final - theta_src_test))
        learning_error_norms.append(np.linalg.norm(e_stack))
        transfer_vector_error_norms.append(np.linalg.norm(t_true_linear - t))

    # --- Plots ---
    plt.figure();
    plt.plot(transfer_vector_error_norms);
    plt.title("‖t - t_true_linear‖");
    plt.grid(True)

    # Final verification plot
    u_ver = vec2liftedMatrix(t) @ test_input
    y_ver = np.asarray([st.theta for st in bilbo_target.simulate(u_ver, reset=True, include_zero_step=False)])
    plt.figure()
    plt.plot(t_vec, theta_src_test, label='Source')
    plt.plot(t_vec, y_ver, label='Target (batch LM transfer)')
    plt.legend();
    plt.title("Verification trajectory");
    plt.show()


def example_iitl_compare_linear_vs_features():
    """
    Compare IITL with your original *linear* transfer vs a *nonlinear feature* transfer
    on identical training and verification trajectories.

    Assumes the following exist in your codebase:
      - BILBO_Dynamics_2D, BILBO_Dynamics_2D_Linear
      - BILBO_MICHAEL_MODEL, DEFAULT_BILBO_MODEL, BILBO_2D_POLES
      - generate_time_vector, generate_random_input
      - vec2liftedMatrix, liftedMatrix2Vec, getTransitionMatrixFromSystem
      - getOptimalLearningMatrixFromMatrix (your original function)

    Plots:
      1) Verification error norms over iterations (linear vs features)
      2) Final verification trajectory overlay (source vs both transfers)
      3) (Optional) ‖t_linear - t_true_linear‖ over iterations
    """
    import numpy as np
    import matplotlib.pyplot as plt

    # ---------- Settings ----------
    Ts = 0.01
    t_vec = generate_time_vector(start=0, end=6, dt=Ts)
    N = len(t_vec)

    # Systems
    BILBO_CLASS = BILBO_Dynamics_2D
    MODEL_SOURCE = DEFAULT_BILBO_MODEL
    POLES_SOURCE = BILBO_2D_POLES

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = [0, -10, -2 + 1j, -2 - 1j]

    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)

    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=Ts)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # Linear proxies (only used for U construction and optional t_true reference)
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=Ts)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)

    # "Oracle" linear transfer (only for reference metric)
    t_true_linear = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # ---------- Data: shared verification and training sets ----------
    verification_input = generate_random_input(t_vec, f_cutoff=2.0, sigma_I=1.0)
    theta_src_ver = np.asarray(
        [s.theta for s in bilbo_source.simulate(verification_input, reset=True, include_zero_step=False)])

    NL = 12  # number of training trajectories
    rng = np.random.default_rng(0)
    freq_min, freq_max = 0.5, 8.0
    sig_min, sig_max = 0.5, 1.5

    learn_inputs, learn_outputs = [], []
    for _ in range(NL):
        u = generate_random_input(
            t_vec,
            f_cutoff=float(rng.uniform(freq_min, freq_max)),
            sigma_I=float(rng.uniform(sig_min, sig_max)),
        )
        theta = np.asarray([st.theta for st in bilbo_source.simulate(u, reset=True, include_zero_step=False)])
        learn_inputs.append(u)
        learn_outputs.append(theta)

    # ---------- Helpers for features approach ----------
    def feature_list(u):
        return [u, u ** 2, np.tanh(u)]  # simple, stable features

    def build_U_linear(u_src):
        # Your original regressor for the linear method
        return P_target @ vec2liftedMatrix(u_src)  # (N, N)

    def build_U_features(u_src):
        # Horizontal stack of block-Toeplitz for the features
        phis = feature_list(u_src)
        M_blocks = [vec2liftedMatrix(phi) for phi in phis]  # each (N,N)
        return np.hstack([P_target @ Mi for Mi in M_blocks])  # (N, 3N)

    def apply_transfer_linear(t_lin, u_src):
        return vec2liftedMatrix(t_lin) @ u_src

    def apply_transfer_features(t_cat, u_src):
        # t_cat = [t1; t2; t3], each length N
        phis = feature_list(u_src)
        out = np.zeros_like(u_src)
        for i, phi in enumerate(phis):
            t_i = t_cat[i * N:(i + 1) * N]
            out += vec2liftedMatrix(phi) @ t_i
        return out

    # ---------- Initialization ----------
    J = 30  # iterations
    t_lin = np.zeros(N)
    t_cat = np.zeros(3 * N)  # features parameter vector

    # Regularization for features (stronger on nonlinear parts)
    lam_lin = 1e-2
    lam_nl = 1.0
    S_feat = np.diag(np.concatenate([
        lam_lin * np.ones(N),
        lam_nl * np.ones(N),
        lam_nl * np.ones(N)
    ]))
    Q = np.eye(N)

    # ---------- Storage ----------
    ver_err_lin_hist = []
    ver_err_feat_hist = []
    lin_dist_to_true_hist = []

    # ---------- Iterations (shared inputs per step) ----------
    for j in range(J):
        u_src = learn_inputs[j % NL]
        y_src = learn_outputs[j % NL]

        # ---- Linear path (your method) ----
        u_tgt_lin = apply_transfer_linear(t_lin, u_src)
        y_tgt_lin = np.asarray(
            [st.theta for st in bilbo_target.simulate(u_tgt_lin, reset=True, include_zero_step=False)])
        e_lin = y_src - y_tgt_lin
        # Your learning matrix
        U_lin = build_U_linear(u_src)  # (N, N)
        L_lin = getOptimalLearningMatrixFromMatrix(U_lin)  # (N, N) via your function
        t_lin = t_lin + L_lin @ e_lin

        # ---- Features path (Approach A) ----
        u_tgt_feat = apply_transfer_features(t_cat, u_src)
        y_tgt_feat = np.asarray(
            [st.theta for st in bilbo_target.simulate(u_tgt_feat, reset=True, include_zero_step=False)])
        e_feat = y_src - y_tgt_feat

        # Gauss–Newton step with ridge: Δt = (U^T Q U + S)^-1 U^T Q e
        U_feat = build_U_features(u_src)  # (N, 3N)
        A = U_feat.T @ (Q @ U_feat) + S_feat
        g = U_feat.T @ (Q @ e_feat)
        delta_t = np.linalg.solve(A, g)
        # mild step-size for stability (optional)
        t_cat = t_cat + 0.8 * delta_t

        # ---- Verification (same trajectory for both) ----
        y_ver_lin = np.asarray(
            [st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin, verification_input),
                                                      reset=True, include_zero_step=False)])
        y_ver_feat = np.asarray(
            [st.theta for st in bilbo_target.simulate(apply_transfer_features(t_cat, verification_input),
                                                      reset=True, include_zero_step=False)])

        ver_err_lin = np.linalg.norm(y_ver_lin - theta_src_ver)
        ver_err_feat = np.linalg.norm(y_ver_feat - theta_src_ver)
        ver_err_lin_hist.append(ver_err_lin)
        ver_err_feat_hist.append(ver_err_feat)

        # Distance to "oracle" linear t (for reference only; not a stopping rule)
        lin_dist_to_true_hist.append(np.linalg.norm(t_true_linear - t_lin))

    # ---------- Plots ----------
    # 1) Verification error norms
    plt.figure()
    plt.plot(ver_err_lin_hist, label='Linear (your IITL)')
    plt.plot(ver_err_feat_hist, label='Nonlinear features (A)')
    plt.xlabel('Iteration');
    plt.ylabel('‖verification error‖')
    plt.title('Verification error over iterations')
    plt.grid(True);
    plt.legend()

    # 2) Final verification trajectory overlay
    y_ver_lin = np.asarray([st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin, verification_input),
                                                                     reset=True, include_zero_step=False)])
    y_ver_feat = np.asarray(
        [st.theta for st in bilbo_target.simulate(apply_transfer_features(t_cat, verification_input),
                                                  reset=True, include_zero_step=False)])
    plt.figure()
    plt.plot(t_vec, theta_src_ver, label='Source (verification)')
    plt.plot(t_vec, y_ver_lin, label='Target w/ Linear transfer')
    plt.plot(t_vec, y_ver_feat, label='Target w/ Features transfer')
    plt.xlabel('t');
    plt.title('Verification outputs');
    plt.legend();
    plt.grid(True)

    # 3) Optional: distance to t_true_linear for the linear method
    plt.figure()
    plt.plot(lin_dist_to_true_hist)
    plt.title('‖t_linear - t_true_linear‖ (reference)')
    plt.xlabel('Iteration');
    plt.grid(True)

    plt.show()


def example_iitl_compare_linear_vs_features_v2():
    """
    Compare IITL with your original *linear* transfer vs a *nonlinear feature* transfer
    on identical training and verification trajectories. This version AUTOMATICALLY
    adapts to the number of nonlinear features you define in `feature_list(u)`.

    Assumes the following exist in your codebase:
      - BILBO_Dynamics_2D, BILBO_Dynamics_2D_Linear
      - DEFAULT_BILBO_MODEL, BILBO_MICHAEL_MODEL (if you want), BILBO_2D_POLES
      - generate_time_vector, generate_random_input
      - vec2liftedMatrix, liftedMatrix2Vec, getTransitionMatrixFromSystem
      - getOptimalLearningMatrixFromMatrix
    """
    import numpy as np
    import matplotlib.pyplot as plt

    # ---------- Settings ----------
    Ts = 0.01
    t_vec = generate_time_vector(start=0, end=6, dt=Ts)
    N = len(t_vec)
    eps = 1e-8  # small numerical guard

    # Systems (adjust models/poles to your needs)
    BILBO_CLASS = BILBO_Dynamics_2D
    MODEL_SOURCE = DEFAULT_BILBO_MODEL
    POLES_SOURCE = BILBO_2D_POLES

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = [0, -10, -2 + 6j, -2 - 6j]  # your example

    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)

    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=Ts)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # Linear proxies (used to construct learning regressors and the linear reference t*)
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=Ts)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)

    # "Oracle" linear transfer (reference only)
    t_true_linear = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # ---------- Shared data ----------
    verification_input = generate_random_input(t_vec, f_cutoff=2.0, sigma_I=1.0)
    theta_src_ver = np.asarray(
        [s.theta for s in bilbo_source.simulate(verification_input, reset=True, include_zero_step=False)])

    NL = 12
    rng = np.random.default_rng(0)
    freq_min, freq_max = 0.5, 8.0
    sig_min, sig_max = 0.5, 1.5

    learn_inputs, learn_outputs = [], []
    for _ in range(NL):
        u = generate_random_input(
            t_vec,
            f_cutoff=float(rng.uniform(freq_min, freq_max)),
            sigma_I=float(rng.uniform(sig_min, sig_max)),
        )
        theta = np.asarray([st.theta for st in bilbo_source.simulate(u, reset=True, include_zero_step=False)])
        learn_inputs.append(u)
        learn_outputs.append(theta)

    # ---------- Feature definition (EDIT HERE FREELY) ----------
    def feature_list(u):
        # You can add/remove features; the rest of the code adapts automatically.
        return [
            u,
            u ** 2,
            # u ** 3,
            # u ** 4,
            np.tanh(u),
            np.sign(u) * np.sqrt(np.abs(u) + eps),  # sqrt with guard
            np.clip(u, -1, 1),
        ]

    # Number of features (p)
    p = len(feature_list(np.zeros(N)))

    # ---------- Helpers ----------
    def build_U_linear(u_src):
        return P_target @ vec2liftedMatrix(u_src)  # (N, N)

    def build_U_features(u_src):
        phis = feature_list(u_src)
        M_blocks = [vec2liftedMatrix(phi) for phi in phis]  # each (N,N)
        return np.hstack([P_target @ Mi for Mi in M_blocks])  # (N, p*N)

    def apply_transfer_linear(t_lin, u_src):
        return vec2liftedMatrix(t_lin) @ u_src

    def apply_transfer_features(t_cat, u_src):
        # t_cat = [t1; t2; ...; tp], each length N
        phis = feature_list(u_src)
        out = np.zeros_like(u_src)
        for i, phi in enumerate(phis):
            t_i = t_cat[i * N:(i + 1) * N]
            # Safety: if someone mis-specified sizes, assert quickly
            if t_i.shape[0] != N:
                raise ValueError(
                    f"t_cat size {t_cat.size} does not match p*N={p * N}. Check feature count vs t_cat init.")
            out += vec2liftedMatrix(phi) @ t_i
        return out

    # ---------- Initialization ----------
    J = 30
    t_lin = np.zeros(N)
    t_cat = np.zeros(p * N)  # <-- adapt to the number of features

    # Regularization for features (heavier on nonlinear blocks)
    lam_lin = 1e-2
    lam_nl = 1.0
    # Per-feature ridge vector: first (linear) gets lam_lin, others lam_nl
    lam_vec = np.concatenate([[lam_lin] + [lam_nl] * (p - 1)])
    # Expand to parameter dimension p*N
    S_feat = np.diag(np.repeat(lam_vec, N))

    Q = np.eye(N)

    # ---------- Logs ----------
    ver_err_lin_hist = []
    ver_err_feat_hist = []
    lin_dist_to_true_hist = []
    nonlin_dist_to_true_hist = []

    # ---------- Iterations ----------
    for j in range(J):
        u_src = learn_inputs[j % NL]
        y_src = learn_outputs[j % NL]

        # ---- Linear path (your method) ----
        u_tgt_lin = apply_transfer_linear(t_lin, u_src)
        y_tgt_lin = np.asarray(
            [st.theta for st in bilbo_target.simulate(u_tgt_lin, reset=True, include_zero_step=False)])
        e_lin = y_src - y_tgt_lin

        U_lin = build_U_linear(u_src)  # (N, N)
        L_lin = getOptimalLearningMatrixFromMatrix(U_lin)  # your function
        t_lin = t_lin + L_lin @ e_lin

        # ---- Features path ----
        u_tgt_feat = apply_transfer_features(t_cat, u_src)
        y_tgt_feat = np.asarray(
            [st.theta for st in bilbo_target.simulate(u_tgt_feat, reset=True, include_zero_step=False)])
        e_feat = y_src - y_tgt_feat

        U_feat = build_U_features(u_src)  # (N, p*N)
        A = U_feat.T @ (Q @ U_feat) + S_feat  # (p*N, p*N)
        g = U_feat.T @ (Q @ e_feat)  # (p*N,)
        delta_t = np.linalg.solve(A, g)
        t_cat = t_cat + 0.8 * delta_t  # mild step size

        # ---- Verification (same trajectory for both) ----
        y_ver_lin = np.asarray(
            [st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin, verification_input),
                                                      reset=True, include_zero_step=False)])
        y_ver_feat = np.asarray(
            [st.theta for st in bilbo_target.simulate(apply_transfer_features(t_cat, verification_input),
                                                      reset=True, include_zero_step=False)])

        ver_err_lin_hist.append(np.linalg.norm(y_ver_lin - theta_src_ver))
        ver_err_feat_hist.append(np.linalg.norm(y_ver_feat - theta_src_ver))
        lin_dist_to_true_hist.append(np.linalg.norm(t_true_linear - t_lin))

    # ---------- Plots ----------
    # 1) Verification error norms
    plt.figure()
    plt.plot(ver_err_lin_hist, label='Linear (your IITL)')
    plt.plot(ver_err_feat_hist, label='Nonlinear features (A)')
    plt.xlabel('Iteration');
    plt.ylabel('‖verification error‖')
    plt.title('Verification error over iterations')
    plt.grid(True);
    plt.legend()

    # 2) Final verification trajectory overlay
    y_ver_lin = np.asarray([st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin, verification_input),
                                                                     reset=True, include_zero_step=False)])
    y_ver_feat = np.asarray(
        [st.theta for st in bilbo_target.simulate(apply_transfer_features(t_cat, verification_input),
                                                  reset=True, include_zero_step=False)])
    plt.figure()
    plt.plot(t_vec, theta_src_ver, label='Source (verification)')
    plt.plot(t_vec, y_ver_lin, label='Target w/ Linear transfer')
    plt.plot(t_vec, y_ver_feat, label='Target w/ Features transfer')
    plt.xlabel('t');
    plt.title('Verification outputs');
    plt.legend();
    plt.grid(True)

    # 3) Optional: distance to t_true_linear for the linear method
    plt.figure()
    plt.plot(lin_dist_to_true_hist)
    plt.title('‖t_linear - t_true_linear‖ (reference)')
    plt.xlabel('Iteration');
    plt.grid(True)

    plt.show()

def example_iitl_linear_plus_gp_residual_compare():
    """
    Compare:
      - Linear IITL (your original per-trial Lj update)
      - Linear IITL + GP residual Δu_GP(u_src) learned from data

    The two methods train and verify on the SAME trajectories.

    Assumes your environment provides:
      - BILBO_Dynamics_2D, BILBO_Dynamics_2D_Linear
      - DEFAULT_BILBO_MODEL, BILBO_MICHAEL_MODEL (if needed), BILBO_2D_POLES
      - generate_time_vector, generate_random_input
      - vec2liftedMatrix, liftedMatrix2Vec, getTransitionMatrixFromSystem
      - getOptimalLearningMatrixFromMatrix
    """
    import numpy as np
    import matplotlib.pyplot as plt

    try:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel as C
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        raise RuntimeError(
            "This example needs scikit-learn. Please install it (e.g. `pip install scikit-learn`) and rerun."
        ) from e

    # ---------------- Settings ----------------
    Ts = 0.01
    t_vec = generate_time_vector(start=0, end=6, dt=Ts)
    N = len(t_vec)

    # Systems (adjust as you like)
    BILBO_CLASS = BILBO_Dynamics_2D
    MODEL_SOURCE = DEFAULT_BILBO_MODEL
    POLES_SOURCE = BILBO_2D_POLES

    MODEL_TARGET = DEFAULT_BILBO_MODEL
    POLES_TARGET = [0, -10, -2+1j, -2-1j]  # example nonlinear-ish target pole placement

    # Training config
    NL = 12          # number of training trajectories
    J  = 30          # iterations
    wnd = 5          # causal taps for GP features: use [u[n], u[n-1], ..., u[n-wnd+1]]
    rho = 1e-2       # Tikhonov reg. for Δu* = argmin ||P Δu - e||^2 + rho||Δu||^2
    gp_train_every = 3      # refit GP every k iterations
    max_gp_points  = 1000   # subsample to keep GP cubic cost reasonable
    rng = np.random.default_rng(0)

    # ---------------- Systems ----------------
    bilbo_source = BILBO_CLASS(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)

    bilbo_target = BILBO_CLASS(model=MODEL_TARGET, Ts=Ts)
    bilbo_target.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)

    # Linear proxies to build P_target and linear-oracle t*
    bilbo_target_linear = BILBO_Dynamics_2D_Linear(model=MODEL_TARGET, Ts=Ts)
    bilbo_target_linear.polePlacement(poles=POLES_TARGET, apply_poles_to_system=True)
    P_target = getTransitionMatrixFromSystem(bilbo_target_linear.system, N=N)

    bilbo_source_linear = BILBO_Dynamics_2D_Linear(model=MODEL_SOURCE, Ts=Ts)
    bilbo_source_linear.polePlacement(poles=POLES_SOURCE, apply_poles_to_system=True)
    P_source = getTransitionMatrixFromSystem(bilbo_source_linear.system, N=N)
    t_true_linear = liftedMatrix2Vec(np.linalg.inv(P_target) @ P_source)

    # ---------------- Shared data ----------------
    verification_input = generate_random_input(t_vec, f_cutoff=2.0, sigma_I=1.0)
    theta_src_ver = np.asarray([s.theta for s in bilbo_source.simulate(verification_input, reset=True, include_zero_step=False)])

    freq_min, freq_max = 0.5, 8.0
    sig_min, sig_max = 0.5, 1.5

    learn_inputs, learn_outputs = [], []
    for _ in range(NL):
        u = generate_random_input(
            t_vec,
            f_cutoff=float(rng.uniform(freq_min, freq_max)),
            sigma_I=float(rng.uniform(sig_min, sig_max)),
        )
        theta = np.asarray([st.theta for st in bilbo_source.simulate(u, reset=True, include_zero_step=False)])
        learn_inputs.append(u)
        learn_outputs.append(theta)

    # ---------------- Helpers ----------------
    def apply_transfer_linear(t_lin, u_src):
        return vec2liftedMatrix(t_lin) @ u_src

    def build_U_linear(u_src):
        return P_target @ vec2liftedMatrix(u_src)  # (N, N)

    def hankel_features(u, taps=wnd):
        """
        Build causal, per-time-step feature vectors:
        x[n] = [u[n], u[n-1], ..., u[n-taps+1],  u[n]^2, ...,  tanh(u[n]), ...]
        Shape: (N, d). We pad the first taps-1 with zeros (causal).
        """
        u = np.asarray(u).reshape(-1)
        Nloc = u.shape[0]
        # base taps (causal)
        X = np.zeros((Nloc, taps))
        for k in range(taps):
            X[k:, k] = u[:Nloc-k]
        # add simple nonlinearities on the current sample
        nonlin = np.stack([u, u**2, np.tanh(u)], axis=1)  # (N, 3)
        return np.hstack([X, nonlin])  # (N, taps+3)

    # GP model (Standardize X and y)
    kernel = C(1.0, (1e-3, 1e3)) * RBF(length_scale=np.ones(wnd+3), length_scale_bounds=(1e-2, 1e3)) \
             + WhiteKernel(noise_level=1e-4, noise_level_bounds=(1e-8, 1e-1))
    gp = GaussianProcessRegressor(kernel=kernel, alpha=0.0, normalize_y=True, n_restarts_optimizer=1, random_state=0)
    x_scaler = StandardScaler()

    # ---------------- Initialization ----------------
    t_lin_only = np.zeros(N)  # linear-only baseline
    t_lin_gp   = np.zeros(N)  # linear part for the GP-enhanced method

    # Logs
    ver_err_lin_hist = []
    ver_err_gp_hist  = []
    lin_dist_to_true_hist = []

    # GP dataset buffers
    X_gp_all = None   # (M, d)
    y_gp_all = None   # (M,)  targets for Δu*

    # Precompute (P^T P + rho I)^{-1} P^T for Δu* mapping
    PtP = P_target.T @ P_target
    A_inv = np.linalg.inv(PtP + rho * np.eye(N))
    P_pinv_rho = A_inv @ P_target.T

    # ---------------- Iterations ----------------
    for j in range(J):
        u_src = learn_inputs[j % NL]
        y_src = learn_outputs[j % NL]

        # ===== Linear-only method =====
        u_tgt_lin = apply_transfer_linear(t_lin_only, u_src)
        y_tgt_lin = np.asarray([st.theta for st in bilbo_target.simulate(u_tgt_lin, reset=True, include_zero_step=False)])
        e_lin = y_src - y_tgt_lin

        U_lin = build_U_linear(u_src)
        L_lin = getOptimalLearningMatrixFromMatrix(U_lin)
        t_lin_only = t_lin_only + L_lin @ e_lin

        # ===== Linear + GP residual method =====
        # Current baseline + residual prediction
        # If GP isn't trained yet, Δu_GP = 0
        if X_gp_all is None:
            delta_u_gp = np.zeros_like(u_src)
        else:
            X_pred = hankel_features(u_src, taps=wnd)
            X_pred_std = x_scaler.transform(X_pred)
            delta_u_gp = gp.predict(X_pred_std)

        # Apply combined input to target
        u_tgt_gp = apply_transfer_linear(t_lin_gp, u_src) + delta_u_gp
        y_tgt_gp = np.asarray([st.theta for st in bilbo_target.simulate(u_tgt_gp, reset=True, include_zero_step=False)])
        e_gp = y_src - y_tgt_gp

        # Update the linear part as usual (keeps stability/structure)
        U_lin_gp = build_U_linear(u_src)
        L_lin_gp = getOptimalLearningMatrixFromMatrix(U_lin_gp)
        t_lin_gp = t_lin_gp + L_lin_gp @ e_gp

        # Supervised target for the GP residual this iteration:
        # desired Δu* to reduce the *current* output error e_gp
        delta_u_star = P_pinv_rho @ e_gp  # (N,)

        # Build features for this u_src and append to dataset
        X_new = hankel_features(u_src, taps=wnd)  # (N, d)
        y_new = delta_u_star                      # (N,)

        if X_gp_all is None:
            X_gp_all = X_new
            y_gp_all = y_new
        else:
            X_gp_all = np.vstack([X_gp_all, X_new])
            y_gp_all = np.concatenate([y_gp_all, y_new])

        # Subsample if dataset grows too large (for GP cubic scaling)
        if X_gp_all.shape[0] > max_gp_points:
            idx = rng.choice(X_gp_all.shape[0], size=max_gp_points, replace=False)
            X_gp_all = X_gp_all[idx]
            y_gp_all = y_gp_all[idx]

        # Fit (or refit) GP periodically
        if (j % gp_train_every) == 0:
            X_std = x_scaler.fit_transform(X_gp_all)
            gp.fit(X_std, y_gp_all)

        # ===== Verification (same trajectory for both) =====
        # Linear-only
        y_ver_lin = np.asarray([st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin_only, verification_input),
                                                                         reset=True, include_zero_step=False)])
        # Linear + GP
        if X_gp_all is None:
            delta_u_gp_ver = np.zeros_like(verification_input)
        else:
            X_ver = hankel_features(verification_input, taps=wnd)
            X_ver_std = x_scaler.transform(X_ver)
            delta_u_gp_ver = gp.predict(X_ver_std)

        y_ver_gp = np.asarray([st.theta for st in bilbo_target.simulate(
            apply_transfer_linear(t_lin_gp, verification_input) + delta_u_gp_ver,
            reset=True, include_zero_step=False)])

        ver_err_lin_hist.append(np.linalg.norm(y_ver_lin - theta_src_ver))
        ver_err_gp_hist.append(np.linalg.norm(y_ver_gp  - theta_src_ver))
        lin_dist_to_true_hist.append(np.linalg.norm(t_true_linear - t_lin_only))

    # ---------------- Plots ----------------
    # 1) Verification error norms
    plt.figure()
    plt.plot(ver_err_lin_hist, label='Linear IITL')
    plt.plot(ver_err_gp_hist,  label='Linear IITL + GP residual')
    plt.xlabel('Iteration'); plt.ylabel('‖verification error‖')
    plt.title('Verification error over iterations')
    plt.grid(True); plt.legend()

    # 2) Final verification trajectory overlay
    # Linear-only
    y_ver_lin = np.asarray([st.theta for st in bilbo_target.simulate(apply_transfer_linear(t_lin_only, verification_input),
                                                                     reset=True, include_zero_step=False)])
    # Linear+GP
    if X_gp_all is None:
        delta_u_gp_ver = np.zeros_like(verification_input)
    else:
        X_ver = hankel_features(verification_input, taps=wnd)
        X_ver_std = x_scaler.transform(X_ver)
        delta_u_gp_ver = gp.predict(X_ver_std)

    y_ver_gp = np.asarray([st.theta for st in bilbo_target.simulate(
        apply_transfer_linear(t_lin_gp, verification_input) + delta_u_gp_ver,
        reset=True, include_zero_step=False)])

    plt.figure()
    plt.plot(t_vec, theta_src_ver, label='Source (verification)')
    plt.plot(t_vec, y_ver_lin, label='Target w/ Linear IITL')
    plt.plot(t_vec, y_ver_gp,  label='Target w/ Linear + GP residual')
    plt.xlabel('t'); plt.title('Verification outputs'); plt.legend(); plt.grid(True)

    # 3) Reference: distance to linear-oracle t*
    plt.figure()
    plt.plot(lin_dist_to_true_hist)
    plt.title('‖t_linear - t_true_linear‖ (linear path)')
    plt.xlabel('Iteration'); plt.grid(True)

    plt.show()


if __name__ == '__main__':
    example_iitl_linear_plus_gp_residual_compare()
