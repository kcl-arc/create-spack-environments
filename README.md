# create-spack-environments

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

### Module files (TCL)

Every CPU base template sets:

```yaml
modules:
  default:
    tcl:
      hide_implicits: true
      exclude: [gcc-runtime, glibc]
```

- **Only roots are visible.** Each root spec gets a module named by the
  rules below. Every other dependency gets a hidden module with a hash suffix
  (e.g. `bzip2/1.0.8-ksfr4yl`). Autoload still loads it, and
  `module --show-hidden avail` lists it. To let users load a package
  directly, add it as a root.
- **Roots of other environments can be visible too.** Spack takes
  visible/hidden from the install database, not from the environment's roots.
  A spec that is a root of another environment (same hash) is visible in
  every environment that depends on it.
- **Excludes.** An environment can contain more than one copy of
  `gcc-runtime` and `glibc`, which made Lmod print warnings. Neither module
  sets anything needed at run time, so both are excluded. Don't exclude
  anything else that is: an excluded package is dropped from its dependents'
  autoload (a Python package would drop out of their `PYTHONPATH`).

Naming:

- Visible modules are `{name}/{version}`. `settings.modules_tcl_projections`
  in `matrix/env_matrix.yaml` adds rules for every environment.
- A rule is only needed when one environment has two roots with the same
  name and version (e.g. hdf5 with and without MPI). Without one, the module
  refresh fails with a name clash.
- Rules are first-match-wins, so put specific rules first (`hdf5+hl ^mpi`
  before `hdf5+hl`).
- Tell copies apart by variant or dependency (`pkg+variant`, `^dep`), not by
  hash, so names don't change when a package is rebuilt. `^dep` also matches
  indirect link/run dependencies, so a broad rule such as `^mpi` renames many
  unrelated packages.
- Changing a rule renames modules, and a plain refresh leaves the old files
  behind. Set the `--delete-tree` marker for each affected environment first
  (spack_core `docs/submissions_overview.md`).

Per environment: `projections` in an overlay (`templates/overlay/env/`)
replace the matrix rules for that environment rather than adding to them, so
repeat any matrix rules still needed. An `exclude` in an overlay adds to the
base template's list. `settings.modules_tcl_exclude` has no effect at the
moment, because every CPU base template sets `exclude`.

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
- `sm100` (`b200`) — Blackwell data-centre
- `sm120` (`rtx6000`) — Blackwell RTX PRO 6000

## CUDA policy in this model

- Keep `+cuda` package build intent in `er-spack-packages/package_installs/*.yaml`.
- Set preferred CUDA toolkit and package-level `cuda_arch` in GPU base templates.
- Do not set global `cuda_arch` in repo-level `config/packages.yaml`.
