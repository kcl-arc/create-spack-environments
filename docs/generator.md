# Environment generator usage

## Generate manifests

```bash
python scripts/generate_envs.py
```

## Check manifests are up to date

```bash
python scripts/generate_envs.py --check
```

## Can this run in GitHub Actions?

Yes.

- `.github/workflows/check-generated-envs.yml` enforces `--check` on PR/push.
- `.github/workflows/generate-env-index.yml` supports two publish modes.

This means local execution is optional; CI can maintain generated outputs.

### Publish modes and triggers

1. PR mode
- Trigger:
	- push to any non-`staging`/non-`production` branch when generator inputs change
	- manual run (`workflow_dispatch`) with `mode=pr`
- Outcome:
	- regenerates files
	- commits generated changes back to the same branch
	- team manually opens PR to `staging`

2. Direct staging mode
- Trigger:
	- manual run (`workflow_dispatch`) with `mode=direct-staging`
- Outcome:
	- checks out `staging`
	- regenerates files
	- commits and pushes directly to `staging` if changes exist

## Inputs

- `matrix/env_matrix.yaml`
- `templates/base/cpu/*.yaml`
- `templates/overlay/gpu/*.yaml`

## Outputs

- `environments/generated/env-<arch>/spack.yaml`
- `environments/generated/env-<arch>-test/spack.yaml`
- `environments/index.yaml`

`environments/index.yaml` includes generated entries and any bespoke manifests
found under `environments/bespoke/**/spack.yaml`.
