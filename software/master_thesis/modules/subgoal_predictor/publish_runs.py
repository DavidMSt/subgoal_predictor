#!/usr/bin/env python3
"""
Publish training run copies with clean, consistent names.

Creates (originals untouched):
  runs_pub/        — TensorBoard event directories, internal structure preserved
  checkpoints_pub/ — .pt and _latest.pt weight files, flat layout
  runs_pub/MAPPING.md + checkpoints_pub/MAPPING.md

Usage:
  python publish_runs.py --dry   # preview without touching anything
  python publish_runs.py         # execute the copy
"""

import argparse
import pathlib
import shutil
import textwrap

BASE      = pathlib.Path(__file__).parent
RUNS_SRC  = BASE / 'runs'
CKPT_SRC  = BASE / 'checkpoints'
RUNS_DST  = BASE / 'runs_pub'
CKPT_DST  = BASE / 'checkpoints_pub'

# ── Mapping ───────────────────────────────────────────────────────────────────
# Each entry: (run_dir relative to RUNS_SRC,
#              ckpt stem relative to CKPT_SRC,   ← supports subdir (homogeneous_gnn/)
#              published name,
#              is_selected_checkpoint)
#
# Chains are ordered oldest → newest (left to right in training plot).
# ★ marks the checkpoint used in evaluation (run_eval.py).

