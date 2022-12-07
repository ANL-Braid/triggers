import boto3

from braid_triggers.config import get_config_val


def create_aws_resource(resource: str, **kwargs):
    client_kwargs = get_config_val("aws.client_params", default={})
    resource_client_kwargs = get_config_val(f"aws.{resource}.client_params", default={})
    client_kwargs.update(resource_client_kwargs)
    client_kwargs.update(kwargs)
    client = boto3.resource(resource, **client_kwargs)
    return client


def create_aws_client(resource: str, **kwargs):
    client_kwargs = get_config_val("aws.client_params", default={})
    resource_client_kwargs = get_config_val(f"aws.{resource}.client_params", default={})
    client_kwargs.update(resource_client_kwargs)
    client_kwargs.update(kwargs)
    client = boto3.client(resource, **client_kwargs)
    return client
