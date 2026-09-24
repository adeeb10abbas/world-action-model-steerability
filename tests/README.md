# Clean study test scope

Run `uv run pytest` from the repository root for the explicit portable CPU subset in [pyproject.toml](../pyproject.toml). It covers the frozen contract and scorer, clean scene authoring, adapters, recorder, annotations, compiler, scene packaging and synthetic production integration. These checks do not start a learned policy or simulator and do not establish native model qualification.

See the [repository setup](../README.md), [runtime prerequisites](../docs/STANDALONE_RUNTIME.md) and [cluster handoff](../docs/CLUSTER_HANDOFF.md) for the corresponding execution boundaries.

Optional tests remain outside the default subset when they require external prerequisites. Native/source-backed checks may need Torch, authorized model sources, a pinned simulator installation or Linux process identity. Archive checks require a tar implementation with zstd support. The CPU test extra includes `usd-core` for authored USD geometry checks; it does not install Isaac.

Disconnected historical audit and MAIN-P tests were removed with their unused source; [the exclusion record](../provenance/legacy-source-exclusion.json) lists exact paths and hashes. Shared geometry helpers and their tests remain where current source imports them. Some mixed optional modules still contain individual tests requiring unavailable source-era records; that does not make their current runtime/geometry coverage disposable. Select optional tests only when their named prerequisites exist, and keep missing-evidence skips separate from native validation.

Do not fabricate missing evidence or alter frozen inputs to satisfy a test. Add portable clean-scene checks to the explicit default subset when integrated. Keep native qualification, scripted scene feasibility and learned-policy outcomes separate in reports.