CHAINS: dict[str, list[tuple[str, str, str, bool]]] = {
    'A_mlp': [
        ('homogeneous_gnn/pre_030426/stage1b_20260324_103903',
         'homogeneous_gnn/stage1b_20260324_103903',
         'A_mlp_stage1b', True),                                      # ★ — no wait head; wait introduced with hom_gnn
    ],
    'A_mlp_discrete': [
        # MLP trained from scratch with discrete wait bins — architectural exploration
        ('homogeneous_gnn/pre_030426/stage2-scratch-v2_20260328_101252',
         'homogeneous_gnn/stage2-scratch-v2_20260328_101252',
         'A_mlp_disc_v2a', False),
        ('homogeneous_gnn/pre_030426/stage2-scratch-v2_20260329_123527',
         'homogeneous_gnn/stage2-scratch-v2_20260329_123527',
         'A_mlp_disc_v2b', False),
    ],
    'A_hom_gnn_discrete': [
        # Hom. GNN with discrete wait bins — run before switching to continuous wait_mode
        ('homogeneous_gnn/gnn_ppo_D2_20260403_221437',
         'homogeneous_gnn/gnn_ppo_D2_20260403_221437',
         'A_hom_gnn_disc', False),
    ],
    'A_hom_gnn': [
        ('homogeneous_gnn/gnn_ppo_D2_cont_20260406_144831',
         'homogeneous_gnn/gnn_ppo_D2_cont_20260406_144831',
         'A_hom_gnn_base', False),
        ('homogeneous_gnn/gnn_ppo_D2_cont_v2_20260407_160009',
         'homogeneous_gnn/gnn_ppo_D2_cont_v2_20260407_160009',
         'A_hom_gnn_v2', False),
        # v3 was resumed twice — a/b/c are segments of the same stage/hyperparams
        ('homogeneous_gnn/gnn_ppo_D2_cont_v3_20260408_153650',
         'homogeneous_gnn/gnn_ppo_D2_cont_v3_20260408_153650',
         'A_hom_gnn_v3a', False),
        ('homogeneous_gnn/gnn_ppo_D2_cont_v3_20260409_125024',
         'homogeneous_gnn/gnn_ppo_D2_cont_v3_20260409_125024',
         'A_hom_gnn_v3b', False),
        ('homogeneous_gnn/gnn_ppo_D2_cont_v3_20260411_174544',
         'homogeneous_gnn/gnn_ppo_D2_cont_v3_20260411_174544',
         'A_hom_gnn_v3c', False),
        ('homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158',
         'homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158',
         'A_hom_gnn_phase2', True),                                     # ★
    ],
    'A_bi_gnn': [
        ('bp_A_20260414_005433',     'bp_A_20260414_005433',     'A_bi_gnn_base', False),
        ('bp_A_ft2_20260416_094315', 'bp_A_ft2_20260416_094315', 'A_bi_gnn_ft2',  True),  # ★
        # ft3-ft5: continued past ★, performance deteriorated
        ('bp_A_ft3_20260416_235148', 'bp_A_ft3_20260416_235148', 'A_bi_gnn_ft3', False),
        ('bp_A_ft4_20260419_021501', 'bp_A_ft4_20260419_021501', 'A_bi_gnn_ft4', False),
        ('bp_A_ft5_20260420_121017', 'bp_A_ft5_20260420_121017', 'A_bi_gnn_ft5', False),
    ],
    'C_bi_gnn': [
        # v1-v3 of the original run were independent fresh starts (excluded)
        ('bp_C_20260415_140332',  'bp_C_20260415_140332',  'C_bi_gnn_v1', False),
        ('bp_C_20260417_181304',  'bp_C_20260417_181304',  'C_bi_gnn_v2', False),
        ('bp_C_20260420_235105',  'bp_C_20260420_235105',  'C_bi_gnn_v3', True),   # ★
        ('bp_C2_20260423_232318', 'bp_C2_20260423_232318', 'C_bi_gnn_v4', False),
    ],
    'D_bi_gnn': [
        # original bp_D v1 was an abandoned fresh start (excluded)
        ('bp_D_20260415_110413',  'bp_D_20260415_110413',  'D_bi_gnn_v1', False),
        ('bp_D2_20260419_234212', 'bp_D2_20260419_234212', 'D_bi_gnn_v2', False),
        ('bp_D2_20260421_144251', 'bp_D2_20260421_144251', 'D_bi_gnn_v3', True),   # ★
        ('bp_D3_20260423_231814', 'bp_D3_20260423_231814', 'D_bi_gnn_v4', False),
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ckpt_files(ckpt_rel: str) -> list[tuple[pathlib.Path, str]]:
    """Return list of (src_path, stem_suffix) for .pt and _latest.pt."""
    stem = pathlib.Path(ckpt_rel).name
    parent = CKPT_SRC / pathlib.Path(ckpt_rel).parent
    results = []
    for suffix in ('', '_latest'):
        src = parent / f'{stem}{suffix}.pt'
        results.append((src, suffix))
    return results


def _verify_sources():
    missing = []
    for policy, entries in CHAINS.items():
        for run_rel, ckpt_rel, name, _ in entries:
            run_src = RUNS_SRC / run_rel
            if not run_src.exists():
                missing.append(f'  run  : {run_src}')
            # Only the best checkpoint (.pt) is required; _latest.pt may not exist for old runs
            best_src, _ = _ckpt_files(ckpt_rel)[0]
            if not best_src.exists():
                missing.append(f'  ckpt : {best_src}')
    if missing:
        print('ERROR — missing source files:')
        for m in missing:
            print(m)
        return False
    return True


def _generate_mapping_md() -> str:
    lines = ['# Training Run Mapping\n',
             'Maps published names → original names + warm-start chain.\n',
             '★ = checkpoint selected for evaluation (run_eval.py).\n',
             'a/b/c suffix = resumed segments of the same experimental stage.\n']
    for policy, entries in CHAINS.items():
        lines.append(f'\n## {policy}\n')
        lines.append('| Published name | Original name | Selected |\n')
        lines.append('|---|---|:---:|\n')
        for run_rel, ckpt_rel, name, is_ep in entries:
            orig = pathlib.Path(run_rel).name
            star = '★' if is_ep else ''
            lines.append(f'| `{name}` | `{orig}` | {star} |\n')
    return ''.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def publish(dry: bool):
    tag = '[DRY]' if dry else '[COPY]'

    if not _verify_sources():
        return

    errors = []
    mapping_md = _generate_mapping_md()

    for policy, entries in CHAINS.items():
        print(f'\n=== {policy} ===')
        for run_rel, ckpt_rel, name, is_ep in entries:
            marker = ' ★' if is_ep else ''
            print(f'  {name}{marker}')

            # — run directory —
            src = RUNS_SRC / run_rel
            dst = RUNS_DST / name
            print(f'    {tag} run  {src} → {dst}')
            if not dry:
                if dst.exists():
                    print(f'         [skip — already exists]')
                else:
                    try:
                        shutil.copytree(src, dst)
                    except Exception as e:
                        errors.append(f'run {name}: {e}')

            # — checkpoint files —
            for src_ckpt, suffix in _ckpt_files(ckpt_rel):
                if not src_ckpt.exists():
                    print(f'    [skip] {src_ckpt.name} not found (no _latest saved)')
                    continue
                dst_ckpt = CKPT_DST / f'{name}{suffix}.pt'
                print(f'    {tag} ckpt {src_ckpt.name} → {dst_ckpt.name}')
                if not dry:
                    dst_ckpt.parent.mkdir(parents=True, exist_ok=True)
                    if dst_ckpt.exists():
                        print(f'         [skip — already exists]')
                    else:
                        try:
                            shutil.copy2(src_ckpt, dst_ckpt)
                        except Exception as e:
                            errors.append(f'ckpt {name}{suffix}: {e}')

    # — MAPPING.md —
    for dst_dir in (RUNS_DST, CKPT_DST):
        dst_md = dst_dir / 'MAPPING.md'
        print(f'\n  {tag} write {dst_md}')
        if not dry:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst_md.write_text(mapping_md)

    if errors:
        print('\nERRORS:')
        for e in errors:
            print(f'  {e}')
    elif not dry:
        print('\nDone. Originals untouched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry', action='store_true',
                        help='Preview without copying anything')
    args = parser.parse_args()
    publish(dry=args.dry)
