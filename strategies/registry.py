"""
Auto-discovery: scans this package for Strategy subclasses and instantiates
them with weights from weights.json. Adding a new strategy = drop a .py file
in this directory defining a Strategy subclass with a unique `name`, and add
its weight to weights.json. Nothing else changes -- main.py never needs edits.
"""

import importlib
import inspect
import json
import os
import pkgutil
import logging

from .base import Strategy

logger = logging.getLogger("strategy_registry")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEIGHTS_PATH = os.path.join(_PROJECT_ROOT, "weights.json")

_SKIP_MODULES = {"base", "registry", "__init__"}


def load_weights_config() -> dict:
    with open(_WEIGHTS_PATH) as f:
        return json.load(f)


def discover_strategies() -> list:
    """Returns a list of INSTANTIATED strategy objects, weight-injected from weights.json."""
    weights_config = load_weights_config()
    module_weights = weights_config.get("strategies", {})

    package_dir = os.path.dirname(os.path.abspath(__file__))
    package_name = __name__.rsplit(".", 1)[0]  # "strategies"

    strategies = []
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        if module_name in _SKIP_MODULES:
            continue
        full_module_name = f"{package_name}.{module_name}"
        module = importlib.import_module(full_module_name)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Strategy) and obj is not Strategy and obj.__module__ == full_module_name:
                weight = module_weights.get(obj.name)
                if weight is None:
                    logger.warning(f"No weight configured for strategy '{obj.name}' in weights.json -- skipping")
                    continue
                strategies.append(obj(weight=weight))

    return strategies