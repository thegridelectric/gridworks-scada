# gridworks-scada-protocol

This package contains data structures used in messages between [gridworks-scada]
devices, the gridworks Ltn and the [gridworks-admin].

## Sema conformance

The named types in this package are hand-written twins of vocabulary words in
the [sema] registry, and sema is the contract: each type's docstring carries
its schema URL (`Sema: https://schemas.electricity.works/types/<name>/<version>`),
and a serialized instance must pass `sema validate`.

The conformance sweep lives here (`gwsproto_sema_conformance.py`) and checks
the whole package at once. From this directory, with a sema checkout in a
sibling directory of the repo:

    uv run python gwsproto_sema_conformance.py

It walks every named type and reports, per type: no sema word registered,
version drift against sema's latest, sema examples the class rejects, and
re-serializations that are not byte-identical to the canonical example. It
prints which sema branch it read, and exits non-zero on any real mismatch.
Run it whenever types change on either side.

The sweep also runs in reverse against `sema_closure/registry.yaml`, a
vendored copy of the tlayouts snapshot registry (the layout words' dependency
closure): every word a layout artifact can carry must have a twin here at the
closure's version. Refresh the copy whenever tlayouts regenerates its snapshot;
the pytest conformance test fails if the copy is missing or a closure word has
no twin.

Two additional modes:

- `--cli` — also pushes each clean re-dump through `sema validate`, so the
  canonical sema runtime is the judge rather than a structural comparison.
- `--release-gate` — every type's pinned version must have sema status
  `published`. Staging vocabulary is mutable and allowed on dev brokers
  only, so this gate must pass before any deploy that talks to a hybrid or
  production broker.

[gridworks-scada]: https://github.com/thegridelectric/gridworks-scada 
[gridworks-admin]: https://pypi.org/project/gridworks-admin/
[sema]: https://github.com/thegridelectric/sema