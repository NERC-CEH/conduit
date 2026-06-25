"""Configuration generator for SatTerC.

This module contains the logic for generating configuration files
by introspecting the Hamilton driver and discovering required inputs.
"""

import inspect
from importlib import import_module
from types import ModuleType
from typing import Any

import xarray as xr
from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

from .. import dag as dag_modules
from ..config import Config
from ..units import unwrap_annotated


def _analyze_model_module(
    module: ModuleType, config: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    """Analyze a model module to discover its inputs and outputs.

    Parameters
    ----------
    module : ModuleType
        A Hamilton module (e.g., models.splash).
    config : dict[str, Any]
        Configuration dict with model parameters.

    Returns
    -------
    tuple
        A tuple containing three lists of strings:
        - 'data_inputs': list of external inputs of type xarray.DataArray
        - 'non_data_inputs': list of config inputs (not DataArray type)
        - 'data_outputs': list of produced outputs of type xarray.DataArray
    """
    dr = driver.Builder().with_modules(module).with_config(config).build()
    all_vars = dr.list_available_variables()

    data_inputs = []
    data_outputs = []
    non_data_inputs = []

    for v in all_vars:
        # Signature-native unit declarations make some node types
        # ``Annotated[DataArray, "<unit>"]``; unwrap so they still count as data.
        v_type = unwrap_annotated(v.type)
        if v.is_external_input:
            if v_type == xr.DataArray:
                data_inputs.append(v.name)
            else:
                non_data_inputs.append(v.name)
        else:
            if v_type == xr.DataArray:
                data_outputs.append(v.name)

    return data_inputs, non_data_inputs, data_outputs


def _strip_suffix(name: str) -> tuple[str, str | None]:
    """Strip frequency suffix from variable name.

    Parameters
    ----------
    name : str
        Variable name (e.g., 'temperature_daily').

    Returns
    -------
    tuple
        (base_name, frequency) or (name, None) if no suffix found.
    """
    for suffix in ("_daily", "_weekly", "_monthly", "_static"):
        if name.endswith(suffix):
            return name[: -len(suffix)], suffix
    return name, None


def get_builtin_models() -> list[str]:
    """Get list of builtin models."""
    from ..setup_utils import BuiltinModels

    return [m.value for m in BuiltinModels]


def get_model_params(model_name: str) -> dict[str, Any]:
    """Extract keyword-only parameters with defaults from the main model function."""
    builtin_models = get_builtin_models()
    module_path = (
        f"satterc.dag.{model_name}" if model_name in builtin_models else model_name
    )

    try:
        module = import_module(module_path)
    except ImportError:
        return {}

    func_name = model_name.split(".")[-1]
    if hasattr(module, func_name):
        func = getattr(module, func_name)
        sig = inspect.signature(func)
        return {
            p.name: p.default
            for p in sig.parameters.values()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
            and p.default is not inspect.Parameter.empty
        }
    return {}


def _infer_required_data(model_names: list[str]) -> dict[str, list[str]]:
    """Infer required data using analyze_model_module.

    Uses data_inputs from each model to construct input lists,
    filters out model outputs, and determines resample lists.
    """
    base_config = {ENABLE_POWER_USER_MODE: True}

    # Collect all model inputs and outputs
    all_data_inputs: set[str] = set()
    model_output_bases: set[str] = set()
    all_model_outputs: list[str] = []

    for model_name in model_names:
        module = getattr(dag_modules, model_name)
        data_inputs, _, data_outputs = _analyze_model_module(module, base_config)

        # Store full input names (with suffix) for categorization
        all_data_inputs.update(data_inputs)
        all_model_outputs.extend(data_outputs)

        # Track base names of model outputs
        for output in data_outputs:
            base, _ = _strip_suffix(output)
            model_output_bases.add(base)

    # Filter out inputs that are model outputs (compare bases)
    # Also filter out grid variables (provided by the grid module, not from files)
    grid_vars = {"latitude", "longitude"}

    inputs_to_keep: set[str] = set()
    for name in all_data_inputs:
        base, freq = _strip_suffix(name)
        if base not in model_output_bases and base not in grid_vars:
            inputs_to_keep.add(name)

    # Categorize inputs by frequency
    daily: set[str] = set()
    weekly: set[str] = set()
    monthly: set[str] = set()
    static: set[str] = set()

    for name in inputs_to_keep:
        base, freq = _strip_suffix(name)
        if freq == "_daily":
            daily.add(base)
        elif freq == "_weekly":
            weekly.add(base)
        elif freq == "_monthly":
            monthly.add(base)
        else:
            static.add(base)

    # Variables available at a finer frequency are resampled rather than loaded
    # from the coarser file. Priority: daily → weekly → monthly.
    resample_daily_to_weekly = daily & weekly
    resample_weekly_to_monthly = weekly & monthly
    resample_daily_to_monthly = (
        daily & monthly
    ) - weekly  # direct hop; no weekly intermediate

    inputs_daily = daily
    inputs_weekly = weekly - resample_daily_to_weekly - resample_weekly_to_monthly
    inputs_monthly = monthly - resample_daily_to_monthly - resample_weekly_to_monthly

    # Categorize model outputs for output file lists
    outputs_daily: list[str] = []
    outputs_weekly: list[str] = []
    outputs_monthly: list[str] = []

    for output in all_model_outputs:
        base, freq = _strip_suffix(output)
        if freq == "_daily":
            outputs_daily.append(base)
        elif freq == "_weekly":
            outputs_weekly.append(base)
        elif freq == "_monthly":
            outputs_monthly.append(base)

    return {
        "inputs_daily": sorted(inputs_daily),
        "inputs_weekly": sorted(inputs_weekly),
        "inputs_monthly": sorted(inputs_monthly),
        "inputs_static": sorted(static),
        "resample_daily_to_weekly": sorted(resample_daily_to_weekly),
        "resample_daily_to_monthly": sorted(resample_daily_to_monthly),
        "resample_weekly_to_monthly": sorted(resample_weekly_to_monthly),
        "outputs_daily": sorted(set(outputs_daily)),
        "outputs_weekly": sorted(set(outputs_weekly)),
        "outputs_monthly": sorted(set(outputs_monthly)),
    }


def generate_config(
    builtin_models: list[str],
    custom_modules: list[str],
    paths: dict[str, str],
) -> Config:
    """Generate a Config object.

    Parameters
    ----------
    builtin_models : list[str]
        List of builtin model names (e.g., ["splash", "pmodel"]).
    custom_modules : list[str]
        List of custom module paths.
    paths : dict[str, str]
        Dictionary mapping path keys to file paths.

    Returns
    -------
    Config
        Configuration object.
    """
    required_data = _infer_required_data(builtin_models)

    config_data: dict[str, Any] = {}

    config_data["models"] = {}
    for model in builtin_models:
        params = get_model_params(model)
        if params:
            config_data["models"][model] = params

    freq_keys = ("daily", "weekly", "monthly", "static")
    config_data["inputs"] = {
        freq: {"path": paths[f"inputs_{freq}"], "vars": required_data[f"inputs_{freq}"]}
        for freq in freq_keys
        if required_data[f"inputs_{freq}"]
    }

    resample_list = []
    for k in (
        "resample_daily_to_weekly",
        "resample_daily_to_monthly",
        "resample_weekly_to_monthly",
    ):
        vars_ = required_data[k]
        if vars_:
            direction = k.removeprefix("resample_")
            from_freq, to_freq = direction.split("_to_")
            resample_list.append(
                {
                    "vars": vars_,
                    "from_freq": from_freq,
                    "to_freq": to_freq,
                    # aggfunc omitted → defaults to "mean" at parse time
                    # TODO: support per-variable aggfunc (e.g. auto-classify
                    # precipitation as sum)
                }
            )
    if resample_list:
        config_data["resample"] = resample_list

    output_freqs = ("daily", "weekly", "monthly")
    config_data["outputs"] = {
        freq: {
            "path": paths[f"outputs_{freq}"],
            "vars": required_data[f"outputs_{freq}"],
        }
        for freq in output_freqs
        if required_data[f"outputs_{freq}"]
    }

    for mod_path in custom_modules:
        pkg, mod = mod_path.split(".", 1)
        config_data.setdefault(pkg, {})[mod] = get_model_params(mod_path)

    return Config(config_data)
