import base64
import json
import logging
from json import JSONDecodeError
from typing import Any, Dict, Optional, TypeVar

import boto3
from botocore.client import BaseClient as BotoBaseClient
from botocore.exceptions import ClientError
from mypy_boto3_secretsmanager import Client as SecretsManagerClient
from pydantic import AnyHttpUrl, BaseSettings
from pydantic.env_settings import SettingsSourceCallable

from .config_vals import SERVICE_ENVIRONMENT, SERVICE_NAME
from .toml_settings import toml_config_settings_source

log = logging.getLogger(__name__)


class AWSSettings(BaseSettings):
    aws_endpoint_url: Optional[AnyHttpUrl]

    class Config:
        environment = SERVICE_ENVIRONMENT
        config_root = "config"
        extra = "ignore"

        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            **kwargs,
        ):
            return (
                toml_config_settings_source,
                env_settings,
                init_settings,
            )

    def session_kwargs(self) -> Dict[str, Any]:
        return {}

    def client_kwargs(self, client_name: str) -> Dict[str, Any]:
        return {"endpoint_url": self.aws_endpoint_url}


aws_settings = AWSSettings()

BotoBaseClientType = TypeVar("BotoBaseClientType", bound=BotoBaseClient)
BotoBaseResourceType = TypeVar(
    "BotoBaseResourceType", bound=boto3.resources.base.ServiceResource
)


def _boto3_session(
    settings: AWSSettings = aws_settings,
) -> boto3.Session:
    return boto3.Session(**settings.session_kwargs())


def boto3_client(
    client_name: str,
    client_class: type[BotoBaseClientType],
    settings: AWSSettings = aws_settings,
) -> BotoBaseClientType:
    session = _boto3_session(settings=settings)
    return session.client(client_name, **(settings.client_kwargs(client_name)))


def boto3_resource(
    resource_name: str,
    resource_class: type[BotoBaseResourceType],
    settings: AWSSettings = aws_settings,
) -> BotoBaseResourceType:

    session = _boto3_session(settings=settings)
    return session.resource(resource_name, **(settings.client_kwargs(resource_name)))


def aws_secrets_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    secrets_client = boto3_client("secretsmanager", SecretsManagerClient)
    environment = settings.__config__.environment
    secret_id = f"{SERVICE_NAME}/{environment}"
    try:
        get_secret_value_response = secrets_client.get_secret_value(SecretId=secret_id)
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary,
        # one of these fields will be populated.
        if "SecretString" in get_secret_value_response:
            secret = get_secret_value_response["SecretString"]
        else:
            secret = base64.b64decode(get_secret_value_response["SecretBinary"])

        json_secret = json.loads(secret)
        return json_secret
    except ClientError as e:
        log.error(f"Unable to load AWS secrets for id {secret_id} due to {e}")
    except JSONDecodeError as err:
        print(f"Couldn't load settings; secret {secret_id} is not valid JSON: {err}")

    return {}


def main():
    print(f"AWS Config:\n{aws_settings}")
    aws_secrets = aws_secrets_settings_source(aws_settings)
    print(f"AWS Secrets Settings:\n{aws_secrets}")
