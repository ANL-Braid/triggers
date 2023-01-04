#!/bin/bash

script_dir=$(dirname $0)


if [ -f docker_local.env ]; then
    source docker_local.env
fi

export AWS_ENDPOINT_URL
export AWS_DEFAULT_REGION
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export COPILOT_SERVICE_NAME
export COPILOT_ENVIRONMENT_NAME


if [ -f docker_local_secrets.env ]; then
    source docker_local_secrets.env
fi


export GLOBUS_AUTH_CLIENT_ID
export GLOBUS_AUTH_CLIENT_SECRET

${script_dir}/.venv/bin/uvicorn braid_triggers.trigger_main:app --host 0.0.0.0 --port 5001 --reload
