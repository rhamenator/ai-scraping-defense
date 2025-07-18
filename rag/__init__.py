import importlib
import sys

# Map submodules from src.rag to the top-level rag package
_MODULES = [
    'training',
    'finetune',
    'train_markov_postgres',
    'email_entropy_scanner',
]

for _name in _MODULES:
    module = importlib.import_module(f'src.rag.{_name}')
    sys.modules[f'rag.{_name}'] = module
    globals()[_name] = module

__all__ = _MODULES
