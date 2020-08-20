import boto3
import argparse
import json

from flask import Flask, current_app as app, jsonify, request, abort, g

app = Flask(__name__)

LAMBDA_ARN = 'arn:aws:lambda:us-east-1:039706667969:function:trigger_function_2'


@app.route('/ping', methods=['GET'])
def ping():
    """ Minimal liveness response
    """
    return "pong"


def create_topic(client, name='myname'):
    res = client.create_topic(Name=name)
    # res = {'TopicArn': 'arn:aws:sns:us-east-1:039706667969:myname2',
    #        'ResponseMetadata': {'RequestId': '2ccd7f9b-29ad-54c5-b660-282ece37831c',
    #                             'HTTPStatusCode': 200,
    #                             'HTTPHeaders': {'x-amzn-requestid': '2ccd7f9b-29ad-54c5-b660-282ece37831c',
    #                                             'content-type': 'text/xml', 'content-length': '313',
    #                                             'date': 'Tue, 18 Aug 2020 14:27:38 GMT'},
    #                             'RetryAttempts': 0}
    #        }
    print(res)
    return res


def add_permission(topic_arn, lambda_arn):
    import uuid
    response = boto3.client('lambda').add_permission(
        FunctionName=lambda_arn,
        StatementId=str(uuid.uuid4()),
        Action='lambda:InvokeFunction',
        Principal='sns.amazonaws.com',
        SourceArn=topic_arn,
    )
    return response

def create_subscription(client, topic_arn, lambda_arn, filter):
    try:
        subscription = client.subscribe(TopicArn=topic_arn,
                                        Protocol='lambda',
                                        Endpoint=lambda_arn,
                                        ReturnSubscriptionArn=True)

        # now set the filter policy
        response = client.set_subscription_attributes(
            SubscriptionArn=subscription['SubscriptionArn'],
            AttributeName='FilterPolicy',
            AttributeValue=json.dumps(filter)
        )

    except Exception as e:
        print(e)
    return response

def put_trigger(topic, info, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table('Triggers')
    try:
        response = table.delete_item(
            Key={
                'topic': topic
            }
        )
        response = table.put_item(
           Item={
                'topic': topic,
                'info': info
            }
        )
    except Exception as e:
        print(e)

    return response


@app.route('/triggers/register', methods=['POST'])
def register_trigger():
    """Return the serialized inputs
    """
    inputs = request.json
    payload = {'flow_input': inputs['flow_input'],
               'config': inputs['config']}
    ret_package = {'status': 'success'}
    try:
        client = boto3.client('sns')
        topic = create_topic(client, name=inputs['topic_name'])
        sns_arn = topic['TopicArn']
        perms = add_permission(sns_arn, LAMBDA_ARN)
        sub = create_subscription(client, sns_arn, LAMBDA_ARN, inputs['filter'])

        # now fire the metadata into the db under the topic_arn
        put_trigger(sns_arn, payload)
        ret_package['topic_arn'] = topic['TopicArn']
    except Exception as e:
        return jsonify(ret_package), 500
    return jsonify(ret_package), 200

@app.route('/test', methods=['GET'])
def test():
    """Return the serialized inputs
    """
    inputs = {'input': 'blob'}

    ret_package = {'status': 'success'}
    try:
        client = boto3.client('sns')
        print('test')
    except Exception as e:
        return jsonify(ret_package), 500
    return jsonify(ret_package), 200


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default=8000,
                        help="Port at which the service will listen on")
    parser.add_argument("-d", "--debug", action='store_true',
                        help="Enables debug logging")

    args = parser.parse_args()

    try:
        app.run(host='0.0.0.0', port=int(args.port), threaded=True)
    except Exception as e:
        # This doesn't do anything
        print("Caught exception : {}".format(e))
        exit(-1)


if __name__ == '__main__':
    cli()
