#!/usr/bin/env python3
"""Export env-derived root install queue from generated environment manifests."""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_ROOT = ROOT / "environments"
INDEX_FILE = ENV_ROOT / "index.yaml"
QUEUE_FILE = ENV_ROOT / "root_install_queue.yaml"


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return payload or {}


def dump_yaml(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def normalize_spec(spec: str) -> str:
    return " ".join(spec.split())


def has_target_constraint(spec: str) -> bool:
    return bool(re.search(r"(^|\s)target=", spec))


def with_target_constraint(spec: str, constraint: str | None) -> str:
    normalized = normalize_spec(spec)
    if not constraint:
        return normalized
    if has_target_constraint(normalized):
        return normalized
    return f"{normalized} target={constraint}"


def _extract_spec_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]

    specs: list[str] = []
    if isinstance(node, list):
        for item in node:
            specs.extend(_extract_spec_strings(item))
    elif isinstance(node, dict):
        for key, value in node.items():
            # Matrix excludes are constraints, not root specs.
            if key == "exclude":
                continue
            specs.extend(_extract_spec_strings(value))
    return specs


def is_root_spec(spec: str) -> bool:
    value = spec.strip().strip('"').strip("'")
    if not value:
        return False
    if value.startswith("$"):
        return False
    if value[0] in ["%", "^", "@", "+", "~"]:
        return False
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*", value))


def queue_items_from_index(index: dict[str, Any]) -> list[dict[str, Any]]:
    entries = index.get("environments", [])
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue

        source = str(entry.get("source", ""))
        if source != "generated":
            continue

        env_name = entry.get("name")
        manifest = entry.get("manifest")
        constraint = entry.get("constraint")

        if not isinstance(env_name, str) or not env_name:
            continue
        if not isinstance(manifest, str) or not manifest:
            continue
        if constraint is not None and not isinstance(constraint, str):
            continue

        manifest_path = ROOT / manifest
        if not manifest_path.is_file():
            continue

        manifest_doc = load_yaml(manifest_path)
        spack_cfg = manifest_doc.get("spack", {}) if isinstance(manifest_doc, dict) else {}
        specs_node = spack_cfg.get("specs", []) if isinstance(spack_cfg, dict) else []

        for raw_spec in _extract_spec_strings(specs_node):
            if not is_root_spec(raw_spec):
                continue

            spec = normalize_spec(raw_spec)
            key = (spec, constraint)
            if key not in grouped:
                grouped[key] = {
                    "spec": spec,
                    "constraint": constraint,
                    "envs": set(),
                }
            grouped[key]["envs"].add(env_name)

    items: list[dict[str, Any]] = []
    for spec, constraint in sorted(grouped.keys()):
        envs = sorted(grouped[(spec, constraint)]["envs"])
        for env_name in envs:
            constrained_spec = with_target_constraint(spec, constraint)
            item = {
                "env": env_name,
                "spec": constrained_spec,
                "source": "environments",
            }
            if constraint:
                item["constraint"] = constraint
            items.append(item)

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Export root install queue from generated env manifests")
    parser.add_argument("--check", action="store_true", help="fail if queue file is stale")
    args = parser.parse_args()

    index = load_yaml(INDEX_FILE)
    queue_payload = {"items": queue_items_from_index(index)}
    expected = yaml.safe_dump(queue_payload, sort_keys=False)

    if args.check:
        if not QUEUE_FILE.exists() or QUEUE_FILE.read_text(encoding="utf-8") != expected:
            print("Stale or missing root install queue:")
            print(f"- {QUEUE_FILE}")
            raise SystemExit(1)
        return

    dump_yaml(QUEUE_FILE, queue_payload)


if __name__ == "__main__":
    main()
