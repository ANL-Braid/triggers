#!/bin/bash

script_dir=$(dirname $0)

${script_dir}/.venv/bin/uvicorn pseudo_trigger.trigger_main:app --host 0.0.0.0 --port 5001 --reload
