Prototype Trigger Service
=========================

Here is a little example Trigger Service that combines various AWS services to support registering triggers.
The goal of the trigger is to invoke an Automate flow in
response to data being published to a Globus Queues queue.

The prototype allows you to register a Trigger with the service. The service in turn creates a SNS topic
that filters messages based on a user-defined condition and invokes a Lambda function to process the event.
Static input data can be published with the Trigger and then stored in a DynamoDB database. These
static inputs are then retrieved when the trigger is fired and combined with the Queues message
as input to the specified Automate flow.

Note: Queues does not yet support eventing, so there is a manual step of
popping a task off a queue and pushing it to an SNS topic. This step could be automated with a cron job, or
solved by implementing the Queues callback functionality.

The Trigger service and scripts to use it are described below.

Service
-------

The service is a flask app with
a single `register_trigger` route.

Users can register a trigger by POSTing the following data to the service:
 - A set of static input to pass to a flow
 - The Flow ID to run when triggered
 - An access token to run the flow with
 - A SNS trigger condition used to filter Queues messages. These are described _here.
 - A name for the trigger (to name the SNS topic)

.. _here: https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html#example-filter-policies

Registering a new trigger causes the service to first create a new SNS topic for the trigger.
Permissions are then added to the SNS topic to allow it to invoke a Lambda function.
A subscription is then made between the SNS topic and the Lambda function, such
that new messages published to the topic will be processed by the function.
The trigger condition is then added to the SNS topic to filter messages.
Finally, the TopicARN is returned to the user.


Test Scripts
------------

The following scripts are in the `test` directory:
- create_queue.py
- create_dynamodb.py
- register_trigger.py
- push_queue.py
- pop_queue.py

create_queue.py:
  Before using the service you need to create a Globus Queues queue. Running this script should
  create a new queue, describe it, then send/receive/delete a message.

create_dynamodb.py:
  You need a dynamodb table to store the user's trigger info. This is key'd by the SNS topic so
  the Lambda function can retrieve it when invoked.

register_trigger.py
  This sends a POST request to the service to register a new trigger.

push_queue.py
  This puts a new message into the Queues queue.

pop_queue.py
  Because Queues doesn't support the callback address we need to manually pop messages off the queue
  and put them into the SNS topic. Running this after push_queue.py will trigger the trigger.

