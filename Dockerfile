FROM python:3.8-slim-buster

RUN mkdir /pseudo-trigger

WORKDIR /pseudo-trigger

COPY ./ ./

RUN apt-get update -y && \
    pip install poetry

RUN poetry install --no-dev

EXPOSE 5001

CMD ["/pseudo-trigger/.venv/bin/uvicorn", "pseudo_trigger.trigger_views:app", "--host", "0.0.0.0", "--port", "5001"]
