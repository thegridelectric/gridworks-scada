# How a scada refuses or breaks a slow dispatch contract

What this is: the one explanation of why a scada will not take a slow
dispatch contract from its LTN, or ends one it holds, and the one
vocabulary it uses to say so. It describes the dispatch gate as
designed; where the code does not do this yet, the section says so in
one sentence.

The scada does two distinct things with dispatch. It **refuses** slow
dispatch contracts from the start, offer by offer. And it **breaks** a
specific contract it already holds. Both come from one computed answer,
`dispatch_refusal` on the Scada actor, which returns a
`gw.dispatch.refusal.reason` or nothing. It is never stored. Every
reader of "does this scada dispatch" calls it: the offer handler, the
per-heartbeat check on a held contract, the stored-contract decision at
restart, and the house's operating status report, so the LTN's standing
view and the per-offer answer come from the same function.

The authorities over that answer fall in two groups, by when the fact
is knowable. Three are files on the box, each with one owner, decisive
before the scada boots. The rest the running scada observes about
itself.

## The deed

The deed is the first and highest authority over whether a scada
trades. Operator holds, service contracts and running state are only
consulted once the deed says the terminal asset has standing in a
market. Without that standing, nothing else matters.

### What a TaDeed is

A `ta.deed` is a TaValidator's attestation of what a terminal asset is.
It binds the asset's identity to the place in the copper tree it was
validated under, and it records the validator's finding. The finding is
what decides. A deed file on disk grants nothing by being there: every
reader consults its `ValidationState`.

The sema word `ta.deed` has one version, `000`, with status `staging`.
Its fields:

| Field | What it is |
|---|---|
| `TaId` | The terminal asset's GNodeId. This is the fixed anchor the deed binds to. |
| `TaAlias` | The asset's GNode alias at issue. Its first segment is the universe (`w`, `hw1`, `d1`). |
| `ValidationState` | The finding, a `ta.validation.state` value. |
| `ValidatorAlias` | The GNode alias of the TaValidator that made the finding. |
| `IssuedS` | When the deed was issued, in UTC seconds. |

The scada uses two of these fields. It compares `TaId` with the
layout's TerminalAsset GNodeId, and it reads `ValidationState`. The
word has one axiom, `SimulatedAssetNeverWorld`: a
`ValidatedSimulatedAsset` deed never has a `w` alias. The gwsproto twin
enforces it
(`packages/gridworks-scada-protocol/src/gwsproto/named_types/ta_deed.py`).

### How a TaValidator issues one

A TaValidator is an independent third party. It checks that the asset
is a physical load drawing electricity, and that it draws it where its
alias and GPS say it is. The `ta.validation.state` values record what
the validator vouched for.

`ta.deed` 000 has no signature or proof field. So a deed on disk is
trusted because of where it sits, and is not checked by cryptography.
No TaValidator service issues deeds yet; every deed on a box today is
hand-written.

A deed reaches the scada as a file. It is `ta-deed.json` in the scada's
config folder, next to `hardware-layout.json`
(`gw_spaceheat/actors/config.py`, `DEFAULT_TA_DEED_FILE`). How a
validator's deed gets onto a box is not built yet.

### Kinds of deed

| `ValidationState` | What is attested | Where it is valid |
|---|---|---|
| `UnValidated` | Nothing. This is the scada's own default when it has no deed. The asset may send telemetry but has no market standing. | Never written into a deed as a grant |
| `ValidatedRealAssetAndGps` | A physical load drawing electricity at the place its alias and GPS declare | Any universe |
| `ValidatedRealAssetIncorrectGps` | A physical load drawing real electricity, but not at its declared location. For example, a bench running against a real universe's prices. | (not confirmed which universes; read before relying) |
| `ValidatedSimulatedAsset` | No electricity drawn anywhere. The identity declares itself simulated. | Dev and hybrid universes, never `w` |

Which deed states grant dispatch is not settled. The code treats every
validated state as a grant, including `ValidatedRealAssetIncorrectGps`.

### How the scada uses it

At boot, the scada reads the deed at `settings.paths.tadeed`. It uses
the deed only when the deed's `TaId` matches the layout's terminal
asset (`gw_spaceheat/scada_app_interface.py`, `ta_deed`). There are two
ways to have no usable deed: the file is missing, or the deed names
another asset. In either case `validation_state` is `UnValidated`.

Once per run, the scada sends the LTN its deed. If it has no usable
deed, it sends a Warning glitch instead: `no-ta-deed` or
`ta-deed-wrong-asset` (`gw_spaceheat/actors/scada.py`,
`send_startup_announcements`). The scada also reports its
`ValidationState` in `gw.house.operating.status`.

