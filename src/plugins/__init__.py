import importlib
import os
from typing import Callable, List

PLUGIN_DIR = os.getenv("PLUGIN_DIR", "/app/plugins")


def load_plugins() -> List[Callable[[object], float]]:
    """Load plugin check functions from the plugins directory."""
    plugins: List[Callable[[object], float]] = []
    if not os.path.isdir(PLUGIN_DIR):
        return plugins
    for filename in os.listdir(PLUGIN_DIR):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        module_name = filename[:-3]
        try:
            module = importlib.import_module(f"plugins.{module_name}")
            func = getattr(module, "check", None)
            if callable(func):
                plugins.append(func)
        except Exception as e:  # pragma: no cover - unexpected
            import logging
            logging.error("Failed to load plugin %s: %s", filename, e)
    return plugins
