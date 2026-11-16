# Development and documentation

```sh
git clone https://github.com/deeplook/termseries.git
cd termseries
uv sync --all-extras
uv run pre-commit install
make test
```

Ruff checks formatting and lint, mypy checks types, and pytest checks behavior.
See [Contributing](https://github.com/deeplook/termseries/blob/main/CONTRIBUTING.md)
for the pull-request workflow.

## Preview the documentation

```sh
uv sync --extra docs
uv run --extra docs mkdocs serve
```

Open the local URL printed by MkDocs. Sources live in `docs/`, navigation and theme
in `mkdocs.yml`. The theme follows the same MkDocs Material setup as
[nfind](https://deeplook.github.io/nfind/).

## Build and check links

```sh
uv run --extra docs mkdocs build --strict
```

The build checks page links and anchors. `site/` is generated output and is ignored
by Git. A small hook in `tools/docs_hooks.py` includes the repository changelog,
license, screenshot, config template, validation report and offline gallery without
keeping duplicate source copies. Only these explicitly selected files are published;
other local experiments under `work/` are not included.

Regenerate the gallery when its fixtures or rendering change:

```sh
uv run --extra browser python work/browser_examples.py
```

## Publishing

The Pages workflow builds documentation on pull requests and publishes on pushes
to `main`, or a manual workflow run on `main`. Deployments use the `github-pages`
environment and GitHub's artifact-based Pages actions. Concurrent publishes are
serialized so an in-flight deployment is allowed to finish. No PyPI release or
version bump is needed for documentation-only changes.
