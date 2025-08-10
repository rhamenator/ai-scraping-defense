import importlib
import importlib.util
import os
import sys
from typing import Callable, List

# Only load plugins that are explicitly allowed. This prevents arbitrary code
# execution if untrusted files are placed in the plugin directory.
DEFAULT_ALLOWED_PLUGINS = os.getenv("ALLOWED_PLUGINS", "ua_blocker").split(",")

PLUGIN_DIR = os.getenv("PLUGIN_DIR", "/app/plugins")


def load_plugins(
    allowed_plugins: List[str] | None = None,
) -> List[Callable[[object], float]]:
    """Load plugin check functions from the plugins directory."""
    if allowed_plugins is None:
        allowed_plugins = DEFAULT_ALLOWED_PLUGINS
    plugins: List[Callable[[object], float]] = []
    if not os.path.isdir(PLUGIN_DIR):
        return plugins
    plugin_dir_real = os.path.realpath(PLUGIN_DIR)
    for filename in os.listdir(PLUGIN_DIR):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        module_name = filename[:-3]
        if module_name not in allowed_plugins:
            continue
        path = os.path.join(PLUGIN_DIR, filename)
        real_path = os.path.realpath(path)
        if (
            os.path.islink(path)
            or os.path.commonpath([plugin_dir_real, real_path]) != plugin_dir_real
        skip = False
        if os.path.islink(path):
            skip = True
        else:
            try:
                if os.path.commonpath([plugin_dir_real, real_path]) != plugin_dir_real:
                    skip = True
            except ValueError:
                skip = True
        if skip:
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{module_name}", real_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                func = getattr(module, "check", None)
                if callable(func):
                    plugins.append(func)
        except Exception as e:  # pragma: no cover - unexpected
            import logging

            logging.error("Failed to load plugin %s: %s", filename, e)
    return plugins
