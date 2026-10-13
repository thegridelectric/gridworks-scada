# gridworks-scada-protocol

This package contains data structures used in messages between [gridworks-scada]
devices, the gridworks Ltn and the [gridworks-admin].

## Sema conformance

The named types in this package are hand-written twins of vocabulary words in
the [sema] registry, and sema is the contract: each type's docstring carries
its schema URL (`Sema: https://schemas.electricity.works/types/<name>/<version>`),
and a serialized instance must pass `sema validate`.

The package vendors its own sema snapshot, `sema_snapshot/sema`: every word
the scada speaks, at the version it speaks, with sema's generated classes and
canonical samples. `sema_seed_request.yaml` is the seed and
`scripts/regen_sema_snapshot.sh` (repo root) regenerates the snapshot from a
sibling sema checkout; the snapshot is committed, so a diff shows the
vocabulary a scada release speaks. The snapshot is a test oracle, never
shipped and never run against a broker.

The conformance sweep lives here (`gwsproto_sema_conformance.py`) and checks
the whole package against the snapshot. From this directory:

    uv run python gwsproto_sema_conformance.py

It walks every named type and reports, per type: no snapshot word, version
drift against the snapshot, no snapshot class at the pinned version, shape
drift (serialized field names or required set differ from the snapshot
class), samples the class rejects, and re-serializations that are not
byte-identical to the canonical sample; per enum, value drift; per format,
examples refused or counterexamples accepted; and in reverse, every snapshot
word with no twin. It exits non-zero on any real mismatch. Run it whenever
types change on either side; the pytest conformance test runs it with an
exact allowlist of known debt.

The named-types tests go further through `tests/named_types/sema_oracle.py`:
every instance a test builds must decode through the snapshot codec and
re-encode identically, and every payload a twin refuses the snapshot must
refuse on the same axiom.

One additional mode, `--cli`, also pushes each clean re-dump through
`sema validate` in a sibling sema checkout, so the canonical sema runtime is
the judge rather than the vendored copy. There is no release gate: staging
vocabulary is allowed on dev brokers only, and the snapshot's
`indexes/staging.yaml` lists the staging words to check by hand before a
deploy that talks to a hybrid or production broker.

[gridworks-scada]: https://github.com/thegridelectric/gridworks-scada 
[gridworks-admin]: https://pypi.org/project/gridworks-admin/
[sema]: https://github.com/thegridelectric/sema