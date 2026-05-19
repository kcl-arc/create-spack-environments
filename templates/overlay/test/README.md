# Test Overlay Templates

This directory contains optional test-specific overrides for Spack environment configurations.

## How it works

When `generate_envs.py` creates test environments (e.g., `env-amd_legacy-cpu-test`), it applies the standard CPU and GPU templates, then optionally merges test-specific overlays **if they exist**.

### Merge order for test environments:
1. `templates/base/cpu/{cpu_family}.yaml`  
2. `templates/overlay/gpu/{gpu_family}.yaml`  
3. `templates/overlay/test/{cpu_family}.yaml` (if exists)  
4. `templates/overlay/test/{gpu_family}.yaml` (if exists)

### Use cases

- **Reduce scope**: Add a minimal spec list to test out a subset of packages before rolling out to production.
- **Alternative variants**: Use different Spack variants or compiler flags for testing performance.
- **Early validation**: Test new package versions or configurations before general availability.

### Example

To add a test-specific override for the `amd_legacy` CPU family:

**File**: `templates/overlay/test/amd_legacy.yaml`

```yaml
spack:
  specs:
    - "cmake@3.27.0"  # Test a specific version
    - "zlib~optimize"  # Test without optimization
```

This would override/augment the specs in the prod `amd_legacy.yaml` template for all test environments like `env-amd_legacy-cpu-test` and `env-amd_legacy-sm80-test`.

## Notes

- Test overlays use the same merge logic as GPU overlays: dictionaries are deep-merged, lists are deduplicated (with whitespace-normalization for Spack specs).
- Prod environments ignore test overlays entirely.
- Both CPU and GPU test overlays can exist independently—use only what you need.
