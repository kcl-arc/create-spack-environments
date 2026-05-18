# Bespoke environments

Place bespoke environments here as:

- `environments/bespoke/env-<arch>/spack.yaml`
- `environments/bespoke/env-<arch>-test/spack.yaml` (optional)

Notes:

- Keep names in the required form `env-<arch>` and `env-<arch>-test`.
- Re-run `python scripts/generate_envs.py` after adding bespoke manifests so
  `environments/index.yaml` is refreshed.
