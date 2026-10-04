# er-spack-environments

This repository implements a family-based environment approach:

1. CPU base templates
2. GPU base templates
3. CPU x GPU matrix
4. Optional env overlays
5. Generator script for concrete `env-<cpuFamily>-<gpuFamily>` manifests
6. CI check for stale generated files

An additional `README.md` is in `environments/bespoke/`

## Environment generator usage (`generate_envs.py`)

### Generator inputs

- `matrix/env_matrix.yaml`
- `matrix/features_to_family.yaml` (used to derive pairs when `enabled_pairs` is omitted/empty)
- `templates/base/cpu/*.yaml`
- `templates/base/gpu/*.yaml`
- `templates/overlay/env/*.yaml` (optional, for named environment overrides)

### Update feature-to-family mappings

Generate `matrix/features_to_family.yaml` from scheduler feature data:

```bash
python scripts/update_features_to_family.py
```

Which Slurm feature token(s) map to which CPU/GPU family (and, for GPUs,
which family wins when a node reports more than one GPU token) is read from
`matrix/env_matrix.yaml`'s `cpu_families`/`gpu_families` sections, not
hardcoded in the script. Adding a new architecture's token mapping is done by
editing `matrix/env_matrix.yaml` alone (see "CPU architectures" below) — no
script change needed. A CPU family's `slurm_features` defaults to
`[<family name>]` when omitted, so a new CPU family is just `<name>: {}`;
only set `slurm_features` explicitly if the live Slurm token(s) differ from
the family name.

With no `--input`, a source is auto-detected in order: `/etc/slurm/slurm.conf`
(production), then live `scontrol show nodes` (if `scontrol` is on `PATH`).
There is no repo-local fallback — pass `--input <path>` explicitly on a
machine that is neither.

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

### Module naming projections (TCL)

- Set global/default projection rules in `matrix/env_matrix.yaml` under:
	- `settings.modules_tcl_projections`
	- `settings.modules_tcl_exclude` (package names/patterns to skip module generation for entirely)
- Example:
	- `all: "{name}/{version}"`
	- `^mpi: "{name}/{version}-mpi-{^mpi.name}"`
	- `boost+container: "{name}/{version}-container"`
- Override per generated environment by setting `spack.modules.default.tcl.projections` (or `.exclude`) in:
	- `templates/overlay/env/env-<cpu>-<gpu>.yaml`

Projection precedence is: env overlay values first, then matrix defaults.

With `concretizer.unify: false`, the same package/version can be concretized
independently more than once (once per root spec that needs it), producing
distinct module-file name clashes if the naming scheme can't tell the copies
apart. Prefer a variant- or dependency-qualified projection key
(`pkg+variant`, `pkg build_type=...`, `^dep`, `^dep.version`) over a bare
content hash, since a hash suffix changes on every rebuild and would force
users to update job scripts each time. For packages that are pure build-time/
transitive dependencies and are never meant to be loaded directly (build
tools, font/graphics-stack internals, pip bootstrap packages), add them to
`modules_tcl_exclude` instead of trying to disambiguate them.

Don't exclude a package that something needs at run time, Python packages in
particular. An excluded package gets no module, so dependents can't autoload
it, and it drops out of their `PYTHONPATH`/`PATH`. The alternative is
`hide_implicits: true` in an env overlay (as in
`templates/overlay/env/env-sapphirerapids-*.yaml`). Every dependency then gets
a module that is hidden from `module avail` and named with a hash suffix, so
duplicate copies don't clash, and autoload still loads it. Only explicitly
installed specs (env roots) stay visible, so add a package as a root if users
should load it directly.

### Generator outputs

- `environments/generated/env-<arch>/spack.yaml`
- `environments/index.yaml`

`environments/index.yaml` includes generated entries and any bespoke manifests
found under `environments/bespoke/**/spack.yaml`.

Only matrix-enabled pairs are generated.

Bespoke environments are created in:

- `environments/bespoke/<name>/spack.yaml`

`<name>` is freeform (not required to follow `env-<arch>`); see
`environments/bespoke/README.md` for naming and the optional `meta.yaml`
(Slurm `constraint`) sidecar.

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
- `zen5` (`zen5`)

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
