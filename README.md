# er-spack-environments scaffold (family model)

This staged scaffold implements the family-based environment approach:

1. CPU base templates
2. GPU overlay templates
3. CPU x GPU matrix
4. Generator script for concrete `env-<cpuFamily>-<gpuFamily>` manifests
5. CI check for stale generated files

## Proposed CPU families

- `amd_legacy`: `zen2`, `zen3`
- `intel_legacy`: `skylake_avx512`, `cascadelake`
- `icelake`: `icelake`
- `zen4_spr`: `zen4`, `sapphirerapids`
- `x86v4`: `x86_64_v4`

Rationale: this keeps family count small while still tracking major ABI/perf boundaries.

## Proposed GPU families

- `cpu` (no GPU)
- `legacy` (`rtx2070`, `rtx2080`, `rtx3070`, `rtx3090`, `titan_x`, `titan_xp`, `titan_v`, `titan_rtx`)
- `sm80` (`a30`, `a40`, `a100`, `a100_40g`, `a100_80g`)
- `sm90` (`h100`, `h200`)
- `sm100` (`b200`)
- `rtx6000_l40s` (`rtx6000`, `l40s`)

## Generator outputs

The generator writes:

- `environments/generated/env-<arch>/spack.yaml`
- `environments/generated/env-<arch>-test/spack.yaml`
- `environments/index.yaml`

Only matrix-enabled pairs are generated.

Bespoke environments live in:

- `environments/bespoke/env-<arch>/spack.yaml`
- `environments/bespoke/env-<arch>-test/spack.yaml`

## CUDA policy in this model

- Keep `+cuda` package build intent in `er-spack-packages/package_installs/*.yaml`.
- Set preferred CUDA toolkit and package-level `cuda_arch` in GPU overlays.
- Do not set global `cuda_arch` in repo-level `config/packages.yaml`.
