import re
from typing import Optional, Union

from discord.enums import try_enum
from discord.ext.commands import BadArgument, Converter
from wavelink import LoadType, NodePool

from context import Context
from spotify import Spotify
from track import PartialTrack, Track

URL_RE = re.compile(r"https?://(?:www\.)?.+")

# regex to match all spotify URLs and URIs we support
# for example https://open.spotify.com/<type>/<id> or spotify:<type>:<id>
SPOTIFY_RE = re.compile(
    r"(?:(?:https://)?open.spotify.com/|spotify:)"
    r"(?P<type>track|album|playlist)(?:/|:)"
    r"(?P<id>[A-Za-z0-9]+)(?:.+)?"
)


class SearchException(BadArgument):
    def __init__(self, message: str, *args, **kwargs):
        self.message = message
        super().__init__(message, *args, **kwargs)


class SearchResult(Converter):
    def __init__(self, return_first: bool = True):
        self.name: Optional[str]
        self.type: str
        self.url: str

        self.thumbnail = ""
        self.tracks: Union[list[Track], list[PartialTrack]] = []
        self._node = NodePool.get_node()
        self._return_first = return_first

    async def get_data(self, query: str) -> dict:
        data, resp = await self._node._get_data("loadtracks", {"identifier": query})

        if resp.status != 200:
            raise SearchException("Invalid server response! Try again later.")

        return data

    async def convert(self, ctx: Context, argument: str):
        if match := SPOTIFY_RE.match(argument):
            spotify: Spotify = ctx.bot.spotify
            _type, _id = match["type"], match["id"]

            try:
                data = await spotify.get_object(_type, _id)
            except spotify.SpotifyRequestError:
                raise SearchException("An error has occurred during a Spotify request.")

            self.name = data["name"]
            self.url = data["external_urls"]["spotify"]

            if data["type"] == "track":
                self.thumbnail = max(
                    data["album"]["images"], key=lambda i: i["height"]
                ).get("url", "")
                self.type = "TRACK"

                artist = data["artists"][0]["name"]

                ll_data = await self.get_data(f"ytsearch:{artist} - {self.name}")
                track_data = ll_data["tracks"][0]
                track = Track(track_data["track"], track_data["info"], context=ctx)
                self.tracks.append(track)

            elif data["type"] == "album":
                self.thumbnail = max(data["images"], key=lambda i: i["height"]).get("url", "")
                self.type = "MULTIPLE"

                for t in await spotify.get_album_tracks(data):
                    ll_data = await self.get_data(f"ytsearch:{t.artist} - {t.name}")
                    track_data = ll_data["tracks"][0]
                    track = Track(track_data["track"], track_data["info"], context=ctx)
                    self.tracks.append(track)

            elif data["type"] == "playlist":
                self.thumbnail = data["images"][0].get("url", "")
                self.type = "MULTIPLE"

                msg = await ctx.send(embed=ctx.embed(
                    f"Queueing {self.name}...",
                    "This can take a while for large playlists.",
                    thumbnail_url=self.thumbnail
                ))
                async with ctx.typing():
                    self.tracks.extend(
                        track for track in
                        await spotify.get_playlist_tracks(ctx, data, self._node)
                    )
                    await msg.delete()

            else:
                raise SearchException("Invalid Spotify API response.")

        else:
            if URL_RE.match(argument):
                query = argument
            else:
                query = f"ytsearch:{argument}"

            data = await self.get_data(query)

            load_type = try_enum(LoadType, data.get("loadType"))

            if load_type is LoadType.load_failed:
                raise SearchException("Failed to load track.")

            if load_type is LoadType.no_matches:
                raise SearchException("Nothing found!")

            if load_type is LoadType.track_loaded:
                track_data = data["tracks"][0]
                track = Track(track_data["track"], track_data["info"], context=ctx)
                self.tracks.append(track)

                self.name = track_data["info"]["title"]
                self.thumbnail = track.thumbnail
                self.type = "TRACK"
                self.url = track.uri

            elif load_type is LoadType.playlist_loaded:
                for track_data in data["tracks"]:
                    self.tracks.append(Track(track_data["track"], track_data["info"], context=ctx))
                self.name = data["playlistInfo"]["name"]
                self.type = "MULTIPLE"
                self.url = None

            elif load_type is LoadType.search_result:
                if self._return_first:
                    track_data = data["tracks"][0]
                    track = Track(track_data["track"], track_data["info"], context=ctx)
                    self.tracks.append(track)

                    self.name = track.title
                    self.thumbnail = track.thumbnail
                    self.type = "TRACK"
                    self.url = track.uri
                else:
                    for track_data in data["tracks"]:
                        self.tracks.append(
                            Track(track_data["track"], track_data["info"], context=ctx)
                        )
                    self.name = ""
                    self.type = "SEARCH_RESULT"
                    self.url = None

            else:
                raise SearchException("Unknown load type, you should report this issue.")

        return self
