#!/usr/bin/env fish
# ------------------------------------------------------------
# Launch bp_C, bp_D, bp_A_ft each in their own tmux session
# (3+3+2 = 8 workers total)
# Run this script AFTER bp_A finishes its current 500-update run.
# ------------------------------------------------------------

set ROOT (dirname (status filename))
set PYTHON $ROOT/.venv/bin/python
set CKPT   $ROOT/master_thesis/modules/subgoal_predictor/checkpoints/bp_A_20260414_005433.pt

cd $ROOT

echo "=== Launching bp_C (10-agent 2-gap 3x3, 3 workers) ==="
tmux new-session -d -s bp_C \
    "caffeinate -i $PYTHON -m master_thesis.modules.subgoal_predictor.train_subgoal \
        --arch bipartite --stage bp_C --scenario rl_8n_fixed_2gap_3x3 \
        --algo ppo --updates 500 --batch 32 --max_steps 850 \
        --lr 3e-4 --wait_mode continuous \
        --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
        --skip_penalty 4.0 --failed_plan_penalty 0.5 \
        --ompl_timelimit 3.0 --n_workers 3 \
        2>&1 | tee /tmp/bp_C.log"

echo "=== Launching bp_D (8-agent 1-gap 3x3, 3 workers) ==="
tmux new-session -d -s bp_D \
    "caffeinate -i $PYTHON -m master_thesis.modules.subgoal_predictor.train_subgoal \
        --arch bipartite --stage bp_D --scenario rl_8n_fixed_1gap_3x3 \
        --algo ppo --updates 500 --batch 32 --max_steps 850 \
        --lr 3e-4 --wait_mode continuous \
        --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
        --skip_penalty 4.0 --failed_plan_penalty 0.5 \
        --ompl_timelimit 3.0 --n_workers 3 \
        2>&1 | tee /tmp/bp_D.log"

echo "=== Launching bp_A_ft (5-agent 1-gap 2x2 fine-tune, 2 workers) ==="
tmux new-session -d -s bp_A_ft \
    "caffeinate -i $PYTHON -m master_thesis.modules.subgoal_predictor.train_subgoal \
        --arch bipartite --stage bp_A_ft --scenario rl_5n_fixed_1gap_2x2 \
        --loadw $CKPT \
        --algo ppo --updates 500 --batch 32 --max_steps 550 \
        --lr 1e-4 --lr_end 1e-5 --lr_schedule cosine \
        --wait_mode continuous \
        --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
        --skip_penalty 4.0 --failed_plan_penalty 0.5 \
        --ompl_timelimit 3.0 --n_workers 2 \
        2>&1 | tee /tmp/bp_A_ft.log"

echo "All three tmux sessions launched."
echo "Monitor with: tmux attach -t bp_C / bp_D / bp_A_ft"
echo "Or tail logs: tail -f /tmp/bp_C.log"
