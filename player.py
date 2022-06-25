from random import shuffle
from typing import Optional, Type

from discord import Client, TextChannel, VoiceChannel
from pomice import Player

from queues import WaitQueue


class QueuePlayer(Player):
    def __init__(self, client: Type[Client], channel: VoiceChannel):
        super().__init__(client, channel)
        self.bound_channel: TextChannel = None
        self.shuffled_queue: Optional[WaitQueue] = None

        self.shuffle = False
        self.shuffled_queue = None
        self.queue = WaitQueue()

        self.has_started = False

    def __eq__(self, other):
        return self.guild == other.guild

    def set_shuffle(self, state: bool):
        self.shuffle = state

        if state is True:
            self.shuffled_queue = WaitQueue()
            self.shuffled_queue.extend(self.queue)
            shuffle(self.shuffled_queue._queue)
        else:
            self.shuffled_queue = None
