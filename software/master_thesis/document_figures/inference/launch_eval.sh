#!/usr/bin/env bash
# Launches each evaluation cell in its own tmux session.
#
# Usage (from repo root, optional group filter):
#   bash master_thesis/document_figures/inference/launch_eval.sh        # all runs
#   bash master_thesis/document_figures/inference/launch_eval.sh A      # scenario A only
#   bash master_thesis/document_figures/inference/launch_eval.sh C D    # scenarios C and D
#
# Attach to any session by name, e.g.:
#   tmux attach -t A_0sg
#   tmux attach -t A_mlp
#   tmux attach -t A_hom_gnn
#   tmux attach -t A_bi_gnn
#   tmux attach -t C_0sg
#   tmux attach -t C_bi_gnn
#   tmux attach -t D_0sg
#   tmux attach -t D_bi_gnn

VENV="$(pwd)/.venv/bin/python"
SCRIPT="master_thesis.document_figures.inference.run_eval"

declare -A N_EP
N_EP["A_0sg"]=200;    N_EP["A_mlp"]=200;    N_EP["A_hom_gnn"]=200; N_EP["A_bi_gnn"]=200
N_EP["C_0sg"]=50;     N_EP["C_bi_gnn"]=50
N_EP["D_0sg"]=50;     N_EP["D_bi_gnn"]=50

ALL_RUNS=("A_0sg" "A_mlp" "A_hom_gnn" "A_bi_gnn" "C_0sg" "C_bi_gnn" "D_0sg" "D_bi_gnn")

# Filter by prefix if args given (e.g. A, C D)
if [ $# -gt 0 ]; then
    FILTERED=()
    for RUN in "${ALL_RUNS[@]}"; do
        for PREFIX in "$@"; do
            if [[ "$RUN" == ${PREFIX}_* ]]; then
                FILTERED+=("$RUN")
                break
            fi
        done
    done
    ALL_RUNS=("${FILTERED[@]}")
fi

for RUN in "${ALL_RUNS[@]}"; do
    N="${N_EP[$RUN]}"
    CMD="caffeinate -i $VENV -m $SCRIPT --run $RUN --n $N"
    tmux kill-session -t "$RUN" 2>/dev/null || true
    tmux new-session -d -s "$RUN"
    tmux send-keys -t "$RUN" "$CMD" Enter
    echo "Started session '$RUN'  (n=$N)"
done

echo ""
echo "Attach with:  tmux attach -t <session_name>"
