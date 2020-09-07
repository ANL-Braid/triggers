import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Optional

from boto3.dynamodb.conditions import Attr, Key
from boto3.dynamodb.table import TableResource as DynamoTable
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import HTTPException
from pydantic import BaseModel

from pseudo_trigger.aws_helpers import create_aws_client, create_aws_resource
from pseudo_trigger.config import get_config_val
from pseudo_trigger.log import setup_python_logging
from pseudo_trigger.models import InternalTrigger

_triggers: Dict[str, InternalTrigger] = {}
log = logging.getLogger(__name__)
setup_python_logging(log)

_TRIGGER_KEY_SCHEMA = ({"AttributeName": "id", "KeyType": "HASH"},)
_TRIGGER_ATTRIBUTE_DEFINITIONS = ({"AttributeName": "id", "AttributeType": "S"},)


def create_table(
    table_name: str,
    key_schema: Iterable[Mapping[str, str]],
    attribute_definitions: Iterable[Mapping[str, str]],
    **kwargs,
) -> DynamoTable:
    try:
        client = create_aws_resource("dynamodb")
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=attribute_definitions,
            KeySchema=key_schema,
            **kwargs,
        )
    except ClientError as ce:
        error_code = ce.response.get("Error", {}).get("Code")
        if error_code == "ResourceInUseException":
            log.info(f"Table {table_name} already exists")
        else:
            log.info(
                f"Error creating dynamo table {table_name}, may be because "
                f"it exists already: {str(ce)}"
            )

    except EndpointConnectionError as err:
        log.info(f"Error creating dynamo table {table_name}: {err}")

    table: DynamoTable = client.Table(table_name)
    return table


def get_table(
    table_name: str,
) -> DynamoTable:
    client = create_aws_resource("dynamodb")
    table: DynamoTable = client.Table(table_name)
    return table


def lookup_trigger(trigger_id: str) -> Optional[InternalTrigger]:
    table = get_table(
        get_config_val("aws.dynamodb.table_name"),
    )
    response = table.query(KeyConditionExpression=Key("id").eq(trigger_id))
    items = response.get("Items")
    if len(items) == 0:
        return None
    try:
        trigger = InternalTrigger(**items[0])
    except Exception as e:
        log.error(f"Cannot create Trigger from {items[0]} got {str(e)}")

    return trigger


"""
    trigger = _triggers.get(trigger_id)
    if trigger is None:
        raise HTTPException(
            status_code=404, detail=f"No trigger with id '{trigger_id}'"
        )
"""


def _to_dynamo_dict(model: BaseModel) -> Dict[str, Any]:
    json_str = model.json()
    model_dict = json.loads(json_str)
    return model_dict


def store_trigger(trigger: InternalTrigger) -> InternalTrigger:
    table = get_table(
        get_config_val("aws.dynamodb.table_name"),
    )
    if trigger.id is None:
        trigger.id = str(uuid.uuid4())
    trigger_dict = _to_dynamo_dict(trigger)
    table.put_item(Item=trigger_dict)
    # _triggers[trigger.id] = trigger
    return trigger


def update_trigger(trigger: InternalTrigger) -> InternalTrigger:
    table = get_table(
        get_config_val("aws.dynamodb.table_name"),
    )
    if trigger.id is None:
        trigger.id = str(uuid.uuid4())
    trigger_dict = _to_dynamo_dict(trigger)
    table.put_item(Item=trigger_dict)
    # _triggers[trigger.id] = trigger
    return trigger


def remove_trigger(trigger_id: str) -> InternalTrigger:
    table = get_table(
        get_config_val("aws.dynamodb.table_name"),
    )
    del_resp = table.delete_item(
        Key={
            "id": trigger_id,
        },
        ReturnValues="ALL_OLD",
    )
    item = del_resp.get("Attributes")
    return InternalTrigger(**item)


def enum_triggers(**kwargs) -> List[InternalTrigger]:
    """
    This is probably really inefficient
    """
    table = get_table(
        get_config_val("aws.dynamodb.table_name"),
    )
    filter_expression = None
    for attr_name, val in kwargs.items():
        this_filter_expression = Attr(attr_name).eq(val)
        if filter_expression is None:
            filter_expression = this_filter_expression
        else:
            filter_expression = filter_expression & this_filter_expression
    response = table.scan(FilterExpression=filter_expression)
    items = response.get("Items", [])
    ret_items = [InternalTrigger(**i) for i in items]
    return ret_items


def init_persistence() -> None:
    local_dynamo_config = {}
    dynamo_config = get_config_val("aws.dynamodb")
    local_dynamo_config.update(dynamo_config)
    do_create = local_dynamo_config.pop("create_table", False)

    # Hack(?) since this has a sub-key
    local_dynamo_config.pop("client_params")

    if do_create:
        table_name = local_dynamo_config.pop("table_name", None)
        if table_name is None:
            print("CANNOT CREATE DYNAMO TABLE, NO table_name configured")
        else:
            create_table(
                table_name=table_name,
                key_schema=_TRIGGER_KEY_SCHEMA,
                attribute_definitions=_TRIGGER_ATTRIBUTE_DEFINITIONS,
                **local_dynamo_config,
            )
    return
