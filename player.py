from random import shuffle
from typing import Optional

from discord import Client, Message, TextChannel, VoiceChannel
from wavelink import Player, WaitQueue


class QueuePlayer(Player):
    bound_channel: Optional[TextChannel]
    np_message: Optional[Message]

    def __init__(self, client: Client, channel: VoiceChannel):
        super().__init__(client, channel)
        self.bound_channel: Optional[TextChannel] = None
        self.shuffled_queue: Optional[WaitQueue] = None

        self.shuffle = False
        self.shuffled_queue: Optional[WaitQueue] = None
        self.queue = WaitQueue()

        self.has_started = False
        self.np_message = None

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.guild == other.guild

    def set_shuffle(self, state: bool):
        self.shuffle = state

        if state is True:
            self.shuffled_queue = WaitQueue()
            self.shuffled_queue.extend(self.queue)
            shuffle(self.shuffled_queue._queue)
        else:
            self.shuffled_queue = None
