import asyncio
import random
import re
from io import BytesIO
from traceback import format_exception
from typing import Optional, Type, Union

from async_timeout import timeout
from discord import Color, File, HTTPException, Member, TextChannel, VoiceState
from discord.embeds import _EmptyEmbed, EmptyEmbed as Empty
from discord.ext import commands
from discord.ext.commands import Cog, CommandError, CommandInvokeError
from wavelink import NodePool, WaitQueue

import spotify_ext as spotify
from bot import Bot
from config import LOG_CHANNEL
from context import Context
from player import QueuePlayer as Player
from tracks import SearchableTrack, Track, YouTubePlaylist


HH_MM_SS_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{1,2}):(?P<s>\d{1,2})")
MM_SS_RE = re.compile(r"(?P<m>\d{1,2}):(?P<s>\d{1,2})")
HUMAN_RE = re.compile(r"(?:(?P<m>\d+)\s*m\s*)?(?P<s>\d+)\s*[sm]")
OFFSET_RE = re.compile(r"(?P<s>(?:\-|\+)\d+)\s*s", re.IGNORECASE)

YT_SHORTS_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([^\n\r?&/]+)")


def format_time(seconds: Union[float, int]) -> str:
    hours, rem = divmod(int(seconds // 1000), 3600)
    minutes, seconds = divmod(rem, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class UserError(CommandError):
    def __init__(self, message: str):
        self.message = message


class Music(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        if ctx.guild is not None:
            return await self.ensure_voice(ctx)
        raise UserError("Music commands are disabled in DMs.")

    async def ensure_voice(self, ctx: Context):
        assert ctx.command is not None \
           and isinstance(ctx.author, Member) \
           and isinstance(ctx.me, Member) \
           and isinstance(ctx.channel, TextChannel)

        should_connect = ctx.command.name in ("play", "playnext", "playskip", "playshuffle")

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise UserError("You're not connected to a voice channel!")

        channel = ctx.author.voice.channel

        if not ctx.voice_client:
            if not should_connect:
                raise UserError("I'm not connected to a voice channel!")

            permissions = channel.permissions_for(ctx.me)

            if not permissions.connect:
                raise UserError(
                    "I'm missing permissions to connect to your voice channel!"
                )

            if not permissions.speak:
                raise UserError("I'm missing permissions to speak in your voice channel!")

            await channel.connect(cls=Player)
            ctx.voice_client.bound_channel = ctx.channel

            await ctx.send(embed=ctx.embed(
                f"Connected to {channel.name}!",
                f"Music commands are bound to {ctx.channel.mention}."
            ))

        elif int(ctx.voice_client.channel.id) != channel.id:
            raise UserError("You need to be in my voice channel to use this!")

        elif ctx.voice_client.bound_channel and ctx.channel != ctx.voice_client.bound_channel:
            bound_channel = ctx.voice_client.bound_channel
            raise UserError(f"Music commands are currently bound to #{bound_channel.name}.")

    async def cog_command_error(self, ctx: Context, error: Type[CommandError]):
        if isinstance(error, UserError):
            await ctx.send(embed=ctx.embed(error.message))

        elif isinstance(error, CommandInvokeError):
            error = error.original
            embed = ctx.embed(f"{error.__class__.__name__}: {error}")
            embed.color = Color(0xFF0E0E)
            await ctx.send(embed=embed)

            log = self.bot.get_channel(LOG_CHANNEL)
            full_traceback = "".join(
                format_exception(type(error), error, error.__traceback__, chain=True)
            )

            assert ctx.guild is not None and isinstance(log, TextChannel)
            embed = ctx.embed(
                "Command exception caught!",
                f"```python\n{full_traceback}\n```" if len(full_traceback) <= 4000 else Empty
            )
            embed.add_field(name="Message", value=f"`{ctx.message.content}`")
            embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})")

            if len(full_traceback) > 4000:
                file = File(BytesIO(full_traceback.encode("utf-8")), "traceback.txt")
                return await log.send(embed=embed, file=file)

            await log.send(embed=embed)

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if member.id != self.bot.user.id:
            return

        guild = member.guild
        if (player := NodePool.get_node().get_player(guild)) is None:
            return

        if not after.channel:
            return await player.disconnect()

        if player.is_playing() and before.channel != after.channel:
            paused = player.is_paused()

            await player.set_pause(True)
            await asyncio.sleep(1)
            await player.set_pause(paused)

    @Cog.listener()
    async def on_wavelink_track_start(self, player: Player, track: Track):
        ctx = track.ctx
        if player.shuffle:
            player.queue.history.put(track)

        if track.is_stream():
            length = "🔴 Live"
        else:
            length = format_time(track.length * 1000)

        embed = ctx.embed(
            f"Now playing: {track.title}",
            url=track.uri,
            thumbnail_url=self.get_embed_thumbnail(track)
        )
        embed.add_field(name="Duration", value=length)
        embed.add_field(name="Requested by", value=ctx.author.mention)

        assert player.bound_channel is not None
        player.np_message = await player.bound_channel.send(embed=embed)

    @Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: Track, _):
        if player.np_message:
            try:
                await player.np_message.delete()
                player.np_message = None
            except (HTTPException, AttributeError):
                pass

        try:
            async with timeout(300):
                if player.shuffle:
                    assert player.shuffled_queue is not None
                    next_track = await player.shuffled_queue.get_wait()
                    del player.queue[player.queue.find_position(next_track)]
                else:
                    next_track = await player.queue.get_wait()

                try:
                    await player.play(next_track, replace=False)
                except Exception as e:
                    if isinstance(next_track, spotify.PartialSpotifyTrack) \
                       and isinstance(e, IndexError):
                        await player.bound_channel.send(embed=next_track.ctx.embed(
                            f"No results found for Spotify track {next_track} - skipping."
                        ))
                    else:
                        await player.bound_channel.send(embed=next_track.ctx.embed(
                            f"Something went wrong while playing {next_track} - skipping."
                        ))
                        print(e)

                    await self.on_wavelink_track_end(player, next_track, "error playing next")
        except asyncio.TimeoutError:
            if not player.is_playing():
                await player.disconnect()

    def get_embed_thumbnail(self, track: Track) -> Union[str, _EmptyEmbed]:
        if (thumbnail := getattr(track, "thumbnail")) is not None:
            return thumbnail
        elif any(i in track.uri for i in ("youtu.be", "youtube.com")):
            return f"https://img.youtube.com/vi/{track.identifier}/mqdefault.jpg"
        else:
            return Empty

    def format_queue(self, queue: WaitQueue[Track]) -> list[str]:
        items = []
        for i, track in enumerate(queue):
            items.append(
                f"**{i + 1}: [{track.title}]({track.uri}) **"
                f"[{'stream' if track.is_stream else format_time(track.length * 1000)}] "
                f"({track.ctx.author.mention})"
            )

        return items

    async def get_tracks(self, ctx: Context, query: str) -> Union[list[Track], YouTubePlaylist]:
        query = query.strip("< >")

        # patch youtube.com/shorts links to their video counterparts
        if YT_SHORTS_RE.match(query):
            query = YT_SHORTS_RE.sub(r"https://youtube.com/watch?v=\1", query)
        elif (match := spotify.URLREGEX.match(query)):
            if match["type"] == "track":
                return await spotify.SpotifyTrack.search(
                    query, return_first=False, ctx=ctx
                )  # type: ignore
            elif match["type"] in ("album", "playlist"):
                return [
                    track async for track in spotify.SpotifyTrack.iterator(
                        query=query, partial_tracks=True, ctx=ctx
                    )
                ]
            else:
                raise UserError("Only Spotify tracks, albums, and playlists are supported.")
        return await SearchableTrack.search(query, return_first=False)  # type: ignore

    async def send_play_command_embed(self, ctx: Context, search: Union[Track, YouTubePlaylist]):
        assert ctx.command is not None
        if isinstance(search, YouTubePlaylist):
            if ctx.command.name in ("playnext", "playskip"):
                last_position = len(search.tracks)
                first_position = 1
            else:
                last_position = len(ctx.voice_client.queue)
                first_position = last_position - len(search.tracks) + 1

            word = "Shuffled" if ctx.command.name == "playshuffle" else "Queued"

            embed = ctx.embed(
                f"{word} {search.name} - {len(search.tracks)} tracks",
                url=Empty,
                thumbnail_url=Empty
            )

            if any(t.is_stream() for t in search.tracks):
                embed.add_field(name="# of tracks", value=len(search.tracks))
            else:
                embed.add_field(
                    name="Duration",
                    value=format_time(sum(t.length for t in search.tracks) * 1000)
                )

            embed.add_field(name="Position in queue", value=f"{first_position}-{last_position}")
        else:
            if ctx.command.name in ("playnext", "playskip"):
                queue_position = 1
            else:
                queue_position = len(ctx.voice_client.queue)

            if search.is_stream():
                length = "🔴 Live"
            else:
                length = format_time(search.length * 1000)

            embed = ctx.embed(
                f"Queued {search.title}",
                url=search.uri,
                thumbnail_url=self.get_embed_thumbnail(search)
            )
            embed.add_field(name="Duration", value=length)
            embed.add_field(name="Position in queue", value=queue_position)

        await ctx.send(embed=embed)

    @commands.command(aliases=["p"])
    @commands.max_concurrency(1, commands.BucketType.guild, wait=True)
    async def play(self, ctx: Context, *, query: str = None):
        """Queues one or multiple tracks. Can be used to resume the player if paused."""
        player = ctx.voice_client

        if player.is_paused() and not query:
            await player.set_pause(False)
            return await ctx.send(embed=ctx.embed("Resumed player!"))
        elif not query:
            return

        if not (search := await self.get_tracks(ctx, query)):
            return await ctx.send(embed=ctx.embed("Nothing found."))

        if isinstance(search, YouTubePlaylist):
            tracks = search.tracks

            for track in tracks:
                player.queue.put(track)
                if player.shuffle:
                    assert player.shuffled_queue is not None
                    player.shuffled_queue.put(track)

            await self.send_play_command_embed(ctx, search)
        else:
            track = search[0]

            player.queue.put(track)
            if player.shuffle:
                assert player.shuffled_queue is not None
                player.shuffled_queue.put(track)

            if player.is_playing():
                await self.send_play_command_embed(ctx, track)

        if not player.is_playing() and not player.has_started:
            await player.play(player.queue.get())
            player.has_started = True

    @commands.command(aliases=["pn", "playtop", "pt"])
    @commands.max_concurrency(1, commands.BucketType.guild, wait=True)
    async def playnext(self, ctx: Context, *, query: str):
        """Same as play command, but adds to the start of the queue."""
        player = ctx.voice_client
        if not (search := await self.get_tracks(ctx, query)):
            return await ctx.send(embed=ctx.embed("Nothing found."))

        if isinstance(search, YouTubePlaylist):
            tracks = search.tracks

            for track in reversed(tracks):
                player.queue.put_at_front(track)
                if player.shuffle:
                    assert player.shuffled_queue is not None
                    player.shuffled_queue.put_at_front(track)

            await self.send_play_command_embed(ctx, search)
        else:
            track = search[0]

            player.queue.put_at_front(track)
            if player.shuffle:
                assert player.shuffled_queue is not None
                player.shuffled_queue.put_at_front(track)

            if player.is_playing():
                await self.send_play_command_embed(ctx, track)

        if not player.is_playing() and not player.has_started:
            await player.play(player.queue.get())
            player.has_started = True

    @commands.command(aliases=["ps"])
    @commands.max_concurrency(1, commands.BucketType.guild, wait=True)
    async def playskip(self, ctx: Context, *, query: str):
        """Same as playnext, but also skips the currently playing track."""
        player = ctx.voice_client
        if not (search := await self.get_tracks(ctx, query)):
            return await ctx.send(embed=ctx.embed("Nothing found."))

        if isinstance(search, YouTubePlaylist):
            tracks = search.tracks

            for track in reversed(tracks):
                player.queue.put_at_front(track)
                if player.shuffle:
                    assert player.shuffled_queue is not None
                    player.shuffled_queue.put_at_front(track)

            await self.send_play_command_embed(ctx, search)
        else:
            track = search[0]

            player.queue.put_at_front(track)
            if player.shuffle:
                assert player.shuffled_queue is not None
                player.shuffled_queue.put_at_front(track)

        if not player.is_playing() and not player.has_started:
            await player.play(player.queue.get())
            player.has_started = True
        elif not player.is_playing():
            pass
        else:
            await player.stop()

    @commands.command(aliases=["shuffleplay", "sp"])
    @commands.max_concurrency(1, commands.BucketType.guild, wait=True)
    async def playshuffle(self, ctx: Context, *, query: str):
        """Adds the given album/playlist to the queue in random order."""
        player = ctx.voice_client
        if not (search := await self.get_tracks(ctx, query)):
            return await ctx.send(embed=ctx.embed("Nothing found."))

        if isinstance(search, YouTubePlaylist):
            tracks = search.tracks
            random.shuffle(tracks)

            for track in tracks:
                player.queue.put(track)
                if player.shuffle:
                    assert player.shuffled_queue is not None
                    player.shuffled_queue.put(track)

            await self.send_play_command_embed(ctx, search)
        else:
            track = search[0]

            player.queue.put(track)
            if player.shuffle:
                assert player.shuffled_queue is not None
                player.shuffled_queue.put(track)

            if player.is_playing():
                await self.send_play_command_embed(ctx, track)

        if not player.is_playing() and not player.has_started:
            await player.play(player.queue.get())
            player.has_started = True

    @commands.command()
    async def pause(self, ctx: Context):
        """Pauses the player if it's playing."""
        player = ctx.voice_client

        if player.is_paused():
            return await ctx.send(embed=ctx.embed(
                "Player already paused.",
                f"Use `{ctx.prefix}play` or `{ctx.prefix}resume` to resume playback."
            ))

        await player.set_pause(True)
        await ctx.send(embed=ctx.embed("Player paused!"))

    @commands.command(aliases=["unpause"])
    async def resume(self, ctx: Context):
        """Resumes playback if the player is paused."""
        player = ctx.voice_client

        if not player.is_paused():
            return await ctx.send(embed=ctx.embed("Player is not paused."))

        await player.set_pause(False)
        await ctx.send(embed=ctx.embed("Player resumed!"))

    @commands.command(aliases=["dc", "stop", "leave", "begone", "fuckoff", "gtfo"])
    async def disconnect(self, ctx: Context):
        """Disconnects the player from its voice channel."""
        player = ctx.voice_client
        channel_name = player.channel.name

        player.queue.clear()
        await player.disconnect()

        await ctx.send(embed=ctx.embed(f"Disconnected from {channel_name}!"))

    @commands.command(aliases=["s"])
    async def skip(self, ctx: Context):
        """Skips the currently playing track."""
        player = ctx.voice_client

        if not player.is_playing():
            return await ctx.send(embed=ctx.embed("Nothing is playing!"))

        assert isinstance(player.track, Track)
        title = player.track.title
        uri = player.track.uri

        await player.stop()
        await ctx.send(embed=ctx.embed(f"Skipped {title}", url=uri))

    @commands.command(aliases=["q", "next", "comingup"])
    async def queue(self, ctx: Context):
        """Displays the player's queue."""
        player = ctx.voice_client
        queue = player.queue if not player.shuffle else player.shuffled_queue

        if not queue:
            embed = ctx.embed("Queue is empty!")
            return await ctx.send(embed=embed)

        queue_items = self.format_queue(queue)

        current = player.track

        assert isinstance(current, Track)
        if current.is_stream():
            current_pos = "stream"
        else:
            current_pos = (
                f"{format_time(player.position * 1000)}/"
                f"{format_time(current.length * 1000)}"
            )

        queue_items.insert(
            0,
            f"**▶ [{current.title}]({current.uri}) **"
            f"[{current_pos}] "
            f"({current.ctx.author.mention})\n"
        )

        q_length = f"{len(queue)} track{'' if len(queue) == 1 else 's'}"
        if any(t.is_stream() for t in queue):  # type: ignore
            q_duration = ""
        else:
            total = format_time(
                sum(t.length for t in queue) + (current.length - player.position) * 1000
            )
            q_duration = f" ({total})"

        await ctx.send(
            embed=ctx.embed(f"Queue - {q_length}{q_duration}", "\n".join(queue_items)[:4000])
        )

    @commands.command(aliases=["np", "current", "now", "song"])
    async def nowplaying(self, ctx: Context):
        """Shows info about the currently playing track."""
        player = ctx.voice_client

        if not player.is_playing():
            return await ctx.send(embed=ctx.embed("Nothing is playing!"))

        track = player.track
        assert isinstance(track, Track)

        if track.is_stream():
            position = "🔴 Live"
        else:
            position = f"{format_time(player.position * 1000)}/{format_time(track.length * 1000)}"

        embed = ctx.embed(
            track.title,
            url=track.uri,
            thumbnail_url=self.get_embed_thumbnail(track)
        )
        embed.add_field(name="Position", value=position)

        embed.add_field(name="Uploader", value=track.author)
        embed.add_field(name="Requested by", value=track.ctx.author.mention)

        await ctx.send(embed=embed)

    @commands.command(aliases=["nuke"])
    async def clear(self, ctx: Context):
        """Clears the player's queue."""
        player = ctx.voice_client

        if not player.queue:
            return await ctx.send(embed=ctx.embed("There's nothing to clear!"))

        amount = len(player.queue)
        player.queue.clear()
        await ctx.send(embed=ctx.embed(f"Cleared {amount} song{'' if amount == 1 else 's'}!"))

    @commands.command(aliases=["r", "rm"])
    async def remove(self, ctx: Context, index: int):
        """Removes a song from the player's queue."""
        player = ctx.voice_client
        queue = player.queue if not player.shuffle else player.shuffled_queue

        if not queue:
            return await ctx.send(embed=ctx.embed("The queue is empty!"))

        if index < 1 or index > len(queue):
            if len(queue) == 1:
                desc = f"Did you mean `{ctx.prefix}{ctx.invoked_with} 1`?"
            else:
                desc = f"Valid track numbers are `1-{len(queue)}`."

            return await ctx.send(embed=ctx.embed(f"Invalid track number!", desc))

        track = queue[index - 1]
        del queue[index - 1]

        if player.shuffle:
            del player.queue[player.queue.find_position(track)]

        assert isinstance(track, Track)

        embed = ctx.embed(f"Removed {track.title}", url=track.uri)
        embed.add_field(name="Requested by", value=track.ctx.author.mention)
        await ctx.send(embed=embed)

    @commands.command(aliases=["m"])
    async def move(self, ctx: Context, _from: int, _to: int):
        """Moves a song from the first given position to the second one."""
        player = ctx.voice_client
        queue = player.queue if not player.shuffle else player.shuffled_queue

        if _from == _to:  # no need to do anything here
            return

        assert isinstance(queue, WaitQueue)

        try:
            queue[_from - 1]
            queue[_to - 1]
        except IndexError:
            embed = ctx.embed("Invalid queue position!", f"Valid positions are 1-{len(queue)}.")
            return await ctx.send(embed=embed)

        track = queue[_from - 1]
        del queue[_from - 1]
        queue.put_at_index(_to - 1, track)

        assert isinstance(track, Track)
        await ctx.send(embed=ctx.embed(f"Moved {track.title} to position {_to}"))

    @commands.command()
    async def shuffle(self, ctx: Context):
        """Toggles shuffle. When enabled, the queue is shuffled and it's restored when disabled."""
        player = ctx.voice_client
        player.set_shuffle(not player.shuffle)

        action = "Enabled" if player.shuffle else "Disabled"
        desc = f"Run the command again to restore the queue's order." if player.shuffle else Empty

        await ctx.send(embed=ctx.embed(f"{action} shuffle!", desc))

    @commands.command()
    async def seek(self, ctx: Context, *, time: str):
        """Seeks to a position in the track.
           Accepted formats are HH:MM:SS, MM:SS (or Mm Ss), +Xs and -Xs
           where X is the number of seconds.
           For example:
               - seek 01:23:30
               - seek 00:32
               - seek 2m 4s
               - seek 50s
               - seek +30s
               - seek -23s
        """
        player = ctx.voice_client
        seconds = 0

        if not player.is_playing():
            return await ctx.send(embed=ctx.embed("Nothing is playing!"))

        if match := HH_MM_SS_RE.fullmatch(time):
            seconds += int(match.group("h")) * 3600000
            seconds += int(match.group("m")) * 60000
            seconds += int(match.group("s")) * 1000

            new_position = seconds
        elif match := MM_SS_RE.fullmatch(time):
            seconds += int(match.group("m")) * 60000
            seconds += int(match.group("s")) * 1000

            new_position = seconds
        elif match := OFFSET_RE.fullmatch(time):
            seconds += int(match.group("s")) * 1000

            position = player.position
            new_position = position + seconds
        elif match := HUMAN_RE.fullmatch(time):
            if m := match.group("m"):
                if match.group("s") and time.lower().endswith("m"):
                    return await ctx.send(embed=ctx.embed(
                        "Invalid time format!",
                        f"See `{ctx.prefix}help seek` for accepted formats."
                    ))
                seconds += int(m) * 60000
            if s := match.group("s"):
                if time.lower().endswith("m"):
                    seconds += int(s) * 60000
                else:
                    seconds += int(s) * 1000

            new_position = seconds
        else:
            return await ctx.send(embed=ctx.embed(
                "Invalid time format!",
                f"See `{ctx.prefix}help seek` for accepted formats."
            ))

        new_position = max(0, min(new_position, player.current.length))
        embed = ctx.embed(f"Seeked to {format_time(new_position)}.")
        await player.seek(new_position)
        await ctx.send(embed=embed)


def setup(bot: Bot):
    bot.add_cog(Music(bot))
