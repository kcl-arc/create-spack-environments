# Install backlog (former test overlays)

`-test` environments are no longer generated, and `generate_envs.py` no longer
reads this directory.

The files here are kept only for their commented-out specs: a reminder of what
needs to be installed next for each CPU or GPU family (one file per family).

To roll a spec out, add it to the matching base template
(`templates/base/cpu/<family>.yaml` or `templates/base/gpu/<family>.yaml`), or
to an env overlay (`templates/overlay/env/env-<cpu>-<gpu>.yaml`) for a single
environment. Then remove the commented line here.
