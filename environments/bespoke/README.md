# Bespoke environments

Place bespoke environments here as:

- `environments/bespoke/<name>/spack.yaml`
- `environments/bespoke/<name>/meta.yaml` (optional)

`<name>` can be anything (e.g. `arc-zen3-cpu`, `arc-ops-rcmb`) — it is not
required to follow the `env-<arch>` form used by generated environments.

Notes:

- Every `spack.yaml` found under `environments/bespoke/**/` is indexed as-is;
  nothing is merged in from the matrix/template pipeline that produces
  `environments/generated/**`.
- If the environment's build/install jobs must land on a specific class of
  node (e.g. to build for a given CPU target), add a `meta.yaml` next to
  `spack.yaml` with a `constraint` key naming the Slurm feature to constrain
  to, e.g.:

  ```yaml
  constraint: zen3
  ```

  Without this, env-sync jobs for the environment are submitted with no
  `--constraint` and may land on any node.
- Re-run `python scripts/generate_envs.py` after adding bespoke manifests so
  `environments/index.yaml` is refreshed (does run on push to the Github repository).
