import asyncio
import re
from typing import Type, Union
from urllib import parse
from discord.ext import commands

import lavalink
from discord import Color
from discord.embeds import _EmptyEmbed, EmptyEmbed
from discord.ext.commands import Cog, CommandError, CommandInvokeError
from lavalink import AudioTrack, DefaultPlayer, format_time, QueueEndEvent, TrackStartEvent

from bot import Bot
from context import Context
from lavalink_voice_client import LavalinkVoiceClient

URL_RE = re.compile(r"https?://(?:www\.)?.+")


class UserError(CommandError):
    def __init__(self, message: str):
        self.message = message


class Music(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        lavalink.add_event_hook(self.track_hook)

    def cog_unload(self):
        self.bot.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx: Context):
        if (is_guild := ctx.guild is not None):
            await self.ensure_voice(ctx)
        return is_guild

    async def cog_command_error(self, ctx: Context, error: Type[CommandError]):
        if isinstance(error, UserError):
            await ctx.send(embed=ctx.embed(error.message))
        elif isinstance(error, CommandInvokeError):
            error = error.original
            embed = ctx.embed(f"{error.__class__.__name__}: {error}")
            embed.color = Color(0xFF0E0E)
            await ctx.send(embed=embed)

    def get_embed_thumbnail(self, url: str) -> Union[str, _EmptyEmbed]:
        if "youtube.com" in url:
            video_id = parse.parse_qs(parse.urlsplit(url).query)["v"][0]
        elif "youtu.be" in url:
            video_id = parse.urlsplit(url).path.replace("/", "")
        else:
            return EmptyEmbed

        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    def get_player(self, guild_id: int) -> DefaultPlayer:
        return self.bot.lavalink.player_manager.get(guild_id)

    async def track_hook(self, event: lavalink.Event):
        if isinstance(event, TrackStartEvent):
            track: AudioTrack = event.track
            ctx: Context = track.extra["context"]

            if track.stream:
                duration = f"🔴 Live"
            else:
                duration = format_time(track.duration)

            embed = ctx.embed(
                f"Now playing: {track.title}",
                url=track.uri,
                thumbnail_url=self.get_embed_thumbnail(track.uri)
            )
            embed.add_field(name="Duration", value=duration)
            embed.add_field(name="Requested by", value=ctx.author.mention)

            await ctx.send(embed=embed)

        elif isinstance(event, QueueEndEvent):
            player: DefaultPlayer = event.player
            try:
                await self.bot.wait_for(
                    "command",
                    check=lambda ctx: ctx.cog == self and ctx.guild.id == int(player.guild_id),
                    timeout=300
                )
            except asyncio.TimeoutError:
                guild = self.bot.get_guild(int(player.guild_id))
                await guild.voice_client.disconnect(force=True)

    async def ensure_voice(self, ctx: Context):
        player: DefaultPlayer = self.bot.lavalink.player_manager.create(
            ctx.guild.id, endpoint=str(ctx.guild.region)
        )
        should_connect = ctx.command.name in ("play",)

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise UserError("You're not connected to a voice channel!")

        if not player.is_connected:
            if not should_connect:
                raise UserError("I'm not connected to a voice channel!")

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect:
                raise UserError(
                    "I'm missing permissions to connect to your voice channel!"
                )

            if not permissions.speak:
                raise UserError("I'm missing permissions to speak in your voice channel!")

            player.store("channel", ctx.channel.id)
            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if int(player.channel_id) != ctx.author.voice.channel.id:
                raise UserError("You need to be in my voice channel to use this!")

    @commands.command(aliases=["p"])
    @commands.max_concurrency(1, commands.BucketType.guild, wait=True)
    async def play(self, ctx: Context, *, query: str):
        player = self.get_player(ctx.guild.id)
        query = query.strip("<>")

        if not URL_RE.match(query):
            query = f"ytsearch:{query}"

        if not (results := await player.node.get_tracks(query)) or not results["tracks"]:
            raise UserError("Nothing found!")

        if results["loadType"] == "PLAYLIST_LOADED":
            tracks = results["tracks"]
            first_position = len(player.queue) + 1

            for track in tracks:
                player.add(
                    requester=ctx.author.id,
                    track=AudioTrack(track, ctx.author.id, context=ctx)
                )

            last_position = len(player.queue)

            embed = ctx.embed(
                f"Queued {results['playlistInfo']['name']} - {len(tracks)} tracks",
                url=query
            )
            embed.add_field(name="Duration", value=format_time(
                sum(t["info"]["length"] for t in tracks)
            ))
            embed.add_field(name="Position in queue", value=f"{first_position}-{last_position}")

            await ctx.send(embed=embed)
        else:
            track = results["tracks"][0]
            player.add(
                requester=ctx.author.id,
                track=AudioTrack(track, ctx.author.id, context=ctx)
            )
            if player.is_playing:
                if track["info"]["isStream"]:
                    duration = f"🔴 Live"
                else:
                    duration = format_time(track["info"]["length"])

                embed = ctx.embed(
                    f"Queued {track['info']['title']}",
                    url=track["info"]["uri"],
                    thumbnail_url=self.get_embed_thumbnail(track["info"]["uri"])
                )
                embed.add_field(name="Duration", value=duration)
                embed.add_field(name="Position in queue", value=len(player.queue))

                await ctx.send(embed=embed)

        if not player.is_playing:
            await player.play()

    @commands.command(aliases=["dc", "stop", "leave"])
    async def disconnect(self, ctx: Context):
        player = self.get_player(ctx.guild.id)

        player.queue.clear()
        await player.stop()
        await ctx.guild.voice_client.disconnect(force=True)

        embed = ctx.embed(f"Disconnected from {ctx.author.voice.channel.name}!")
        await ctx.send(embed=embed)

    @commands.command(aliases=["s"])
    async def skip(self, ctx: Context):
        player = self.get_player(ctx.guild.id)

        embed = ctx.embed(f"Skipped {player.current.title}")
        await player.stop()
        await ctx.send(embed=embed)


def setup(bot: Bot):
    bot.add_cog(Music(bot))
