#!/usr/bin/env python3
"""Generate matrix/features_to_family.yaml from scheduler feature data.

CPU/GPU family definitions -- which Slurm feature token(s) map to which
family, and which GPU family wins when a node reports more than one GPU
token -- are sourced from matrix/env_matrix.yaml's `cpu_families` and
`gpu_families` sections, not hardcoded here. Adding a new CPU architecture is
just a `cpu_families: {<name>: {}}` entry in matrix/env_matrix.yaml (its
Slurm feature token defaults to the family name) plus a base template under
templates/base/cpu/; no edit to this script is needed.

The input can be a plain list of lines containing `Features=...`, such as:
- slurm.conf content
- `scontrol show nodes` output
- markdown snippets that include `Features=...`

When --input is not given, a source is auto-detected in this order:
1. /etc/slurm/slurm.conf, if present (the production Slurm config).
2. Live `scontrol show nodes` output, if `scontrol` is on PATH.

There is deliberately no repo-local fallback fixture: this script has no
useful default on a machine that is neither a production Slurm host nor has
`scontrol` on PATH. Pass --input explicitly there.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
PRODUCTION_SLURM_CONF = pathlib.Path("/etc/slurm/slurm.conf")
MATRIX_FILE = ROOT / "matrix" / "env_matrix.yaml"
OUTPUT_FILE = ROOT / "matrix" / "features_to_family.yaml"
OVERRIDES_FILE = ROOT / "matrix" / "features_to_family_overrides.yaml"

FEATURES_RE = re.compile(r"Features\s*=\s*([^\s]+)")


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def dump_yaml(path: pathlib.Path, payload: dict[str, Any], header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if header:
            handle.write(header)
        yaml.safe_dump(payload, handle, sort_keys=False)


def load_cpu_token_to_family(matrix_doc: dict[str, Any]) -> dict[str, str]:
    """Derive {slurm feature token: cpu family} from env_matrix.yaml's cpu_families.

    A family's `slurm_features` defaults to `[family]` when omitted/empty --
    every CPU family so far uses a single Slurm feature token identical to
    its family name, so declaring a new one is just `<name>: {}`. Only
    override `slurm_features` for the rare family whose live Slurm token(s)
    differ from its family name.
    """
    cpu_families = matrix_doc.get("cpu_families", {})
    if not isinstance(cpu_families, dict):
        raise ValueError("matrix/env_matrix.yaml: 'cpu_families' must be a mapping")

    token_to_family: dict[str, str] = {}
    for family, family_cfg in cpu_families.items():
        if family_cfg is None:
            family_cfg = {}
        if not isinstance(family_cfg, dict):
            continue
        tokens = family_cfg.get("slurm_features") or [family]
        for token in tokens:
            token = str(token).strip()
            if not token:
                continue
            existing = token_to_family.get(token)
            if existing and existing != family:
                raise ValueError(
                    "matrix/env_matrix.yaml: CPU feature token %r is claimed by "
                    "both %r and %r" % (token, existing, family)
                )
            token_to_family[token] = family
    return token_to_family


def load_gpu_token_priority(matrix_doc: dict[str, Any]) -> dict[str, tuple[int, str]]:
    """Derive {slurm feature token: (priority, gpu family)} from gpu_families.

    Priority is the family's `preferred_cuda_arch` (higher wins when a node
    reports multiple GPU tokens); families without one (e.g. the non-GPU
    `cpu` family) contribute no tokens here.
    """
    gpu_families = matrix_doc.get("gpu_families", {})
    if not isinstance(gpu_families, dict):
        raise ValueError("matrix/env_matrix.yaml: 'gpu_families' must be a mapping")

    token_priority: dict[str, tuple[int, str]] = {}
    for family, family_cfg in gpu_families.items():
        if not isinstance(family_cfg, dict):
            continue
        cuda_arch = family_cfg.get("preferred_cuda_arch")
        if cuda_arch is None:
            continue
        try:
            priority = int(str(cuda_arch).strip())
        except ValueError:
            raise ValueError(
                "matrix/env_matrix.yaml: gpu family %r has a non-numeric "
                "preferred_cuda_arch %r" % (family, cuda_arch)
            )
        for token in family_cfg.get("slurm_features", []) or []:
            token = str(token).strip()
            if not token:
                continue
            existing = token_priority.get(token)
            if existing and existing[1] != family and existing[0] >= priority:
                continue
            token_priority[token] = (priority, family)
    return token_priority


def canonicalize_features(features: list[str]) -> tuple[str, ...]:
    cleaned = sorted({token.strip() for token in features if token.strip()})
    return tuple(cleaned)


def extract_feature_sets(text: str) -> list[tuple[str, ...]]:
    sets: set[tuple[str, ...]] = set()
    for match in FEATURES_RE.finditer(text):
        raw = match.group(1)
        tokens = raw.split(",")
        feature_set = canonicalize_features(tokens)
        if feature_set:
            sets.add(feature_set)
    return sorted(sets)


def infer_cpu_family(features: tuple[str, ...], cpu_token_to_family: dict[str, str]) -> str | None:
    for token in features:
        family = cpu_token_to_family.get(token)
        if family:
            return family
    return None


def infer_gpu_family(features: tuple[str, ...], gpu_token_priority: dict[str, tuple[int, str]]) -> str:
    best_rank = -1
    best_family = "cpu"
    for token in features:
        info = gpu_token_priority.get(token)
        if not info:
            continue
        rank, family = info
        if rank > best_rank:
            best_rank = rank
            best_family = family
    return best_family


def mappings_from_features(
    feature_sets: list[tuple[str, ...]],
    cpu_token_to_family: dict[str, str],
    gpu_token_priority: dict[str, tuple[int, str]],
    strict: bool,
) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    unknown_cpu_sets: list[tuple[str, ...]] = []

    for feature_set in feature_sets:
        cpu_family = infer_cpu_family(feature_set, cpu_token_to_family)
        if cpu_family is None:
            unknown_cpu_sets.append(feature_set)
            continue

        mappings.append(
            {
                "features": list(feature_set),
                "cpu_family": cpu_family,
                "gpu_family": infer_gpu_family(feature_set, gpu_token_priority),
            }
        )

    if strict and unknown_cpu_sets:
        formatted = "\n".join(f"- {','.join(item)}" for item in unknown_cpu_sets)
        raise ValueError(
            "Could not infer CPU family for feature sets (add a matching "
            "cpu_families entry with these slurm_features to matrix/env_matrix.yaml):\n"
            f"{formatted}"
        )

    return mappings


def merge_overrides(base: list[dict[str, Any]], overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}

    for item in base:
        features = tuple(item.get("features", []))
        if features:
            merged[features] = item

    for item in overrides:
        if not isinstance(item, dict):
            continue
        features = item.get("features")
        if not isinstance(features, list):
            continue
        key = canonicalize_features([str(token) for token in features])
        if not key:
            continue

        cpu_family = str(item.get("cpu_family", "")).strip()
        gpu_family = str(item.get("gpu_family", "")).strip()
        if not cpu_family or not gpu_family:
            continue

        merged[key] = {
            "features": list(key),
            "cpu_family": cpu_family,
            "gpu_family": gpu_family,
        }

    return [merged[key] for key in sorted(merged.keys())]


def _collect_live_scontrol_text() -> str | None:
    scontrol = shutil.which("scontrol")
    if not scontrol:
        return None
    try:
        result = subprocess.run(
            [scontrol, "show", "nodes"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except Exception:
        return None
    return result.stdout


def resolve_default_input() -> tuple[pathlib.Path | None, str | None]:
    """Pick an input source with no explicit --input given.

    Returns (path, live_text): exactly one is set on success, both None if
    nothing usable was found (caller reports the error).
    """
    if PRODUCTION_SLURM_CONF.is_file():
        return PRODUCTION_SLURM_CONF, None

    live_text = _collect_live_scontrol_text()
    if live_text:
        return None, live_text

    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Update matrix/features_to_family.yaml from feature data")
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "Path to source text containing Features=... entries. If omitted, "
            "auto-detects /etc/slurm/slurm.conf, then live `scontrol show nodes`"
        ),
    )
    parser.add_argument(
        "--matrix",
        default=str(MATRIX_FILE),
        help="Path to env_matrix.yaml providing cpu_families/gpu_families definitions",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help="Output YAML file path",
    )
    parser.add_argument(
        "--overrides",
        default=str(OVERRIDES_FILE),
        help="Optional override YAML file path",
    )
    parser.add_argument(
        "--allow-unknown-cpu",
        action="store_true",
        help="Skip feature sets where cpu_family cannot be inferred",
    )
    args = parser.parse_args()

    matrix_path = pathlib.Path(args.matrix)
    matrix_doc = load_yaml(matrix_path)
    if not matrix_doc:
        raise SystemExit(f"Matrix file does not exist or is empty: {matrix_path}")
    cpu_token_to_family = load_cpu_token_to_family(matrix_doc)
    gpu_token_priority = load_gpu_token_priority(matrix_doc)

    live_text: str | None = None
    if args.input:
        input_path = pathlib.Path(args.input)
        if not input_path.exists():
            raise SystemExit(f"Input file does not exist: {input_path}")
        text = input_path.read_text(encoding="utf-8")
        source_label = str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else str(input_path)
    else:
        input_path, live_text = resolve_default_input()
        if input_path is None and live_text is None:
            raise SystemExit(
                "No input source found: no --input given, /etc/slurm/slurm.conf is "
                "not present, and `scontrol` is not on PATH. Pass --input explicitly."
            )
        if live_text is not None:
            text = live_text
            source_label = "live: scontrol show nodes"
        else:
            text = input_path.read_text(encoding="utf-8")
            source_label = str(input_path)

    feature_sets = extract_feature_sets(text)
    mappings = mappings_from_features(
        feature_sets, cpu_token_to_family, gpu_token_priority, strict=not args.allow_unknown_cpu
    )

    overrides_path = pathlib.Path(args.overrides)
    overrides_doc = load_yaml(overrides_path)
    overrides = overrides_doc.get("mappings", [])
    if overrides and not isinstance(overrides, list):
        raise SystemExit(f"Invalid overrides format in {overrides_path}: 'mappings' must be a list")

    merged = merge_overrides(mappings, overrides if isinstance(overrides, list) else [])

    payload = {
        "source": source_label,
        "mappings": merged,
    }
    header = (
        "# Map observed scheduler feature sets to CPU/GPU families.\n"
        "# Generated by scripts/update_features_to_family.py.\n"
        "# Manual disambiguation can be applied in matrix/features_to_family_overrides.yaml.\n"
    )
    dump_yaml(pathlib.Path(args.output), payload, header=header)


if __name__ == "__main__":
    main()
