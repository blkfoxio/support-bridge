# Import schema extensions so drf-spectacular discovers them
try:
    from . import schema  # noqa: F401
except ImportError:
    pass
