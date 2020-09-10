Pseudo Trigger Service
======================

Here's a little example of what a Trigger Service might do. It allows one to create a trigger which will pull events from a Globus Queue, filter the event content to see if it meets criteria for firing, and then will invoke an action (including a Flow) with a body which may be built from the content of the Event.

Getting Started
---------------

After cloning this repo, first run: ``poetry install``. (if you don't have poetry installed, go do that first).

This should create a virtualenv (.venv) in the current directory.

This will create the service, but it also will install a command line tool which will be installed into the virtual environment. It can be invoked via either ``poetry run pseudo-trigger`` or by invoking it within the virtual environment as in ``.venv/bin/pseudo-trigger`` (I prefer the latter).

As we are in rapid development phase, there's no set DNS name for the service. Thus, you need to pass the URL for the trigger service into the CLI tool via the environment variable: ``PSEUDO_TRIGGER_URL``. 

At time of writing the full value for this should be:

``PSEUDO_TRIGGER_URL="http://pseud-Publi-11PYV3L9WQ22M-382926136.us-east-1.elb.amazonaws.com/triggers"``

So, one can invoke the tool as:

``PSEUDO_TRIGGER_URL="http://pseud-Publi-11PYV3L9WQ22M-382926136.us-east-1.elb.amazonaws.com/triggers" .venv/bin/pseudo-trigger``


For the rest of this doc, we'll assume this setup for all invocations of the CLI tool, and simply write ``pseudo-trigger``.

Creating and testing a Trigger
------------------------------

Before we can usefully create a Trigger, we first need to create a Queue in the Globus Queues service to send messages on. This can be done via:

``globus-automate queue create --label trigger-test --admin urn:globus:auth:identity:<my_auth_identity> --sender urn:globus:auth:identity:<my_auth_identity> --receiver urn:globus:auth:identity:<my_auth_identity>``

where ``<my_auth_identity>`` is replaced with your Globus Auth identity which can be retrieved via:

``globus session show``

Take note of the ``id`` field in the output for latter use. We'll refer to it as ``<queue_id>`` else where.

Now, we create a Trigger which will listen on this Queue via:

``pseudo-trigger trigger create --action-url https://actions.globus.org/hello_world --event-filter True --event-template '{"echo_string": "From Trigger"}' --queue-id <queue_id>``

There are four key pieces of information here:

1. The URL of the Action to invoke in response to events/messages. This should be the base URL of an Action or of a Flow, and it must follow the Action API spec to publish its required scope via the introspection API call (all Globus operated Actions as well as all Flows do so).

2. An Event Filter expression which will be evaluated against each incoming event to determine if the action should be invoked. This Event Filter must evaluate to a boolean value (python-like truthiness is not good enough (that's a general statement but it applies specifically here)). More on writing expressions on event content below. 

3. A Template, in JSON format (sorry no reading from file support yet), of the body which will be passed to the Actin/Flow when invoking it. This follows a format very similar to the ``Parameters`` block of a Globus Flows Action state. A simple value within the JSON will be passed as is. If the property name ends with ``.=`` it will be evaluated as an expression (still getting to that point where we can tell you about expressions).

4. The id of the queue to listen on.

To write expressions in either the Event Filter or the Event Template, one can write typical sorts of string or arithmetic expressions. To access fields of the Event, simply name the field from the Event structure you with to use. The fields are:

*    ``body: Dict[str, Any]``  -- more on the body below

*    ``event_id: str``

*    ``sent_by_effective_identity: str``

*    ``timestamp: str``

*    ``sent_by_app: Optional[str] = None``

*    ``sent_by_identity_set: Optional[List[str]] = None``

The additional field ``event_count: int`` is added indicating the number of messages which have been retrieved by the trigger to this point.

As Globus Queues messages are by default simply strings, we provide a helper to convert JSON formatted messages into fields. Thus, if the content of the message were say:

``{"Hello": "World"}``

The value within the expression ``body.Hello`` would have the value ``"World"``.

If the content of the message does not parse as JSON, the entire content is provided under the field name ``message`` which makes it available in an expression as ``body.message``.

Upon creation of the Trigger, the Trigger will be in the "PENDING" state. That state indicates that it is exists in the system, but it is not monitoring the queue. To do this, we must *enable* the Trigger. We do this with:

``pseudo-trigger enable <trigger-id>`` where the value for ``<trigger-id>`` is shown (as field name ``trigger_id``) in the output from the trigger ``create`` call.

Upon enabling the trigger, the trigger service will require that you consent to having it read messages from the Queue and invoke the Action. So, a browser Globus Auth consent is likely to pop up here. The trigger service will be caching the tokens created here and refreshing them as needed (not quite there yet...).

The result from running enable should be the same state of the Trigger with the state now set to ``ENABLED``.

We can now send messages to the Queue and thus to the trigger:

``globus-automate queue send --message '{"Hello": "World"}' <queue_id>``

There's no immediate feedback that anything happened here, but the Trigger is monitoring the queue and will, assuming the filter evaluated to True, invoke the Action.

We can check to see if this occurred by running:

``pseudo-trigger trigger display <trigger-id>``

The output should now be more verbose than the output of previous trigger operations. In particular, the fields ``last_action_status``, ``last_event`` and ``event_count`` should now have content letting us know what the Trigger has been up to most recently.

Service
-------

Some notes on the service:

1. The Trigger service is built on FastAPI and it makes (extensive) use of the Python asyncio capability which is supported by FastAPI. This is intended to make the service both scaleable (asyncio is notable for being light on resource usage) and responsive (no single Trigger or Action should block others from making solid progress).

2. When a Trigger is enabled, an asyncio task is created for monitoring the Queue associated with the trigger. This task will stay alive as long as the Trigger is in the ``ENABLED`` state or when the Trigger still has Actions running. The loop for this task will monitor both the Queue and any Actions which are still outstanding. It will also release actions when they are complete. 

3. Only one Trigger can (reliably) listen on a Queue at a time (not enforced right now). If multiple Triggers have the same Queue id, they will compete for messages (presumably). It would be desirable to allow for multiple Triggers to listen to the same Queue and for each to receive each message. This would allow for effective fan out of messages from Queues.

4. Counter-part to the previous point, one could imagine a single Trigger that listens on multiple Queues and waits until some joint condition is met to fire the Action. Defining such joint conditions is probably non-trivial.

5. The service is presently deployed to AWS Fargate/ECS. The ``copilot`` command line tool is used for setting up and managing all environments. The commands to do this are in the file copilot_bootstrap.sh if anyone should be interested. This includes setting up the DynamoDB table used for tracking the Triggers.
