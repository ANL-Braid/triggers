import logging
from typing import Any, Dict

import toml
from pydantic import BaseSettings

log = logging.getLogger(__name__)


def toml_config_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    environment = settings.__config__.environment
    config_root = settings.__config__.config_root
    path = f"{config_root}/{environment}.toml"
    toml_settings = {}
    try:
        toml_settings = toml.load(path)
        log.info(f"Loaded TOML config from {path}")
    except FileNotFoundError:
        log.warning(f"Unable to load toml settings from {path}")
    return toml_settings
