import logging
import typing as t
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from pydantic.env_settings import SettingsSourceCallable

from .aws_ops import AWSSettings, aws_secrets_settings_source, aws_settings
from .config_vals import SERVICE_ENVIRONMENT, SERVICE_NAME
from .toml_settings import toml_config_settings_source

log = logging.getLogger(__name__)


class Settings(AWSSettings):
    # db_url: SecretStr
    service_name: str | None = SERVICE_NAME
    globus_auth_client_id: str = "Unknown"
    globus_auth_client_secret: str = "Unknown"  # SecretStr
    globus_auth_scope: str = (
        "https://auth.globus.org/scopes/"
        "5fd0098d-ef5c-4ae7-a3fd-fc972111eacd/braid_policy_engine_all"
    )
    log_level: str = "info"
    log_format: t.Literal["json", "console"] = "json"
    dynamo_table_name: str = Field("NOT_SET", env="TRIGGERS_NAME")
    create_dynamo_table: bool = False

    class Config:
        environment = SERVICE_ENVIRONMENT
        config_root = Path(__file__).resolve().parent.parent / "config"

        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            **kwargs,
        ):
            return (
                aws_secrets_settings_source,
                toml_config_settings_source,
                env_settings,
                init_settings,
            )


settings: Settings | None = None


def get_settings(**kwargs) -> Settings:
    global settings
    if settings is None:
        try:
            settings_vars = {**kwargs, **(aws_settings.dict())}
            settings = Settings(**settings_vars)
        except ValidationError as ve:
            log.warning(f"Failed to load settings due to {str(ve)}")
            settings = Settings()
    return settings
