# The scada and its LTN: the dispatch contract

What this is: a plain explanation of the agreement between a GridWorks
scada and the Leaf Transactive Node (LTN) that represents its house in
the market, for an engineer or operator who needs to know why a house
is or is not under dispatch and what the two sides say to each other.

## The relationship

The LTN stands for the house in the electricity market. Each hour it
works out how much energy the house should take in the coming hour and
offers the scada a slow dispatch contract: a start time, a duration, an
average power, and whether the oil boiler is on. The offer is a
`slow.contract.heartbeat` with status `Created`, sent in the first ten
seconds after the top of the hour, and only when the LTN has a price in
hand.

The scada decides at the offer whether it can serve the contract. If it
cannot, it answers with a single reason and nothing else moves. If it
can, it takes the contract, hands the house to its leaf ally, and from
then on answers each LTN heartbeat with one of its own that reports the
energy used so far. When the hour ends the scada sends a completion
heartbeat and the LTN may offer the next contract. If something happens
mid-hour that stops the scada serving it, the scada sends a
terminating heartbeat with the reason, and the contract is over.

The design principle on both sides is that the LTN never has to guess.
Every refusal and every termination names one reason from one fixed
vocabulary, and the scada keeps a standing report of the same answer so
the LTN can see, between offers, whether the house accepts dispatch.

## Where the answer comes from

One function on the Scada actor, `dispatch_refusal`, returns the reason
the scada will not take or keep a contract, or `None` when it takes
one. It is computed each time it is asked and never stored. Every
reader of "does this scada dispatch" calls it: the offer handler, the
check on each heartbeat of a held contract, the decision whether to
resume a stored contract after a restart, and the operating status the
scada reports. Because there is one function, the standing view and the
per-offer answer cannot disagree.

The reasons, in the order the function checks them:

| Reason | What is true |
|---|---|
| `NoTaDeed` | The deed on file does not give this terminal asset standing to trade |
| `OperatorHold` | The operational params say the operator holds the house out of dispatch |
| `ServiceContractBroken` | The operational params say the service contract stands broken |
| `ScadaBlind` | A channel the layout family's control requires is disabled in the layout or its reading is stale |
| `InAdmin` | An admin session runs the house |

The order is by permanence, most permanent first. A deed is issued by a
third party and changes rarely; an operator's hold is a person's
decision; a broken service contract stays broken until a person clears
it; sensing comes and goes; an admin session is over in hours. When
more than one is true, the reported reason is the one that will still
be true tomorrow, so a log line or a status read a day later still
explains the house.

Standby is not a reason of its own. The operational params word has an
axiom that Standby implies `OperatorHold`, so a house in standby
refuses as a held house.

## The TaDeed

The deed is the first and highest authority over whether a scada
trades at all. Holds, service contracts and running state are consulted
only once the deed says the terminal asset has standing in a market.

A `ta.deed` is a TaValidator's attestation of what a terminal asset is.
A TaValidator is an independent third party that checks that the asset
is a physical load drawing electricity, and that it draws it where its
alias and GPS say it does. The deed records the asset's GNodeId
(`TaId`), its GNode alias at issue (`TaAlias`), the validator's alias,
when it was issued, and the finding, a `ValidationState`. The finding
is what decides. A deed file on disk grants nothing by being there.

The validation states are `UnValidated` (nothing attested; the scada's
own default when it has no deed), `ValidatedRealAssetAndGps` (a real
load at its declared place), `ValidatedRealAssetIncorrectGps` (a real
load, not at its declared place, for example a bench running against a
real universe's prices), and `ValidatedSimulatedAsset` (no electricity
drawn anywhere). A simulated-asset deed never names an alias in the
world universe; the deed word's own axiom enforces that. The scada adds
no clause of its own about simulation, since a hardware-in-the-loop
house is a real asset.

The deed reaches the scada as a file, `ta-deed.json`, in the scada's
config folder beside `hardware-layout.json` and
`operational-params.json`. The deed has no signature field. It is
trusted because of where it sits, not by cryptography; when deeds are
signed, `deed_grants_dispatch` in `sema_to_dc.py` is where the
verification goes.

That function is the whole of the scada's deed check. It is true when
a deed is on file, its `TaId` and `TaAlias` both name the layout's
terminal asset, and its `ValidationState` is anything other than
`UnValidated`. Any validated state grants dispatch. The file is read at
each check, so a deed that goes away mid-run is noticed at the next LTN
heartbeat, and a held contract ends with `NoTaDeed`.

Once per run, after its first weather forecast, the scada sends the LTN
its deed. If it has no usable deed it sends a Warning glitch instead,
`no-ta-deed` when the file is missing or `ta-deed-wrong-asset` when the
file names another terminal asset. The scada's `ValidationState` also
appears on its operating status.

## The operational params: DispatchHold

The second authority is the house's operational params file. Its
`DispatchHold` field is two booleans, each a fact its writer owns.

`OperatorHold` belongs to a person. It means the operator holds the
house out of dispatch, and only a person edits it.

`ServiceContractBroken` belongs to the scada's cold latch, and only a
person clears it. The service contract is the agreement between the
homeowner and the aggregator that the house will be kept warm. When the
cold watch finds the house cold with its stores empty while a dispatch
contract is held, the scada has broken that agreement. It sets
`ServiceContractBroken` in the params it runs and in the file on disk,
reports the refusal on its operating status, and ends the contract with
`ServiceContractBroken`. From then on every offer is refused with that
reason, across restarts, until a person edits the file. A scada holding
no contract when the house goes cold has broken nothing and changes
nothing; a scada that already refuses dispatch keeps its reason.

This is the one place the running scada writes to a file. Nothing else
writes across: the deed is never copied anywhere, and the params file
never records what the layout says. The file states a hold, not the
answer; whether the scada accepts dispatch is derived everywhere and
stored nowhere.

