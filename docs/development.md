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
license, screenshot, config template, validation report and offline gallery. The
gallery and validation source live in `docs/_source/`; local experiments in `work/`
are not required to build or publish the documentation.

Regenerate the gallery when its fixtures or rendering change:

```sh
uv run --extra browser python tools/browser_examples.py
```

## Regenerate the TUI image

The checked-in image uses the actual Textual controls and chart PNG, with
synthetic demo observations. Regenerate it from the repository root:

```sh
env -u NO_COLOR uv run python tools/capture_tui.py
cp work/tui-preview.png docs/assets/termseries-tui.png
```

The capture exports SVG and metadata under `work/`. PNG conversion uses
`rsvg-convert` from librsvg; CI publishes the checked-in PNG and does not need that
system tool. Intermediate preview files do not need to be committed.

## Publishing

The Pages workflow builds documentation on pull requests and publishes on pushes
to `main`, or a manual workflow run on `main`. Deployments use the `github-pages`
environment and GitHub's artifact-based Pages actions. Concurrent publishes are
serialized so an in-flight deployment is allowed to finish. No PyPI release or
version bump is needed for documentation-only changes.

## PyPI releases and provenance

The separate `Publish` workflow runs when a GitHub release is published. It builds
the wheel and source archive with `uv build`, then uses the pinned PyPA publishing
action with Trusted Publishing and signed PEP 740 attestations enabled. No package
is published just by pushing a branch or merging a pull request.

The PyPI project's Trusted Publisher must allow repository `deeplook/termseries`
and workflow `publish.yml`. The workflow currently has no GitHub environment, so
the publisher's optional environment field should be left unset. The repository
workflow grants `id-token: write`; it does not use a long-lived PyPI API token.

See [PyPI's attestation guide](https://docs.pypi.org/attestations/producing-attestations/)
for how attestations are created and [Trusted Publisher configuration](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
for the PyPI-side settings. Those settings are managed separately from this repo.
