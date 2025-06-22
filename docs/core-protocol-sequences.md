# Core Scada protocol message sequences

This document gives a high-level sketch of core message flows between the Scada, the Atomic Transactive Node (`Atn`)
and various other "actors" running on the Scada or in the home. 

What we describe below are standard patterns of messages, where one message will (usually) trigger the next


### Meter aggregate power change

    Meter   ->  PowerWatts                       ->  Scada 
    Scada   ->  PowerWatts                       ->  Atn            

See description [here](https://github.com/thegridelectric/gridworks-scada/blob/main/gw_spaceheat/actors/scada.py#L253).

Milliseconds matter for Scada responsiveness with PowerWatts. The Scada will not, for example, request an ack
from the `Atn` for receipt of the `PowerWatts`. Note also that the `PowerWatts` does not have a timestamp.


### Scada 5 minute Status report

    Scada   ->  GtShStatus                  ->  Atn
    Scada   ->  SnapshotSpaceheat           ->  Atn

The `GtShStatus` message contains all the telemetry updates received by the Scada in the last 5 minutes.
The `SnapshotSpaceheeat` contains the latest telemetry status for all known telemetry points.


### Meter asynchronous telemetry

    Meter   ->  GtShTelemetryFromMultipurposeSensor                  ->  Scada 
    
The primary power meter is the most important example of a [multipurpose sensors](docs/multipurpose-sensor.md). 

The trigger for the power meter reporting a new power reading is a fractional change of the maximum rated power. 
FILL THIS IN.

### Atn dispatches relay

    Atn     ->  GtDispatchBoolean           ->  Scada

    (As long as the `Atn-Scada dispatch contract is live) 

    Scada   ->  GtDispatchBooleanLocal      ->  Relay

    (and then usually, as long as the relay driver code is working and the relay
    state does in fact change)

    Relay   ->  GtTelemetry                 ->  Scada

The relay (aka BooleanActuator) has two core functions. It is waiting for commands
from the scada, and it is also tracking the state of the relay. The GtTelemetry message
is sent when the relay state changes.

Assuming the relay follows the command from the Scada _and_ the state of the relay does 
in fact change, an atn dispatch command will be followed shortly by a GtTelemetry from 
the relay.

### Atn requests status

    Atn     ->  SendSnap              ->  Scada
    Scada   ->  SnapshotSpaceheat           ->  Atn

This a maintenance command for humans to immediately see `SnapshotSpaceheat` from the Scada instead of 
waiting for 5 minutes. 

### HomeAlone incomplete fragment

    Home    ->  GtDispatchBooleanLocal      -> Scada

    (As long as the `Atn-Scada dispatch contract is NOT live) 

    Scada   ->  GtDispatchBooleanLocal      ->  Relay

    (and then usually, as long as the relay driver code is working and the relay
    state does in fact change)

    Relay   ->  GtTelemetry                 ->  Scada