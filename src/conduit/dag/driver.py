"""Build Hamilton drivers from configured module lists."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

if TYPE_CHECKING:
    from conduit.specs import CacheSpec, NodeSpec

# Built-in DAG module addressable by a short name in config. Every other section
# is loaded by its dotted `_import_path`, so user-defined modules are first-class
# and treated no differently. ("node" is handled specially in build_driver, which
# generates it from the config's node_specs; [[resample]] desugars to node specs.)
MODULES: dict[str, str] = {
    "node": "conduit.dag.node",
}


def build_driver(
    modules: list[str],
    config: dict[str, Any],
    allow_module_overrides: bool = False,
    cache: "CacheSpec | None" = None,
    node_specs: "list[NodeSpec] | None" = None,
) -> driver.Driver:
    """Build a Hamilton driver from a list of module names and config.

    Parameters
    ----------
    modules
        List of module identifiers: the built-in short name "node" or a dotted
        import path to a user module (e.g. "mypkg.mymodel").
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

    Returns
    -------
    driver.Driver
        A configured Hamilton driver ready for execution.
    """
    config = dict(config)
    config[ENABLE_POWER_USER_MODE] = True

    from conduit.dag.node import make_node_module

    if "node" in modules and not node_specs:
        raise ValueError(
            "The built-in 'node' module was requested but no node_specs were "
            "given, so it would generate no nodes. Pass "
            "node_specs=parsed.node_specs."
        )

    modules_ = []
    for mod in modules:
        if mod == "node":
            modules_.append(make_node_module(node_specs or []))
        elif mod in MODULES:
            modules_.append(import_module(MODULES[mod]))
        else:
            try:
                modules_.append(import_module(mod))
            except ModuleNotFoundError as exc:
                raise ValueError(
                    f"Cannot load module '{mod}': not a known conduit module "
                    f"and not importable as a Python module."
                ) from exc

    dr = driver.Builder().with_modules(*modules_).with_config(config)

    if allow_module_overrides:
        dr = dr.allow_module_overrides()

    if cache is not None:
        from conduit.dag.caching import apply_cache

        dr = apply_cache(dr, cache)

    built = dr.build()

    # Build-time contract-consistency check (units + dims/dtype); a no-op in
    # "off" mode (the conftest default), so this does not affect builds that opt
    # out of contract handling.
    from conduit.dag.contract_check import check_dag_contracts

    check_dag_contracts(built)

    return built
