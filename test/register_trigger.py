import requests
import json

topic = "myname4"

flow_input = {
  "Exec1Input": {
      "tasks": [{
        "endpoint": '4b116d3c-1703-4f8f-9f6f-39921e5864df',
        "func": 'adeb9c55-c4c4-4e53-891b-5740482d4eab',
        "payload": {'name': 'bob'}
      }]
   }
}

config = {"flow_id": '4780da39-3e97-4bf7-91b8-0710b5154a4e',
           "access_token": 'Agp5ykyXg678G96PEmmYa2EP9r8P2ljeQbdE8343eq31wEl2WzTvC7Y63BmMw53mewmgDpgd4gGyouX47qnVCkBz8',}

payload = {'flow_input': flow_input,
           'config': config,
           "topic_name": topic,
           "filter": {"file_num": [{"numeric": [">", 5]}]}
           }

res = requests.post(url="http://0.0.0.0:8000/triggers/register", json=payload)
print(res.json())