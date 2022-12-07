#!/bin/bash

script_dir=$(dirname $0)

GLOBUS_AUTH_CLIENT_ID="9b54c03e-30be-43e7-8b5d-133f94930837" \
    GLOBUS_AUTH_CLIENT_SECRET="NDms9sZ5H5v5waFtkyKHPUUQkgrH1RsXpR1jg+3DxyU=" \
    ${script_dir}/.venv/bin/uvicorn braid_triggers.trigger_main:app --host 0.0.0.0 --port 5001 --reload
