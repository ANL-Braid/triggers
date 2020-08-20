import boto3


def create_table(dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.create_table(
        TableName='Triggers',
        KeySchema=[
            {
                'AttributeName': 'topic',
                'KeyType': 'HASH'  # Partition key
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'topic',
                'AttributeType': 'S'
            },
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        }
    )
    return table

def put_trigger(topic, info, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table('Triggers')
    response = table.put_item(
       Item={
            'topic': topic,
            'info': info
        }
    )
    return response

def get_trigger(topic, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table('Triggers')

    try:
        response = table.get_item(Key={'topic': topic})
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']


topic = 'arn:aws:sns:us-east-1:039706667969:myname2'
info = {"theta_ep": '123abc', 'local_ep': '456def'}

try:
    table = create_table()
    print(table)
except:
    print('table exists')
print('putting data')
res = put_trigger(topic, info)
print(res)
print('getting data')
res = get_trigger(topic)
print(res)