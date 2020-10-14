#!/bin/bash

export AWS_PROFILE=globus-automate

copilot app init --domain automate.globuscs.info triggers

copilot env init --name test --profile globus-automate --default-config

copilot svc init --name triggers-api --svc-type "Load Balanced Web Service" --dockerfile ./Dockerfile

copilot storage init -n pseudo_trigger_triggers -t DynamoDB -s triggers-api --partition-key trigger_id:S --no-sort --no-lsi

copilot svc deploy --name triggers-api --env test
