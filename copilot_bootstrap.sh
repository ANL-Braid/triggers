#!/bin/bash

export AWS_PROFILE=globus-automate

copilot app init pseudo-triggers

copilot env init --name test --profile globus-automate --default-config

copilot svc init --name pseudo-triggers-api --svc-type "Load Balanced Web Service" --dockerfile ./Dockerfile

copilot storage init -n pseudo_trigger_triggers -t DynamoDB -s pseudo-triggers-api --partition-key trigger_id:S --no-sort --no-lsi

copilot svc deploy --name pseudo-triggers-api --env test