## The sensing: ScadaBlind

Each layout family has a short list of channels its control needs in
order to act as a leaf ally. For the House0 family these are the
effective buffer temperature depths; for the Nolan family, the band
sensors at depths one and three. The list is `dispatch_channels` in
`actors/hydronic/shared.py`, and one predicate beside it, `buffer_fresh`,
answers whether every channel on it has a reading inside the channel's
freshness bound (2.1 capture periods). A channel never read, or flushed
because it flatlined, is stale.

That predicate is the one availability answer. The dispatch gate asks
it at the offer and at each heartbeat of a held contract. Local control
asks it for its own data-available judgment. The derived generator
asks it before estimating energy. The leaf ally waits on it once, at
the start of a contract, through a one-shot event the scada sets the
first time the predicate is true.

A channel on the list that the layout disables never arrives, so the
scada is blind from boot and refuses every offer for the whole run.
That is knowable from the deployed files before the scada starts, and
the daily `disabled-roster` glitch names the channels when the disabled
set overlaps the required one. A layout with no buffer tank has no
dispatch channels to be fresh and is blind for the run; families without
tanks name their own set when they arrive.

`ScadaBlind` is a derived, scada-level fact. It goes on the operating
status beside `TopState`, so the LTN's standing view says blind and the
per-offer rejection is the backstop.

## How the LTN sees it

The scada reports a `gw.house.operating.status` to the LTN whenever any
field of it changes (the first send always goes). It states the
`ValidationState`, standby and service mode, `AcceptsDispatch` with the
`DispatchRefusalReason` when there is one, the scada's `TopState`,
`ScadaBlind`, and whether the LTN is currently dispatching. This is the
standing view: what the LTN can read between offers.

The per-offer answer is one of two messages, in the same vocabulary.

A rejection before the contract exists. When a `Created` heartbeat
arrives and `dispatch_refusal` returns a reason, the scada sends a
`slow.contract.rejection` naming the contract and the reason, and
returns. No heartbeat is stored, no timer starts, the scada's auto state
stays where it is, and no grace period follows. The LTN drops its
pending heartbeat and deletes its stored copy, so the rejected offer is
neither resent nor reloaded. It may offer again at its next price.

A termination after. When the scada holds a contract and something
stops it serving it, `end_contract` sends a `slow.contract.heartbeat` with status
`TerminatedByScada`, the reason from the same vocabulary, and a
free-text cause. The scada stores that heartbeat so a restart finds a
finished contract, then forgets it so it holds none. The LTN records
the energy used and clears its own copy. Terminations come from the
cold latch, a deed lost mid-contract, a required channel gone stale
mid-contract, a stored contract not resumed at restart because the
answer now refuses, admin taking the house, and the ally itself giving
up.

A terminated contract is never restarted, on either side. The scada
holds none after `end_contract`; the LTN holds none after the
terminating heartbeat. Dispatch resumes only with a fresh offer.

## Admin

When someone takes the house into admin, the scada ends the contract it
holds on the way in. It tells the LTN the contract is terminated, with
`InAdmin` as the reason, and stores that so a restart during the
session finds a finished contract. Only then does the auto state go
dormant; local control is not woken on the way. While the session runs,
any offer is refused with the same reason, and the operating status says
so. When admin times out or releases, the scada wakes back into local
control holding no contract, reports that it accepts dispatch again,
and takes the next offer the LTN makes. The LTN only offers at the top
of the hour, so an admin session costs the rest of that hour in local
control. That is accepted: five-minute contracts may come, and an
occasional admin session is not a problem at scale.

## Startup

The LTN cannot offer until it has the scada's layout, which the scada
announces once per run along with its deed and operating status. The
scada sends that announcement only after its upstream link can publish
and after it holds its first heating forecast. The leaf ally's first
judgment under a contract depends on a forecast (without one, its
buffer-empty test answers no and its buffer-full test falls back to a
default), so this order guarantees that the ally's first judgment under
a contract has a forecast to work from. The ally also waits for both
facts itself before judging, since an LTN that already has the layout
from an earlier run can offer at its next price regardless.

A contract stored from before a restart waits for the same forecast
before it is resumed. The resume runs as its own task a few seconds
into the run; until it has run, LTN continuation heartbeats for the
loaded contract are logged and dropped. When it runs, the scada asks
`dispatch_refusal` once more. If the answer refuses, the stored contract
ends with a terminating heartbeat and the leaf ally hears nothing. If it
accepts, the contract goes live and the ally takes it. An offer that
arrives in those first seconds takes the loaded contract's place.

Every contract the ally gets passes through one helper,
`send_contract_to_ally`, which checks `dispatch_refusal` first. The
offer handler, the resume, and the resend when the ally is found
dormant all go through it, so a scada that refuses dispatch gives the
contract up for the reason instead of handing it on.

## Glossary

TaDeed. A TaValidator's attestation of what a terminal asset is, kept
as `ta-deed.json` in the scada's config folder. Its `ValidationState`
is what grants standing to trade.

Terminal asset. The electrical load the house presents to the grid,
identified by a GNodeId and a GNode alias; the thing the deed is about
and the thing the LTN represents.

LTN. Leaf Transactive Node. The service that represents the house in
the market, holds its price, and offers the scada one slow dispatch
contract per hour.

Leaf ally. The actor inside the scada that runs the house under a
dispatch contract, making the hourly energy target happen with the
equipment it has.

Local control. The actor that runs the house when no contract is held:
on boot, between contracts, after a refusal or termination, and after
an admin session ends.

Admin. A person taking direct command of the house's actuators for a
bounded session. The scada's `TopState` is `Admin` for its duration;
its auto state is dormant.
