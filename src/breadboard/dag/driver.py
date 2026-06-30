"""Build Hamilton drivers from configured module lists."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

if TYPE_CHECKING:
    from breadboard.config import CacheSpec

# Built-in DAG modules addressable by a short name in config. Every other
# section is loaded by its dotted `_import_path`, so user-defined modules are
# first-class and treated no differently from these built-ins.
MODULES: dict[str, str] = {
    "node": "breadboard.dag.node",
    "resample": "breadboard.dag.resample",
}


def build_driver(
    modules: list[str],
    config: dict[str, Any],
    allow_module_overrides: bool = False,
    cache: "CacheSpec | None" = None,
) -> driver.Driver:
    """Build a Hamilton driver from a list of module names and config.

    Parameters
    ----------
    modules
        List of module identifiers: a built-in short name ("node", "resample")
        or a dotted import path to a user module (e.g. "mypkg.mymodel").
    config
        Configuration dict passed to the Hamilton driver.
    allow_module_overrides
        If True, allow later modules to override earlier ones.
    cache
        If provided, enable Hamilton result caching according to this spec.

    Returns
    -------
    driver.Driver
        A configured Hamilton driver ready for execution.
    """
    config[ENABLE_POWER_USER_MODE] = True

    from breadboard.dag.node import make_node_module

    modules_ = []
    for mod in modules:
        if mod == "node":
            modules_.append(make_node_module(config.get("node_specs", [])))
        elif mod in MODULES:
            modules_.append(import_module(MODULES[mod]))
        else:
            try:
                modules_.append(import_module(mod))
            except ModuleNotFoundError as exc:
                raise ValueError(
                    f"Cannot load module '{mod}': not a known breadboard module "
                    f"and not importable as a Python module."
                ) from exc

    dr = driver.Builder().with_modules(*modules_).with_config(config)

    if allow_module_overrides:
        dr = dr.allow_module_overrides()

    if cache is not None:
        from breadboard.dag.caching import apply_cache

        dr = apply_cache(dr, cache)

    built = dr.build()

    # Build-time unit-consistency check; a no-op in "off" mode (the conftest
    # default), so this does not affect builds that opt out of unit handling.
    from breadboard.dag.unit_check import check_dag_units

    check_dag_units(built)

    return built
