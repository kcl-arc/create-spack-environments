# er-spack-environments

## Quick start

The `create-spack-development` repository has been built in order to facilitate the development and testing of new packages. Once a package has been developed using the processes outlined it can be added to the appropriate environments.

If the package needs a local override it will need to be in the `create-spack-packages` repository and the commit hash will need to be updated in `spack_core.pp` in the puppet repo.

specs are added in yaml files in `create-spack-environments`.

The majority of specs can be added in `templates/base/cpu/*.yaml` files.

Packages that use GPUs for processing are added in `templates/base/gpu/sm*.yaml` files. To make a CPU bound version available add it in `templates/base/gpu/cpu.yaml` (an existing example is `quantum-espresso`).

Specific environments can have additional specs (or any other adaptations) by adding `.yaml` file in `templates/overlay/env/`. The `.yaml` files can either be the same name as one of the existing base templates (e.g. `zen5.yaml` or `sm89.yaml`) or a spcific environment (e.g. `env-zen5-sm89.yaml`).

Once a file has been added to these templates the `generate_envs.py` script should be run.

Bespoke environments can also be created; this is with a view to being able to create environments for specific groups if required. A complete `spack.yaml` is entered in a directory with the desired name of the environment.

An additional `README.md` is in `environments/bespoke/`

## Details

This repository implements a family-based environment approach:

1. CPU base templates
2. GPU base templates
3. CPU x GPU matrix
4. Optional env overlays
5. Generator script for concrete `env-<cpuFamily>-<gpuFamily>` manifests
6. CI check for stale generated files

## Environment generator usage (`generate_envs.py`)

### Generator inputs

- `matrix/env_matrix.yaml`
- `matrix/features_to_family.yaml` (maintained by hand; used to derive pairs when `enabled_pairs` is omitted/empty)
- `templates/base/cpu/*.yaml`
- `templates/base/gpu/*.yaml`
- `templates/overlay/env/*.yaml` (optional, for named environment overrides)

### Update feature-to-family mappings

`matrix/features_to_family.yaml` decides which `env-<cpu>-<gpu>` environments
are generated. Edit it by hand in this repo, then regenerate and commit.
Nothing on the cluster updates it.

1. Make sure the families exist in `matrix/env_matrix.yaml`:
   - `cpu_families`: a new CPU family is just `<name>: {}`, plus a base
     template in `templates/base/cpu/`. Its Slurm feature token (used as the
     environment's `constraint` in `environments/index.yaml`) defaults to the
     family name. Only set `slurm_features` if the live token differs.
   - `gpu_families`: copy an existing `sm*` entry, plus a base template in
     `templates/base/gpu/`.
2. Add one mapping per node feature set (the `Features=` value in
   `slurm.conf`). Keep entries sorted by `features`, as the script below
   does, so cross-check diffs stay small:

   ```yaml
   - features:
     - l40s
     - zen5
     cpu_family: zen5
     gpu_family: sm89
   ```

   `generate_envs.py` only reads `cpu_family` and `gpu_family`; `features`
   records which Slurm feature set the mapping covers. To stop building an
   environment, remove its mappings (see "Remove an environment" in the
   spack_core `env-ops.md`).
3. Run `python scripts/generate_envs.py` and commit the result. The
   `generate-env-index` Action doesn't run when only
   `features_to_family.yaml` changes.

#### Optional cross-check against Slurm

`scripts/update_features_to_family.py` rebuilds the mappings from
`Features=` lines, using the `slurm_features` tokens in `env_matrix.yaml`.
Use it only to check the hand-edited file against a freshly copied
`slurm.conf`:

```bash
scp <slurm-controller>:/etc/slurm/slurm.conf /tmp/slurm.conf
python scripts/update_features_to_family.py --input /tmp/slurm.conf
git diff matrix/features_to_family.yaml
```

Always review the diff before keeping any of it:

- An old copy of `slurm.conf` brings back mappings for decommissioned nodes.
- Nodes we deliberately don't build for come back too.
- A GPU token with no `gpu_families` entry is mapped to `gpu_family: cpu`
  without an error. Only unknown CPU tokens fail.

`matrix/features_to_family_overrides.yaml` is applied on top of the script's
output. It can add or replace mappings, not remove them.

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
