# Hierarchical State Machine Implementation

GridWorks SCADA uses hierarchical state machines to maintain clear control authority while enabling dynamic reassignment of control. Key principles include:

1. **Parent-Child State Coupling**: A node can only be the parent ("boss") of other nodes when it is in a non-dormant state. This creates a natural hierarchy where control authority flows from active to dormant states.

2. **Command Tree Reassignment**: When state changes occur, the parent node can dynamically reassign the command tree at and below it, changing which nodes report to which bosses. This enables flexible control strategies while maintaining clear authority chains. These command tree changes end up in the persistent store via NewCommandTree messages

3. **State-Based Control**: Each actor maintains its own state machine with clearly defined states and transitions. State changes are always immediately preceded by command tree reassignments. They are oftne almost immediately followed by physical actuator commands.


Example: The StatBoss protects thermal stratification during heat pump startup and defrost cycles. It has two states: Dormant and Active. A triggering event moving it from Dormant to Activce could be detecting defrost. This trigger would:
1. Triggers its boss (say `lc.n` for the LocalControl Normal ShNode) to enter a `StratBoss` state
2. Its boss gives it authority over relevant relays aod 010V ctuators through command tree reassignment
3. `StatBoss` is then moved from Dormant to Active, and will be responsible for maintaing good stratifiation in the buffer and store as best it can until a triggering event mooves it back into SDormant (likely detecting a significant lift in temp by the heat pump)

Sometimes the SCADA will be in state where StatBoss could never be triggered to its Active state. For example, if the Scada is missing all of its tank temperature sensor data it will move into a LocalControl ScadaBlind state where the heat pump operates under thermostatic control from a tank aquastat invisible to the SCADA. In the relevant command tree, the `stat-boss` has no boss.  Events triggering Dormant -> Active must all require that `strat-boss` has a boss.


4 **Programming Tip: Don't Doorknob** Doorknobbing is when I'm on the way out the door and I say something in important that deserves more time. In this setting, it means sending an actuation command just before leaving a state. Since actuation commands are passed as messages, they're going to take ~10 ms to be received. If the command tree has changed in that time (which it can do with state change) then the actuator will ignore your doorknobbed message. This can be confounding to debug.