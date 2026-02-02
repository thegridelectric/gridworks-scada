import asyncio

from actors.sh_node_actor import ShNodeActor


class Gw108ThermistorBoard(ShNodeActor):
    def start(self):
        self._task = asyncio.create_task(self.main())

    async def main(self):
        while not self._stop_requested:
            readings = await asyncio.to_thread(self.read_all_temps_sync)
            self.emit(readings)
            await asyncio.sleep(self.period)