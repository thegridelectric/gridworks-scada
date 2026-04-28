from actors.sieg_loop.fallback import SiegLoopFallback
from actors.sieg_loop.pid import SiegLoopPid

def __getattr__(name: str):
    if name == "SiegLoop":
        from actors.sieg_loop_loader import SiegLoop

        return SiegLoop
    raise AttributeError(name)


__all__ = [
    "SiegLoop",
    "SiegLoopFallback",
    "SiegLoopPid",
]
