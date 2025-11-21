import importlib
import importlib.util
import os
import sys
from pathlib import Path

from typing import Callable, List

# Only load plugins that are explicitly allowed. This prevents arbitrary code
# execution if untrusted files are placed in the plugin directory.
DEFAULT_ALLOWED_PLUGINS = os.getenv("ALLOWED_PLUGINS", "ua_blocker").split(",")

PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "/app/plugins"))


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def load_plugins(
    allowed_plugins: List[str] | None = None,
) -> List[Callable[[object], float]]:
    """Load plugin check functions from the plugins directory."""
    if allowed_plugins is None:
        allowed_plugins = DEFAULT_ALLOWED_PLUGINS
    plugins: List[Callable[[object], float]] = []
    if not PLUGIN_DIR.is_dir():
        return plugins
    base = PLUGIN_DIR.resolve()
    for entry in PLUGIN_DIR.iterdir():
        if entry.name.startswith("_") or entry.suffix != ".py" or not entry.is_file():
            continue
        module_name = entry.stem
        if module_name not in allowed_plugins:
            continue
        if entry.is_symlink() or not _is_within(base, entry):
            continue
        spec = importlib.util.spec_from_file_location(
            f"plugins.{module_name}", str(entry)
        )
        if not spec or not spec.loader:
            continue
        name = spec.name
        try:
            if name in sys.modules:
                del sys.modules[name]
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            func = getattr(module, "check", None)
            if callable(func):
                plugins.append(func)
        except Exception as e:  # pragma: no cover - unexpected
            sys.modules.pop(name, None)
            import logging

            logging.error("Failed to load plugin %s: %s", entry.name, e)
    return plugins
