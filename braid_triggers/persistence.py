import logging
import numbers
import typing as t
import uuid

from boto3.dynamodb.conditions import Attr, Key
from boto3.dynamodb.types import Binary, Decimal
from botocore.exceptions import ClientError, EndpointConnectionError
from mypy_boto3_dynamodb import DynamoDBServiceResource
from mypy_boto3_dynamodb.service_resource import Table as DynamoTable
from pydantic import BaseModel

from braid_triggers.aws_ops import boto3_resource
from braid_triggers.models import InternalTrigger
from braid_triggers.settings import get_settings

_triggers: dict[str, InternalTrigger] = {}
log = logging.getLogger(__name__)

_TRIGGER_KEY_SCHEMA = ({"AttributeName": "trigger_id", "KeyType": "HASH"},)
_TRIGGER_ATTRIBUTE_DEFINITIONS = (
    {"AttributeName": "trigger_id", "AttributeType": "S"},
)

settings = get_settings()


def create_table(
    table_name: str,
    key_schema: t.Iterable[t.Mapping[str, str]],
    attribute_definitions: t.Iterable[t.Mapping[str, str]],
    billing_mode="PAY_PER_REQUEST",
    **kwargs,
) -> DynamoTable:
    try:
        client = boto3_resource("dynamodb", DynamoDBServiceResource)
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=attribute_definitions,
            KeySchema=key_schema,
            BillingMode=billing_mode,
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
    client = boto3_resource("dynamodb", DynamoDBServiceResource)

    table: DynamoTable = client.Table(table_name)
    return table


T = t.TypeVar("T")


def _iterate_dict(
    val: t.Any | None, val_transformer: t.Callable[[t.Any], t.Any]
) -> t.Any | None:
    """Iterate over a nested (dict/list) structure, and call the transformer on any simple
    (non-dict/list) values

    """
    if isinstance(val, dict):
        val = {k: _iterate_dict(v, val_transformer) for k, v in val.items()}
    elif isinstance(val, list):
        val = [_iterate_dict(v, val_transformer) for v in val]
    else:
        val = val_transformer(val)
    return val


def _from_dynamo_dict(d: dict[str, t.Any]) -> dict[str, t.Any]:
    def dynamo_deserialize(val: t.Any) -> t.Any:
        if isinstance(val, Decimal):
            val = float(val)
            if int(val) == val:
                val = int(val)
        elif isinstance(val, Binary):
            val = val.value
        return val

    return _iterate_dict(d, dynamo_deserialize)


def _dict_to_dynamo_dict(d: dict[str, t.Any]) -> dict[str, t.Any]:
    def dynamo_serialize(val: t.Any) -> t.Any:
        if isinstance(val, numbers.Number):
            val = Decimal(val)
        elif isinstance(val, (bytes, bytearray)):
            val = Binary(val)
        elif val is not None:
            val = str(val)
        return val

    return _iterate_dict(d, dynamo_serialize)


def _pydantic_model_to_dynamo_dict(model: BaseModel) -> dict[str, t.Any]:
    return _dict_to_dynamo_dict(model.dict())


def lookup_by_key(inst_class: t.Type[T], table: DynamoTable, **kwargs) -> T | None:
    k, v = next(iter(kwargs.items()))
    response = table.query(KeyConditionExpression=Key(k).eq(v))
    items = response.get("Items")

    instance: T | None = None
    if len(items) > 0:
        try:
            item = _from_dynamo_dict(items[0])
            instance = inst_class(**item)
            return instance
        except Exception as e:
            log.error(f"Cannot create Trigger from {items[0]} got {str(e)}")
    return instance


QueryElement = t.Union[BaseModel, dict]


