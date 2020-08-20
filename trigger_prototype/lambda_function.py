import json
import boto3
import botocore.vendored.requests as requests

def lambda_handler(event, context):

    message = event['Records'][0]['Sns']['Message']
    print(event['Records'][0])
    
    topic_arn = event['Records'][0]['Sns']['TopicArn']
    print(topic_arn)
    trigger_input = get_trigger(topic_arn)
    print(trigger_input)
    
    event_input = json.loads(message)['event']
    print(event_input)
    flow_input = trigger_input['info']['flow_input']
    flow_input.update(event_input)
    
    print(flow_input)

    res = run_flow(flow_input, trigger_input['info']['config']['flow_id'], 
                   trigger_input['info']['config']['access_token'])
    print(res)
    
    return res
    
def run_flow(flow_input, flow_id, access_token):
    """Start the Automate flow"""
    url = "https://flows.globus.org"
    
    payload = {'body': flow_input}
    
    headers = {'Authorization': f'Bearer {access_token}'}
    res = requests.post(url=f"{url}/{flow_id}/run", 
                        headers=headers, json=payload)
    return res.json()

    
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

