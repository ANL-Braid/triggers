import collections
import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import toml

_DEFAULT_ENVIRONMENT = "dev"

_ENVIRONMENT_SOURCES = [
    "COPILOT_ENVIRONMENT_NAME",
    "PSEUDO_TRIGGER_ENVIRONMENT",
    "TRIGGER_ENVIRONMENT",
]

_CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"


# Precedence goes up, so values from last in the list overwrites values from first in the
# list
_CONFIG_FILE_TEMPLATES = ["global.toml", "{}.toml", "{}-local.toml"]


def _get_environment() -> str:
    for env_source in _ENVIRONMENT_SOURCES:
        env_val = os.environ.get(env_source)
        if env_val is not None:
            return env_val
    return _DEFAULT_ENVIRONMENT


_config: Optional[Dict[str, Any]] = None


def _deep_update(d: Mapping, u: Mapping) -> Mapping:
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = _deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def _load_config() -> Dict[str, Any]:
    global _config
    if _config is not None:
        return _config
    env = _get_environment()
    if _config is None:
        _config = {"ENVIRONMENT": env}
    for config_file in _CONFIG_FILE_TEMPLATES:
        config_file_path = _CONFIG_ROOT / config_file.format(env)
        try:
            config_info = toml.load(str(config_file_path))
            print(f"LOADED Config from {config_file_path}")
            _deep_update(_config, config_info)
        except Exception as e:
            print(
                f"UNABLE TO LOAD CONFIG: {config_file_path} due to {str(e)}",
                file=sys.stderr,
            )
    _config.update({"OS_ENVIRONMENT": os.environ})
    return _config


def get_config_val(
    config_path: str, default: Optional[Any] = None, path_sep: str = "."
) -> Any:
    config = _load_config()
    parts = config_path.split(path_sep)
    for part in parts:
        if part in config:
            config = config[part]
            if isinstance(config, str) and config.startswith("environ::"):
                config_parts = config.split("::")
                if len(config_parts) < 2:
                    config_parts.append(default)
                config = os.environ.get(config_parts[1], config_parts[2])
                break
        else:
            config = default
            break
    return config
