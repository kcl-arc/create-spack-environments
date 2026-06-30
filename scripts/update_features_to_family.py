#!/usr/bin/env python3
"""Generate matrix/features_to_family.yaml from scheduler feature data.

The input can be a plain list of lines containing `Features=...`, such as:
- slurm.conf content
- `scontrol show nodes` output
- markdown snippets that include `Features=...`
"""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / ".repomix" / "input" / "features.md"
OUTPUT_FILE = ROOT / "matrix" / "features_to_family.yaml"
OVERRIDES_FILE = ROOT / "matrix" / "features_to_family_overrides.yaml"

CPU_TOKEN_TO_FAMILY: list[tuple[str, str]] = [
    ("zen2", "zen2"),
    ("zen3", "zen3"),
    ("zen4", "zen4"),
    ("icelake", "icelake"),
    ("cascadelake", "cascadelake"),
    ("sapphirerapids", "sapphirerapids"),
    ("x86_64_v4", "x86v4"),
    ("skylake_avx512", "skylake"),
]

# Higher rank wins when multiple GPU tokens are present.
GPU_TOKEN_PRIORITY: dict[str, tuple[int, str]] = {
    "b200": (100, "sm100"),
    "rtx6000": (100, "sm100"),
    "h200": (90, "sm90"),
    "h100": (90, "sm90"),
    "l40s": (89, "sm89"),
    "a100": (80, "sm80"),
    "a100_40g": (80, "sm80"),
    "a100_80g": (80, "sm80"),
    "a30": (80, "sm80"),
    "rtx3070": (86, "sm86"),
    "rtx3090": (86, "sm86"),
    "a40": (86, "sm86"),
    "rtx2070": (75, "sm75"),
    "rtx2080": (75, "sm75"),
    "titan_rtx": (75, "sm75"),
    "titan_v": (70, "sm70"),
    "titan_x": (61, "sm61"),
    "titan_xp": (61, "sm61"),
}

FEATURES_RE = re.compile(r"Features\s*=\s*([^\s]+)")


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def dump_yaml(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


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


def infer_cpu_family(features: tuple[str, ...]) -> str | None:
    feature_set = set(features)
    for token, family in CPU_TOKEN_TO_FAMILY:
        if token in feature_set:
            return family
    return None


def infer_gpu_family(features: tuple[str, ...]) -> str:
    best_rank = -1
    best_family = "cpu"
    for token in features:
        info = GPU_TOKEN_PRIORITY.get(token)
        if not info:
            continue
        rank, family = info
        if rank > best_rank:
            best_rank = rank
            best_family = family
    return best_family


def mappings_from_features(feature_sets: list[tuple[str, ...]], strict: bool) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    unknown_cpu_sets: list[tuple[str, ...]] = []

    for feature_set in feature_sets:
        cpu_family = infer_cpu_family(feature_set)
        if cpu_family is None:
            unknown_cpu_sets.append(feature_set)
            continue

        mappings.append(
            {
                "features": list(feature_set),
                "cpu_family": cpu_family,
                "gpu_family": infer_gpu_family(feature_set),
            }
        )

    if strict and unknown_cpu_sets:
        formatted = "\n".join(f"- {','.join(item)}" for item in unknown_cpu_sets)
        raise ValueError(f"Could not infer CPU family for feature sets:\n{formatted}")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Update matrix/features_to_family.yaml from feature data")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Path to source text containing Features=... entries",
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

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    overrides_path = pathlib.Path(args.overrides)

    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    feature_sets = extract_feature_sets(text)
    mappings = mappings_from_features(feature_sets, strict=not args.allow_unknown_cpu)

    overrides_doc = load_yaml(overrides_path)
    overrides = overrides_doc.get("mappings", [])
    if overrides and not isinstance(overrides, list):
        raise SystemExit(f"Invalid overrides format in {overrides_path}: 'mappings' must be a list")

    merged = merge_overrides(mappings, overrides if isinstance(overrides, list) else [])

    payload = {
        "source": str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else str(input_path),
        "mappings": merged,
    }
    dump_yaml(output_path, payload)


if __name__ == "__main__":
    main()