The gate re-reads the deed at every LTN heartbeat. A scada with no
deed, or with a deed that does not grant dispatch, refuses every offer.
If it is holding a contract when that happens, it breaks the contract
with reason `NoTaDeed`.

The code today differs in three ways. It checks only new offers (status
`Created`). It refuses only `UnValidated`. It answers with a rejection
that names the `ValidationState` instead of `NoTaDeed`
(`gw_spaceheat/actors/scada.py`, `process_slow_contract_heartbeat`).

### Simulated deeds

Open: a simulated house has no real validator. The scada test suite
uses hand-written `ValidatedSimulatedAsset` fixtures
(`tests/config/*.ta.deed.json`) issued by `d1.validator.gridworks`. No
service with that alias issues deeds. Three questions are unresolved:

- Who issues a simulated deed?
- Should `ValidatorAlias` name a GNode that exists?
- Should a fixture deed count as attested at all?

## The operational params: DispatchHold

The second file is `gw.operational.params`, the house's tunable state.
Its `DispatchHold` field is a `gw.dispatch.hold`: two booleans, each a
fact its writer owns.

| Field | Owner | Meaning |
|---|---|---|
| `OperatorHold` | a person | The operator holds the house out of dispatch. Standby implies it (the word's axiom 3). |
| `ServiceContractBroken` | the cold latch, cleared by a person | The service contract between the homeowner and the aggregator stands broken. The scada sets it when it finds the house cold; a person clears it by editing the file. |

While either is true the scada refuses every offer, with that reason.
The name says what it is: a hold the file places on dispatch, one of
three authorities, not the answer. The deed and the running scada can
refuse a house that has no hold at all.

The ops word does not say whether the scada accepts dispatch. That is
derived everywhere, never stored.

## The layout: a disabled required channel

The third file is the hardware layout. Each layout family has a short
list of channels its control needs to act as a leaf ally (for Nolan,
the band, depth1 and depth3; for House0, the effective buffer
channels). A channel on that list that the layout disables never
arrives, so the scada is blind for the whole run and refuses every
offer with `ScadaBlind`. This is knowable from the deployed files
before boot, and the daily disabled-roster glitch says so when the
disabled set intersects the required set. The layout's disabled set is
about what the house can serve and is larger than the required set.

## Observed while running

The running code owns the rest. Each refuses an offer and breaks a held
contract.

- **`InAdmin`.** An admin session holds the command tree. Admin waking
  mid-contract ends the contract before the scada goes dormant.
- **`ScadaBlind`.** A required channel has gone stale: its last read
  time is outside the channel's nyquist bound (2.1 capture periods), or
  it has never been read. One predicate in the hydronic layer,
  `buffer_fresh`, answers this for local control, the gate and the ally
  alike.
- **The cold latch.** The moment the service contract breaks, the
  scada breaks the held contract with `ServiceContractBroken` and
  writes `DispatchHold.ServiceContractBroken` into the ops word, so
  every later offer is refused. This is the one place the running code
  writes to a file. Nothing else writes across: the deed is never
  copied, and the ops word never copies the layout.

## Precedence

Ordered by permanence, most permanent first, so a log line names the
reason that will still be true tomorrow.

| # | Fact | Reason | Source |
|---|---|---|---|
| 1 | the deed does not grant dispatch | `NoTaDeed` | the deed file, read now |
| 2 | `DispatchHold.OperatorHold` | `OperatorHold` | the ops word |
| 3 | `DispatchHold.ServiceContractBroken` | `ServiceContractBroken` | the ops word; set by the code |
| 4 | a required channel is disabled or not fresh | `ScadaBlind` | the hydronic predicate |
| 5 | `top_state` is Admin | `InAdmin` | the Scada actor |
| | none of the above | the scada takes the contract | |

`Standby` is not a reason: the ops word's axiom makes Standby imply
`OperatorHold`, so a standby house refuses as a held house.

## The two messages

- **A refusal at the offer.** On a `Created` heartbeat with a reason,
  the scada sends `slow.contract.rejection` with the `Reason` and
  returns. Nothing else moves: no heartbeat is stored, no timer starts,
  no grace period follows. The LTN drops its pending heartbeat and may
  offer again at its next price.
- **A termination after.** `TerminatedByScada` is the one path for
  ending a contract the scada holds, and the terminating
  `slow.contract.heartbeat` names the `Reason` in the same enum beside
  its free-text `Cause`. Its cases: the cold latch, a stored contract
  not resumed at restart because the answer now refuses, the deed lost
  mid-contract, a required channel gone stale mid-contract, and Admin
  waking mid-contract.

The per-heartbeat check on a held contract evaluates `dispatch_refusal`
at each LTN heartbeat, the same moment it re-reads the deed. Nothing is
written to the params file by these checks; the deed and the sensing
are the truth and may come back.