def query_for_class(
    inst_class: t.Type[T],
    table: DynamoTable,
    *,
    query_vals: QueryElement | t.Iterable[QueryElement] | None = None,
    **kwargs,
) -> list[T]:
    """Perform a scan of a dynamo table returning instances of the provided class. That
    class must take as constructor params the properties of the items returned from the
    scan.

    The values to be queried can be provided in a variety of ways: in query_vals, there
    can be a single instance of a dict or a pydantic BaseModel instance. If a list of
    these is provided, the scan will return values matching any of these.

    kwargs may also be provided for the query. If they are, they are treated as another
    element of the query_vals list and so will form another condition that may be
    matched.

    The only forms of matching provided are exact match against the values or a
    list/set/tuple of values. If a set of values is given, then the match for the
    property is the value being in the set.
    """
    filter_expression = None
    if query_vals is not None and not isinstance(query_vals, list):
        query_vals = [query_vals]
    if len(kwargs) > 0:
        if not query_vals:
            query_vals = [kwargs]
        else:
            query_vals.append(kwargs)
    for query_val in query_vals:
        this_filter_expression = None
        if not isinstance(query_val, dict):
            try:
                query_val = query_val.dict()
            except Exception as e:
                log.error(
                    f"Failed converting {query_val} via dict() due to {str(e)}, skipping..."
                )
                continue
        for k, v in query_val.items():
            if isinstance(v, (tuple, list, set)):
                this_attr = Attr(k).is_in(v)
            else:
                this_attr = Attr(k).eq(v)
            if this_filter_expression is None:
                this_filter_expression = this_attr
            else:
                this_filter_expression = this_filter_expression & this_attr

        if filter_expression is None:
            filter_expression = this_filter_expression
        else:
            filter_expression = filter_expression | this_filter_expression

    response = table.scan(FilterExpression=filter_expression)
    items = response.get("Items", [])
    instances: list[T] = []
    for item in items:
        instances.append(inst_class(**item))
    return instances


def lookup_trigger(trigger_id: str) -> InternalTrigger | None:
    table = get_table(
        settings.dynamo_table_name,
    )
    trigger = lookup_by_key(InternalTrigger, table, trigger_id=trigger_id)
    return trigger


def scan_triggers(
    query_vals: QueryElement | t.Iterable[QueryElement] | None = None, **kwargs
) -> list[InternalTrigger]:
    table = get_table(
        settings.dynamo_table_name,
    )
    return query_for_class(InternalTrigger, table, query_vals=query_vals, **kwargs)


def store_trigger(trigger: InternalTrigger) -> InternalTrigger:
    table = get_table(
        settings.dynamo_table_name,
    )
    if trigger.trigger_id is None:
        trigger.trigger_id = str(uuid.uuid4())
    trigger_dict = _pydantic_model_to_dynamo_dict(trigger)
    table.put_item(Item=trigger_dict)
    return trigger


def update_trigger(trigger: InternalTrigger) -> InternalTrigger:
    table = get_table(
        settings.dynamo_table_name,
    )
    if trigger.trigger_id is None:
        trigger.trigger_id = str(uuid.uuid4())
    trigger_dict = _pydantic_model_to_dynamo_dict(trigger)
    table.put_item(Item=trigger_dict)
    return trigger


def remove_trigger(trigger_id: str) -> InternalTrigger:
    table = get_table(
        settings.dynamo_table_name,
    )
    del_resp = table.delete_item(
        Key={
            "trigger_id": trigger_id,
        },
        ReturnValues="ALL_OLD",
    )
    item = del_resp.get("Attributes")
    item = _from_dynamo_dict(item)
    return InternalTrigger(**item)


def enum_triggers(**kwargs) -> list[InternalTrigger]:
    """
    This is probably really inefficient
    """
    table = get_table(
        settings.dynamo_table_name,
    )
    filter_expression = None
    for attr_name, val in kwargs.items():
        this_filter_expression = Attr(attr_name).eq(val)
        if filter_expression is None:
            filter_expression = this_filter_expression
        else:
            filter_expression = filter_expression & this_filter_expression
    try:
        response = table.scan(FilterExpression=filter_expression)
        items = response.get("Items", [])
        ret_items = [InternalTrigger(**_from_dynamo_dict(i)) for i in items]
    except Exception as e:
        log.warning(f"Scan on filter {filter_expression} returned error {e}, {type(e)}")
        ret_items = []
    return ret_items


def init_persistence() -> None:
    if settings.create_dynamo_table:
        create_table(
            table_name=settings.dynamo_table_name,
            key_schema=_TRIGGER_KEY_SCHEMA,
            attribute_definitions=_TRIGGER_ATTRIBUTE_DEFINITIONS,
        )
