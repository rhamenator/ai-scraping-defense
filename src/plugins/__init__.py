import importlib
import os
from typing import Callable, List

# Only load plugins that are explicitly allowed. This prevents arbitrary code
# execution if untrusted files are placed in the plugin directory.
ALLOWED_PLUGINS = os.getenv("ALLOWED_PLUGINS", "ua_blocker").split(",")

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
        if module_name not in ALLOWED_PLUGINS:
            continue
        path = os.path.join(PLUGIN_DIR, filename)
        if os.path.islink(path):
            continue
        try:
            module = importlib.import_module(f"plugins.{module_name}")
            func = getattr(module, "check", None)
            if callable(func):
                plugins.append(func)
        except Exception as e:  # pragma: no cover - unexpected
            import logging

            logging.error("Failed to load plugin %s: %s", filename, e)
    return plugins
