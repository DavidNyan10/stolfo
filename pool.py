"""
Customized Wavelink Node, NodePool and Websocket classes to support my use case.
Huge thanks to the Pythonista people for the library (and for being awesome in general! <3)

MIT License

Copyright (c) 2019-2021 PythonistaGuild

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import json
import logging
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    TypeVar,
)

import discord
from wavelink import abc, Node as _Node, NodePool as _NodePool, Stats
from wavelink.errors import *
from wavelink.utils import MISSING
from wavelink.websocket import Websocket as _Websocket

from track import Track

if TYPE_CHECKING:
    from wavelink.ext import spotify


__all__ = (
    "Node",
    "NodePool",
)


PT = TypeVar("PT", bound=abc.Playable)
PLT = TypeVar("PLT", bound=abc.Playlist)


logger: logging.Logger = logging.getLogger(__name__)


class Websocket(_Websocket):
    async def process_data(self, data: Dict[str, Any]) -> None:
        op = data.get("op", None)
        if not op:
            return

        if op == "stats":
            self.node.stats = Stats(self.node, data)
            return

        try:
            player = self.node.get_player(self.node.bot.get_guild(
                int(data["guildId"])))  # type: ignore
        except KeyError:
            return

        if player is None:
            return

        if op == 'event':
            event, payload = await self._get_event_payload(data['type'], data)
            logger.debug(f'op: event:: {data}')

            # Use the actual track.Track instance that started playing to keep its context
            if event == "track_start":
                payload["track"] = player.source

            self.dispatch(event, player, **payload)

        elif op == "playerUpdate":
            logger.debug(f"op: playerUpdate:: {data}")
            try:
                await player.update_state(data)
            except KeyError:
                pass


class Node(_Node):
    async def _connect(self) -> None:
        self._websocket = Websocket(node=self)

        await self._websocket.connect()


class NodePool(_NodePool):
    @classmethod
    async def create_node(
        cls,
        *,
        bot: discord.Client,
        host: str,
        port: int,
        password: str,
        https: bool = False,
        heartbeat: float = 30,
        region: Optional[discord.VoiceRegion] = None,
        spotify_client: Optional[spotify.SpotifyClient] = None,
        identifier: str = MISSING,
        dumps: Callable[[Any], str] = json.dumps,
    ) -> Node:
        if identifier is MISSING:
            identifier = os.urandom(8).hex()

        if identifier in cls._nodes:
            raise NodeOccupied(
                f"A node with identifier <{identifier}> already exists in this pool."
            )

        node = Node(
            bot=bot,
            host=host,
            port=port,
            password=password,
            https=https,
            heartbeat=heartbeat,
            region=region,
            spotify=spotify_client,
            identifier=identifier,
            dumps=dumps,
        )

        cls._nodes[identifier] = node
        await node._connect()

        return node
