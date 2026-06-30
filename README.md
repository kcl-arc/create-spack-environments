# er-spack-environments

This repository implements a family-based environment approach:

1. CPU base templates
2. GPU base templates
3. CPU x GPU matrix
4. Optional env/test overlays
5. Generator script for concrete `env-<cpuFamily>-<gpuFamily>` manifests
6. CI check for stale generated files

Additional `README.md` files are in `templates/overlay/test/` and `environments/bespoke/`

## Environment generator usage (`generate_envs.py`)

### Generator inputs

- `matrix/env_matrix.yaml`
- `matrix/features_to_family.yaml` (used to derive pairs when `enabled_pairs` is omitted/empty)
- `templates/base/cpu/*.yaml`
- `templates/base/gpu/*.yaml`
- `templates/overlay/env/*.yaml` (optional, for named environment overrides)
- `templates/overlay/test/*.yaml` (optional, for test-specific overrides)

### Update feature-to-family mappings

Generate `matrix/features_to_family.yaml` from scheduler feature data:

```bash
python scripts/update_features_to_family.py
```

Optional overrides can be added in `matrix/features_to_family_overrides.yaml`.

### Run on cluster (recommended deployment pre-step)

When you want mappings and generated environments to reflect live Slurm state, run this on a cluster host with `scontrol` (automatically called by `spack_deploy.py` in hpc-spack_core repo):

```bash
./scripts/refresh_env_matrix.sh
```

This performs, in order:
1. Collect node `Features=` values from Slurm.
2. Regenerate `matrix/features_to_family.yaml`.
3. Regenerate `environments/generated/**` and `environments/index.yaml`.
4. Regenerate `environments/root_install_queue.yaml`.

### Module naming projections (TCL)

- Set global/default projection rules in `matrix/env_matrix.yaml` under:
	- `settings.modules_tcl_projections`
- Example:
	- `all: "{name}/{version}-{compiler.name}-{compiler.version}"`
	- `+mpi: "{name}/{version}-mpi-{compiler.name}-{compiler.version}"`
- Override per generated environment by setting `spack.modules.default.tcl.projections` in:
	- `templates/overlay/env/env-<cpu>-<gpu>.yaml`
	- `templates/overlay/env/env-<cpu>-<gpu>-test.yaml`
	- or family-level test overlays such as `templates/overlay/test/cascadelake.yaml`

Projection precedence is: env/test overlay values first, then matrix defaults.

### Generator outputs

- `environments/generated/env-<arch>/spack.yaml`
- `environments/generated/env-<arch>-test/spack.yaml`
- `environments/index.yaml`

`environments/index.yaml` includes generated entries and any bespoke manifests
found under `environments/bespoke/**/spack.yaml`.

Only matrix-enabled pairs are generated.

Bespoke environments are created in:

- `environments/bespoke/env-<arch>/spack.yaml`
- `environments/bespoke/env-<arch>-test/spack.yaml`

### Generate manifests locally

```bash
python scripts/generate_envs.py
```

### Check manifests are up to date

```bash
python scripts/generate_envs.py --check
```

### GitHub Actions

- `.github/workflows/check-generated-envs.yml` enforces `--check` on PR/push.
- `.github/workflows/generate-env-index.yml` supports two publish modes.

This means local execution is optional (although still useful to check the resulting `spack.yaml` files are as expected).

#### Publish modes and triggers

1. PR mode
- Trigger by either:
	- push to any non-`staging`/non-`production` branch when generator inputs change
	- manual run (`workflow_dispatch`) with `mode=pr`
- Outcome:
	- regenerates files
	- commits generated changes back to the same branch

2. Direct staging mode (deprecated)
- Trigger:
	- manual run (`workflow_dispatch`) with `mode=direct-staging`
- Outcome:
	- checks out `staging`
	- regenerates files
	- commits and pushes directly to `staging` if changes exist

## CPU architectures

- `icelake` (`icelake`)
- `skylake` (`skylake_avx512`)
- `cascadelake` (`cascadelake`)
- `sapphirerapids` (`sapphirerapids`)
- `x86v4` (`x86_64_v4`)
- `zen2` (`zen2`)
- `zen3` (`zen3`)
- `zen4` (`zen4`)

## GPU families

- `cpu` (no GPU)
- `sm61` (`titan_x`, `titan_xp`) — Pascal; deprecated in CUDA 12.8
- `sm70` (`titan_v`) — Volta; deprecated in CUDA 12.8
- `sm75` (`rtx2070`, `rtx2080`, `titan_rtx`) — Turing
- `sm80` (`a30`, `a100`, `a100_40g`, `a100_80g`) — Ampere data-centre
- `sm86` (`rtx3070`, `rtx3090`, `a40`) — Ampere client
- `sm90` (`h100`, `h200`)
- `sm89` (`l40s`)
- `sm100` (`b200`, `rtx6000`)

## CUDA policy in this model

- Keep `+cuda` package build intent in `er-spack-packages/package_installs/*.yaml`.
- Set preferred CUDA toolkit and package-level `cuda_arch` in GPU base templates.
- Do not set global `cuda_arch` in repo-level `config/packages.yaml`.
