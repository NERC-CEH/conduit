"""Build Hamilton drivers from configured module lists."""

from importlib import import_module
from pathlib import Path
from typing import Any

from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

from .errors import ConduitValueError
from .importing import import_user_module
from .specs import CacheSpec, NodeSpec

# Built-in DAG module addressable by a short name in config. Every other section
# is loaded by its `_import_path` (see `conduit.importing`), so user-defined modules
# are first-class and treated no differently. ("node" is handled specially in
# build_driver, which generates it from node_specs; [[resample]] desugars to those.)
MODULES: dict[str, str] = {
    "node": "conduit.nodegen",
}


def build_driver(
    modules: list[str],
    config: dict[str, Any],
    allow_module_overrides: bool = False,
    cache: CacheSpec | None = None,
    node_specs: list[NodeSpec] | None = None,
    base: Path | None = None,
) -> driver.Driver:
    """Build a Hamilton driver from a list of module names and config.

    Parameters
    ----------
    modules
        List of module identifiers: the built-in short name "node", a dotted
        import path to an installed module (e.g. "mypkg.mymodel"), or a path to a
        .py file (e.g. "nodes.py").
    config
        Configuration dict passed to the Hamilton driver. Copied, not mutated.
    allow_module_overrides
        If True, allow later modules to override earlier ones.
    cache
        If provided, enable Hamilton result caching according to this spec.
    node_specs
        The `[[node]]` specs to generate the built-in "node" module from
        (`conduit.config.ParsedConfig.node_specs`). Required whenever "node"
        appears in ``modules``.
    base
        The directory a relative .py path in ``modules`` resolves against, normally
        the one holding the config (`conduit.specs.ParsedConfig.base`).

    Returns
    -------
    driver.Driver
        A configured Hamilton driver ready for execution.
    """
    config = dict(config)
    config[ENABLE_POWER_USER_MODE] = True

    from .nodegen import make_node_module

    if "node" in modules and not node_specs:
        raise ConduitValueError(
            "The built-in 'node' module was requested but no node_specs were "
            "given, so it would generate no nodes. Pass "
            "node_specs=parsed.node_specs."
        )

    modules_ = []
    for mod in modules:
        if mod == "node":
            modules_.append(make_node_module(node_specs or [], base))
        elif mod in MODULES:
            modules_.append(import_module(MODULES[mod]))
        else:
            modules_.append(import_user_module(mod, base))

    dr = driver.Builder().with_modules(*modules_).with_config(config)

    if allow_module_overrides:
        dr = dr.allow_module_overrides()

    if cache is not None:
        from .caching import apply_cache

        dr = apply_cache(dr, cache)

    built = dr.build()

    # The flagship guarantee: every declared contract on the whole DAG is checked
    # here, before any compute. A no-op when the policy is "off", so pipelines that
    # opt out of contract handling are unaffected.
    from .contract_check import check_dag_contracts

    check_dag_contracts(built)

    return built
