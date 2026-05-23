#!/usr/bin/env python3
"""Generate env-<cpu>-<gpu> manifests from matrix and template fragments."""

from __future__ import annotations

import argparse
import copy
import pathlib
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
MATRIX_FILE = ROOT / "matrix" / "env_matrix.yaml"
CPU_TEMPLATE_DIR = ROOT / "templates" / "base" / "cpu"
GPU_TEMPLATE_DIR = ROOT / "templates" / "overlay" / "gpu"
TEST_TEMPLATE_DIR = ROOT / "templates" / "overlay" / "test"
ENV_ROOT = ROOT / "environments"
GENERATED_DIR = ENV_ROOT / "generated"
BESPOKE_DIR = ENV_ROOT / "bespoke"
INDEX_FILE = ENV_ROOT / "index.yaml"


def normalize_spack_spec(spec: str) -> str:
    return "".join(spec.split())


def is_equivalent_list_item(left: Any, right: Any, normalize_strings: bool) -> bool:
    if normalize_strings and isinstance(left, str) and isinstance(right, str):
        return normalize_spack_spec(left) == normalize_spack_spec(right)
    return left == right


def merge_list_unique(dst_list: list[Any], src_list: list[Any], normalize_strings: bool = False) -> list[Any]:
    merged = list(dst_list)
    for item in src_list:
        if not any(is_equivalent_list_item(item, existing, normalize_strings) for existing in merged):
            merged.append(copy.deepcopy(item))
    return merged


def deep_merge(dst: dict[str, Any], src: dict[str, Any], path: tuple[str, ...] = ()) -> dict[str, Any]:
    for key, value in src.items():
        if key in dst and isinstance(dst[key], dict) and isinstance(value, dict):
            deep_merge(dst[key], value, path + (key,))
        elif key in dst and isinstance(dst[key], list) and isinstance(value, list):
            normalize_strings = path + (key,) == ("spack", "specs")
            dst[key] = merge_list_unique(dst[key], value, normalize_strings=normalize_strings)
        else:
            dst[key] = copy.deepcopy(value)
    return dst


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def normalize_fragment(doc: dict[str, Any]) -> dict[str, Any]:
    if "spack" in doc:
        return doc

    # Treat shorthand fragments as content for the spack root section.
    spack_fragment_keys = {
        "specs",
        "packages",
        "concretizer",
        "view",
        "modules",
        "container",
        "config",
        "upstreams",
        "develop",
        "repos",
        "mirrors",
    }
    if any(key in doc for key in spack_fragment_keys):
        return {"spack": copy.deepcopy(doc)}

    return doc


