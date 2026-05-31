"""
config_loader.py
----------------
Loads a training config YAML and returns a flat dict of hyperparameters
whose keys match the parameter names of train() in train_subgoal.py.

Usage
-----
    from master_thesis.modules.subgoal_predictor.training_configs.config_loader import load_training_config

    hparams = load_training_config("training_configs/my_run.yaml")
    train(**hparams)

YAML key names follow the train() signature exactly.  The only exception is
`wait_times`, which maps to the module-level WAIT_TIMES list in train_subgoal.py
and must be handled by the caller.

Precedence when used alongside argparse:
    CLI explicit flags  >  YAML values  >  argparse defaults
"""

import yaml
from pathlib import Path

# Keys that train() requires (no default value) — config must supply them.
_REQUIRED = ('n_updates', 'batch_size')

# All keys that load_training_config accepts and their expected Python types.
# Used for type-checking and early error messages.
_FIELD_TYPES: dict[str, type | tuple] = {
    'n_updates':            int,
    'batch_size':           int,
    'max_steps':            int,
    'log_dir':              str,
    'save_dir':             str,
    'initial_weights':      (str, type(None)),
    'save_every':           int,
    'run_name_override':    (str, type(None)),
    'resume':               bool,
    'record':               bool,
    'eval_out':             (str, type(None)),
    'scenario':             str,
    'n_subgoals':           int,
    'ompl_timelimit':       (int, float),
    'wait_mode':            str,
    'skip_penalty':         (int, float),
    'failed_plan_penalty':  (int, float),
    'arch':                 str,
    'algo':                 str,
    'lr':                   (int, float),
    'lr_end':               (int, float, type(None)),
    'lr_schedule':          str,
    'entropy_coeff_pos':    (int, float),
    'entropy_coeff_wait':   (int, float),
    'diversity_sigma':      (int, float),
    'n_workers':            int,
    'stage':                (str, type(None)),
    'evaluate':             bool,
    'wait_times':           (list, type(None)),   # handled separately by caller
}


def load_training_config(path: str | Path) -> dict:
    """Load a training config YAML and return a validated hparam dict.

    Parameters
    ----------
    path:
        Path to the YAML file.

    Returns
    -------
    dict
        Flat dict whose keys match train() parameter names.
        Only keys present in the file are returned — callers apply their
        own defaults for missing keys.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    KeyError
        If a required field (n_updates, batch_size) is missing.
    TypeError
        If a field value has an unexpected type.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: '{path}'")

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping at the top level, got {type(raw).__name__}")

    # Validate required fields
    for key in _REQUIRED:
        if key not in raw:
            raise KeyError(f"Config '{path}' is missing required field: '{key}'")

    # Type-check known fields; warn on unknown keys
    hparams: dict = {}
    for key, value in raw.items():
        if key not in _FIELD_TYPES:
            import warnings
            warnings.warn(f"Unknown config key '{key}' will be ignored.", stacklevel=2)
            continue
        expected = _FIELD_TYPES[key]
        if not isinstance(value, expected):
            raise TypeError(
                f"Config field '{key}': expected {expected}, got {type(value).__name__} ({value!r})"
            )
        hparams[key] = value

    return hparams
