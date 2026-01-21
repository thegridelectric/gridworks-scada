"""
Procedural, non-transactive interrupts
-------------------------------------

These procedures are designed to perform short-duration corrective actions
without interfering with transactive dispatch or hierarchical state machines.

Characteristics:
- Emit warning-level glitches when they begin (for auditability)
- Do NOT transition or override FSMs (top-level or local)
- Intended to complete quickly (typically < 1 minute)
- MUST NOT actuate transactive load-control relays
- May temporarily manipulate local relays or analog outputs
- Must be watchdog-safe

Examples:
- DistPumpDoctor
- StorePumpDoctor
"""