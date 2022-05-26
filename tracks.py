from typing import ClassVar, Optional, Type, TypeVar, Union

import yarl
from wavelink import (
    Node,
    NodePool,
    PartialTrack as _PartialTrack,
    SearchableTrack as _SearchableTrack,
    Track as _Track,
    YouTubePlaylist as _YouTubePlaylist,
    YouTubeTrack as _YoutubeTrack
)
from wavelink.utils import MISSING

import spotify_ext as spotify
from context import Context

ST = TypeVar("ST", bound="SearchableTrack")


class Track(_Track):
    def __init__(self, *args, ctx: Context, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)


class SearchableTrack(_SearchableTrack, Track):
    _search_type: ClassVar[str]

    @classmethod
    async def search(
        cls: Type[ST],
        query: str,
        *,
        type=None,
        node: Node = MISSING,
        return_first: bool = False,
        ctx: Context
    ) -> Union[Optional[ST], list[ST]]:
        """|coro|
        Search for tracks with the given query.
        Parameters
        ----------
        query: str
            The song to search for.
        spotify_type: Optional[:class:`spotify.SpotifySearchType`]
            An optional enum value to use when searching with Spotify.
        node: Optional[:class:`wavelink.Node`]
            An optional Node to use to make the search with.
        return_first: Optional[bool]
            An optional bool which when set to True will return only the first track found. Defaults to False.
            Use this as True, when searching with LocalTrack.
        Returns
        -------
        Union[Optional[Track], List[Track]]
        """
        if node is MISSING:
            node = NodePool.get_node()

        check = yarl.URL(query)

        if str(check.host) == 'youtube.com' or str(check.host) == 'www.youtube.com' and check.query.get("list") or \
                cls._search_type == 'ytpl':
            tracks = await node.get_playlist(cls=YouTubePlaylist, identifier=query)
            if tracks:
                tracks.ctx = ctx
        elif cls._search_type == 'local':
            tracks = await node.get_tracks(cls, query)
            for track in tracks:
                track.ctx = ctx
        else:
            tracks = await node.get_tracks(cls, f"{cls._search_type}:{query}")
            for track in tracks:
                track.ctx = ctx

        if return_first and not isinstance(tracks, YouTubePlaylist) and tracks is not None:
            return tracks[0]

        return tracks


class YouTubeTrack(SearchableTrack, _YoutubeTrack):
    ...


class YouTubePlaylist(_YouTubePlaylist, SearchableTrack):
    _search_type: ClassVar[str] = "ytpl"

    def __init__(self, data: dict, ctx: Context):
        self.tracks: list[YouTubeTrack] = []
        self.name: str = data["playlistInfo"]["name"]

        self.selected_track: Optional[int] = data["playlistInfo"].get("selectedTrack")
        if self.selected_track is not None:
            self.selected_track = int(self.selected_track)

        for track_data in data["tracks"]:
            track = YouTubeTrack(track_data["track"], track_data["info"], ctx=ctx)
            self.tracks.append(track)


class PartialTrack(_PartialTrack):
    def __init__(self, *args, ctx: Context, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)


class PartialSpotifyTrack(PartialTrack):
    def __init__(self, data, ctx: Context):
        self.thumbnail = data["images"][0]["url"]
        self.uri = data["external_urls"].get("spotify")
        super().__init__(
            query=f"{', '.join([i['name'] for i in data['artists']])} - {data['name']}",
            ctx=ctx
        )
