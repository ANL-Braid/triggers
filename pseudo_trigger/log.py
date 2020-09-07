import logging
import sys
import uuid

from starlette_context import context

from pseudo_trigger.config import get_config_val


async def set_debug_id(request, call_next):
    context.debug_id = str(uuid.uuid4())
    response = await call_next(request)
    return response


class Formatter(logging.Formatter):
    def __init__(self, *args, http=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = http

    def format(self, record):
        msg = super().format(record)
        if self.http:
            if getattr(context, "debug_id", None):
                msg += f" debug_id={context.debug_id}"
            user_id = getattr(context, "user_id", None)
            msg += f" user_id={user_id}"
        return msg


def setup_python_logging(log: logging.Logger, http: bool = False):
    log_level = logging.INFO
    if get_config_val("log.debug") is True:
        log_level = logging.DEBUG
    log.setLevel(log_level)
    log_file = get_config_val("log.file")
    if log_file is not None:
        handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler(sys.stdout)
    log_formater = "{asctime} {levelname:7} ({name}:{lineno}) {message}"
    date_formatter = "%Y-%m-%dT%H:%M:%S%z"
    handler.setFormatter(
        Formatter(fmt=log_formater, datefmt=date_formatter, style="{", http=http)
    )
    log.addHandler(handler)
