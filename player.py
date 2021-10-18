from random import shuffle
from typing import Optional, Type

from discord import Client, VoiceChannel
from pomice import Player, Track

from queues import WaitQueue


class QueuePlayer(Player):
    def __init__(self, client: Type[Client], channel: VoiceChannel):
        super().__init__(client, channel)
        self.shuffled_queue: Optional[WaitQueue]

        self.shuffle = False
        self.shuffled_queue = None
        self.queue = WaitQueue()

    def set_shuffle(self, state: bool):
        self.shuffle = state

        if state is True:
            self.shuffled_queue = WaitQueue()
            self.shuffled_queue.extend(self.queue)
            shuffle(self.shuffled_queue._queue)
        else:
            self.shuffled_queue = None

    async def on_voice_server_update(self, data):
        await super().on_voice_server_update(data)
        print(data)

    async def on_voice_state_update(self, data):
        self._voice_state["event"].update(data)
        await super().on_voice_state_update(data)
        print(self._voice_state)
