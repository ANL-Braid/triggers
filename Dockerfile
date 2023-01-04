FROM python:3.10-slim-buster

ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV PYTHONBREAKPOINT=0

RUN mkdir /braid-triggers

WORKDIR /braid-triggers

COPY ./ ./

RUN python3 -m pip install poetry

RUN pip install poetry==1.2

RUN \
    set -eu; \
    poetry install --only main; \
    poetry cache clear --all --no-interaction pypi;

EXPOSE 5001

CMD ["/braid-triggers/.venv/bin/uvicorn", "braid_triggers.trigger_main:app", "--host", "0.0.0.0", "--port", "5001"]
