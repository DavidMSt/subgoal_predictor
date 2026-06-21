import yaml
from pathlib import Path

_N = type(None)


class BilbolabEnvConfig:
    scenario:            str
    max_steps:           int
    agent_log_level:     str
    alpha:               float
    beta:                float
    crossing_bonus:      float
    energy_weight:       float
    diversity_sigma:     float
    diversity_bonus:     float
    ompl_timelimit:      float
    replan_block_s:      float
    skip_penalty:        float
    failed_plan_penalty: float

    def __init__(self, path: str | Path):
        d = yaml.safe_load(Path(path).read_text())
        self.scenario            = d['scenario']
        self.max_steps           = d.get('max_steps',           400)
        self.agent_log_level     = d.get('agent_log_level',     'WARNING')
        self.alpha               = d.get('alpha',               0.3)
        self.beta                = d.get('beta',                1.0)
        self.crossing_bonus      = d.get('crossing_bonus',      1.5)
        self.energy_weight       = d.get('energy_weight',       2.0)
        self.diversity_sigma     = d.get('diversity_sigma',     0.35)
        self.diversity_bonus     = d.get('diversity_bonus',     1.5)
        self.ompl_timelimit      = d.get('ompl_timelimit',      10.0)
        self.replan_block_s      = d.get('replan_block_s',      0.0)
        self.skip_penalty        = d.get('skip_penalty',        4.0)
        self.failed_plan_penalty = d.get('failed_plan_penalty', 0.0)

_SHARED = {
    'scenario':          str,
    'arch':              str,
    'ompl_timelimit':    (int, float),
    'replan_block_s':    (int, float),
    'n_workers':         int,
}

_TRAIN = _SHARED | {
    'n_updates':          int,
    'batch_size':         int,
    'max_steps':          int,
    'log_dir':            str,
    'save_dir':           str,
    'initial_weights':    (str, _N),
    'run_name_override':  (str, _N),
    'algo':               str,
    'lr':                 (int, float),
    'lr_end':             (int, float, _N),
    'lr_schedule':        str,
    'entropy_coeff_pos':  (int, float),
    'entropy_coeff_wait': (int, float),
    'alpha':              (int, float),
    'beta':               (int, float),
    'crossing_bonus':     (int, float),
    'energy_weight':      (int, float),
    'diversity_sigma':    (int, float),
    'diversity_bonus':    (int, float),
    'stage':              (str, _N),
    'skip_penalty':       (int, float),
    'failed_plan_penalty':(int, float),
}

_RESUME = _SHARED | {
    'n_updates':         int,
    'initial_weights':   str,
    'save_dir':          str,
    'log_dir':           str,
    'save_every':        int,
    'stage':             (str, _N),
    'run_name_override': (str, _N),
}

_EVALUATE = _SHARED | {
    'n_episodes':         int,
    'initial_weights':    str,
    'eval_out':           (str, _N),
    'batch_size':         int,
    'max_steps':          int,
    'alpha':              (int, float),
    'beta':               (int, float),
    'crossing_bonus':     (int, float),
    'energy_weight':      (int, float),
    'diversity_sigma':    (int, float),
    'diversity_bonus':    (int, float),
    'skip_penalty':       (int, float),
    'failed_plan_penalty':(int, float),
}

_SCHEMA   = {'train': _TRAIN, 'resume': _RESUME, 'evaluate': _EVALUATE}
_REQUIRED = {
    'train':    ('n_updates', 'batch_size'),
    'resume':   ('n_updates', 'initial_weights'),
    'evaluate': ('n_episodes', 'initial_weights'),
}


def load_training_config(path: str | Path) -> dict:
    """Load and validate a run config YAML. Returns a flat dict including run_type."""
    raw = yaml.safe_load(Path(path).open())

    run_type = raw.get('run_type')
    if run_type not in _SCHEMA:
        raise ValueError(f"'run_type' must be one of {list(_SCHEMA)}, got {run_type!r}")

    for key in _REQUIRED[run_type]:
        if key not in raw:
            raise KeyError(f"[{run_type}] missing required field: '{key}'")

    schema = _SCHEMA[run_type]
    out = {'run_type': run_type}
    for key, value in raw.items():
        if key == 'run_type':
            continue
        if key not in schema:
            raise KeyError(f"[{run_type}] unknown field: '{key}'")
        if not isinstance(value, schema[key]):
            raise TypeError(f"[{run_type}] '{key}': got {type(value).__name__} ({value!r})")
        out[key] = value

    return out
