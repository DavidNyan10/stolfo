from typing import Type

from discord import Client, VoiceChannel
from pomice import Player

from .queue import WaitQueue


class QueuePlayer(Player):
    def __init__(self, client: Type[Client], channel: VoiceChannel):
        super().__init__(client, channel)
        self.queue = WaitQueue()
