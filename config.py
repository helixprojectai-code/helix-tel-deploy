import os
import yaml
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).parent / "tel.yaml"

REQUIRED_KEYS = {
    "hub": ["host", "port"],
    "node": ["id"],
    "logging": ["level"],
}


def load_config(path: str = None) -> dict:
    config_path = Path(path) if path else DEFAULT_CONFIG

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError(f"Config file is empty or malformed: {config_path}")

    for section, keys in REQUIRED_KEYS.items():
        if section not in cfg:
            raise KeyError(f"Config missing required section: [{section}]")
        for key in keys:
            if key not in cfg[section]:
                raise KeyError(f"Config missing required key: [{section}].{key}")

    # Environment variable overrides
    cfg["hub"]["host"] = os.environ.get("TEL_HUB_HOST", cfg["hub"]["host"])
    cfg["hub"]["port"] = int(os.environ.get("TEL_HUB_PORT", cfg["hub"]["port"]))
    cfg["node"]["id"] = os.environ.get("TEL_NODE_ID", cfg["node"]["id"])
    cfg["node"]["seed"] = os.environ.get("TEL_NODE_SEED", cfg["node"].get("seed"))

    return cfg
