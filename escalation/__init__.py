import importlib
import sys

# Map submodules from src.escalation to the top-level escalation package
_MODULES = [
    "escalation_engine",
]

for _name in _MODULES:
    module = importlib.import_module(f"src.escalation.{_name}")
    sys.modules[f"escalation.{_name}"] = module
    globals()[_name] = module

__all__ = _MODULES
