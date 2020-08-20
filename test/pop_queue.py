import time
import json
import uuid
import requests
import boto3

from globus_sdk import AuthClient
from fair_research_login import NativeClient, JSONTokenStorage


TOKEN_FILENAME = 'globus_queues.json'
SCOPES = ['https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/admin',
          'https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/send',
          'https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/receive']
CLIENT_ID = '4cf29807-cf21-49ec-9443-ff9a3fb9f81c'


native_client = NativeClient(client_id=CLIENT_ID,
                                          app_name="queues client",
                                          token_storage=JSONTokenStorage(TOKEN_FILENAME))

native_client.login(requested_scopes=SCOPES,
                                     no_local_server=True,
                                     no_browser=True,
                                     refresh_tokens=True,
                                     force=False)

all_authorizers = native_client.get_authorizers_by_scope(requested_scopes=SCOPES)
print(all_authorizers)
admin_authorizer = all_authorizers['https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/admin']
send_authorizer = all_authorizers['https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/send']
receive_authorizer = all_authorizers['https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/receive']

admin_token = admin_authorizer.access_token
send_token = send_authorizer.access_token
receive_token = receive_authorizer.access_token

adminheaders = {"Authorization": f"Bearer {admin_token}"}
sendheaders = {"Authorization": f"Bearer {send_token}"}
receiveheaders = {"Authorization": f"Bearer {receive_token}"}


def create_queue(headers):
    url = 'https://queues.api.globus.org/v1/queues'

    input = {
        "data": {
            "label": "my-test-queue",
            "delivery_timeout": 60,
            "admins": [
                "urn:globus:auth:identity:c4765424-d274-11e5-b894-cb4139f74ecf"
            ],
            "senders": [
                "urn:globus:auth:identity:c4765424-d274-11e5-b894-cb4139f74ecf"
            ],
            "receivers": [
                "urn:globus:auth:identity:c4765424-d274-11e5-b894-cb4139f74ecf"
            ],
            "receiver_url": "https://example.com/notify",
            "receiver_scope": "urn:globus:auth:scope:whatever:all"
        }
    }

    res = requests.post(url, headers=headers, json=input)
    print(res.json())
    return res.json()['id']


def receive_message(queue, headers):
    url = f"https://queues.api.globus.org/v1/queues/{queue}/messages"

    res = requests.get(url, headers=headers)
    return res.json()


def delete_message(recpt, queue, headers):
    input = {
                "data": [
                    {
                        "receipt_handle": recpt
                    }
                ]
            }

    res = requests.delete(url=f"https://queues.api.globus.org/v1/queues/{queue}/messages",
                          headers=headers, json=input)
    if res.status_code == 204:
        return 'done'
    return res


def create_attributes(data):
    attrs = {}
    for k, v in data.items():
        dt = "String"
        if type(v) in [int, float]:
            dt = "Number"
        if type(v) == list:
            dt = "String.Array"

        attrs[k] = {
            'DataType': dt,
            'StringValue': str(v),
        }
    return attrs


def push_sns(filename, topic_arn='arn:aws:sns:us-east-1:039706667969:myname2'):
    client = boto3.client('sns')
    event = json.loads(filename)
    message = {'event': event}
    attrs = create_attributes(event)
    print(attrs)
    print(message)
    response = client.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        MessageAttributes=attrs,
        Subject='test',
    )



# queue = create_queue(adminheaders)
queue = "73f1dd7c-63e2-4048-b589-116465c547e3"

print("Receiving message")
res = receive_message(queue, receiveheaders)
print(res)
filename = res['data'][0]['message_body']
receipt_handle = res['data'][0]['receipt_handle']
print(filename)

import sys
topic_arn = sys.argv[1]
push_sns(filename, topic_arn)


print("deleting message")
res = delete_message(receipt_handle, queue, receiveheaders)
print(res)