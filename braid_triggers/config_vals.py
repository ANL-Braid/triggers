import os


def getenv_from_alternatives(
    *args, default: str | None = None, set_alias: str | None = None
) -> str | None:
    rval = default
    for arg in args:
        env_val = os.getenv(arg)
        if env_val is not None:
            rval = env_val
            break
    if rval is not None and set_alias is not None and os.getenv(set_alias) is None:
        os.environ[set_alias] = rval
    return rval


SERVICE_NAME = getenv_from_alternatives(
    "SERVICE_NAME", "COPILOT_SERVICE_NAME", default="triggers"
)

SERVICE_ENVIRONMENT = getenv_from_alternatives(
    "SERVICE_ENVIRONMENT",
    "GLOBUS_SDK_ENVIRONMENT",
    "COPILOT_ENVIRONMENT_NAME",
    default="localtest",
)

__version__ = "0.1.0"
