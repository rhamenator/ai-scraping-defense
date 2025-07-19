import importlib
import sys

# Map submodules from src.rag to the top-level rag package
_MODULES = [
    'training',
    'finetune',
    'email_entropy_scanner',
]

# Expose the Rust extension if available
_markov_rs = None
try:
    _markov_rs = importlib.import_module('markov_train_rs')
    sys.modules['rag.markov_train_rs'] = _markov_rs
    globals()['markov_train_rs'] = _markov_rs
    _MODULES.append('markov_train_rs')
except ImportError:
    pass

for _name in _MODULES:
    if _name == 'markov_train_rs':
        module = _markov_rs
    else:
        module = importlib.import_module(f'src.rag.{_name}')
    sys.modules[f'rag.{_name}'] = module
    globals()[_name] = module

__all__ = _MODULES
