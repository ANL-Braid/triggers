import time
import json
import uuid
import requests

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


    print(headers)
    res = requests.post(url, headers=headers, json=input)
    print(res)
    print(res.text)
    print(res.json())
    return res.json()['id']


def send_message(queue, headers, num=1):
    url = f"https://queues.api.globus.org/v1/queues/{queue}/messages"
    fn = str(uuid.uuid4())
    input = {
      "data": [
        {
          "deduplication_id": fn,
          "message_attributes": {},
          "message_body": json.dumps({"filename": f"MY_FILE_{num}.cbf",
                                      "file_num": int(num)})
        }
      ]
    }
    res = requests.post(url, headers=headers, json=input)
    return res.json()


queue = "73f1dd7c-63e2-4048-b589-116465c547e3"

import sys
num = sys.argv[1]

msg = send_message(queue, sendheaders, num=num)
print(msg)
msg_id = msg['data'][0]['message_id']
print(msg_id)