def write_yaml(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def render(
    cpu_family: str,
    gpu_family: str,
    is_test: bool = False,
    test_env_name: str | None = None,
) -> dict[str, Any]:
    cpu_path = CPU_TEMPLATE_DIR / f"{cpu_family}.yaml"
    gpu_path = GPU_TEMPLATE_DIR / f"{gpu_family}.yaml"
    cpu_doc = normalize_fragment(load_yaml(cpu_path))
    gpu_doc = normalize_fragment(load_yaml(gpu_path))

    merged: dict[str, Any] = {}
    deep_merge(merged, cpu_doc)
    deep_merge(merged, gpu_doc)
    
    if is_test:
        test_cpu_path = TEST_TEMPLATE_DIR / f"{cpu_family}.yaml"
        test_gpu_path = TEST_TEMPLATE_DIR / f"{gpu_family}.yaml"
        test_env_path = TEST_TEMPLATE_DIR / f"{test_env_name}.yaml" if test_env_name else None
        if test_cpu_path.exists():
            test_cpu_doc = normalize_fragment(load_yaml(test_cpu_path))
            deep_merge(merged, test_cpu_doc)
        if test_gpu_path.exists():
            test_gpu_doc = normalize_fragment(load_yaml(test_gpu_path))
            deep_merge(merged, test_gpu_doc)
        if test_env_path and test_env_path.exists():
            test_env_doc = normalize_fragment(load_yaml(test_env_path))
            deep_merge(merged, test_env_doc)
    
    return merged


def ensure_generated_structure(data: dict[str, Any], env_name: str, settings: dict[str, Any]) -> dict[str, Any]:
    spack = data.setdefault("spack", {})
    modules = spack.setdefault("modules", {})
    default = modules.setdefault("default", {})

    enable = default.setdefault("enable", [])
    if "tcl" not in enable:
        enable.append("tcl")

    roots = default.setdefault("roots", {})
    modules_root_base = settings.get("modules_root_base", "/software/spack_v1_1_1/install/modules")
    roots.setdefault("tcl", f"{modules_root_base}/{env_name}/")

    tcl = default.setdefault("tcl", {})
    tcl.setdefault("hash_length", 0)
    tcl.setdefault("naming_scheme", "{name}/{version}-{compiler.name}-{compiler.version}")

    container = spack.setdefault("container", {})
    container.setdefault("format", settings.get("container_format", "singularity"))

    return data


def infer_slurm_constraint(cpu_family: str, matrix: dict[str, Any]) -> str | None:
    cpu_meta = matrix.get("cpu_families", {}).get(cpu_family, {})
    features = cpu_meta.get("slurm_features", [])
    if not features:
        return None
    return str(features[0])


def discover_bespoke_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not BESPOKE_DIR.exists():
        return entries

    for manifest in sorted(BESPOKE_DIR.rglob("spack.yaml")):
        env_name = manifest.parent.name
        if not env_name.startswith("env-"):
            continue
        entries.append(
            {
                "name": env_name,
                "manifest": str(manifest.relative_to(ROOT)).replace("\\", "/"),
                "source": "bespoke",
                "enabled": True,
            }
        )
    return entries


def write_index(entries: list[dict[str, Any]]) -> None:
    payload = {"environments": entries}
    write_yaml(INDEX_FILE, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check generated files are up to date")
    args = parser.parse_args()

    matrix = load_yaml(MATRIX_FILE)
    enabled_pairs = matrix.get("enabled_pairs", [])
    settings = matrix.get("settings", {})
    stale = []
    generated_index_entries: list[dict[str, Any]] = []

    for cpu_family, gpu_family in enabled_pairs:
        env_name = f"env-{cpu_family}-{gpu_family}"
        
        # Prod environment
        prod_data = render(cpu_family, gpu_family, is_test=False)
        prod_data = ensure_generated_structure(prod_data, env_name, settings)
        prod_path = GENERATED_DIR / env_name / "spack.yaml"
        
        # Test environment
        test_env_name = f"{env_name}-test"
        test_data = render(cpu_family, gpu_family, is_test=True, test_env_name=test_env_name)
        test_data = ensure_generated_structure(test_data, test_env_name, settings)
        test_path = GENERATED_DIR / test_env_name / "spack.yaml"

        constraint = infer_slurm_constraint(cpu_family, matrix)
        generated_index_entries.extend(
            [
                {
                    "name": env_name,
                    "manifest": str(prod_path.relative_to(ROOT)).replace("\\", "/"),
                    "constraint": constraint,
                    "source": "generated",
                    "enabled": True,
                },
                {
                    "name": test_env_name,
                    "manifest": str(test_path.relative_to(ROOT)).replace("\\", "/"),
                    "constraint": constraint,
                    "source": "generated",
                    "enabled": True,
                },
            ]
        )

        if args.check:
            expected_prod = yaml.safe_dump(prod_data, sort_keys=False)
            expected_test = yaml.safe_dump(test_data, sort_keys=False)
            if not prod_path.exists() or prod_path.read_text(encoding="utf-8") != expected_prod:
                stale.append(str(prod_path))
            if not test_path.exists() or test_path.read_text(encoding="utf-8") != expected_test:
                stale.append(str(test_path))
        else:
            write_yaml(prod_path, prod_data)
            write_yaml(test_path, test_data)

    index_entries = generated_index_entries + discover_bespoke_entries()

    if args.check:
        expected_index = yaml.safe_dump({"environments": index_entries}, sort_keys=False)
        if not INDEX_FILE.exists() or INDEX_FILE.read_text(encoding="utf-8") != expected_index:
            stale.append(str(INDEX_FILE))
    else:
        write_index(index_entries)

    if args.check and stale:
        print("Stale or missing generated manifests:")
        for item in stale:
            print(f"- {item}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
