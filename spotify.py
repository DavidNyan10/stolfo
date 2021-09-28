import time
from dataclasses import dataclass

from wavelink.ext.spotify import SpotifyClient, SpotifyRequestError

from context import Context
from pool import Node
from track import PartialTrack, Track


@dataclass
class _Track:
    artist: str
    name: str


async def get_data(query: str, node: Node) -> dict:
    data, resp = await node._get_data("loadtracks", {"identifier": query})

    if resp.status != 200:
        raise Exception("Invalid server response! Try again later.")

    return data


class Spotify(SpotifyClient):
    async def get_object(self, type: str, identifier: str) -> dict:
        if not self._bearer_token or time.time() >= self._expiry:
            await self._get_bearer_token()

        url = f"https://api.spotify.com/v1/{type}s/{identifier}"
        async with self.session.get(url, headers=self.bearer_headers) as resp:
            if resp.status != 200:
                raise SpotifyRequestError(resp.status, resp.reason)

            return await resp.json()

    async def get_album_tracks(self, album: dict) -> list[_Track]:
        artist = album["artists"][0]["name"]
        tracks = []
        for t in album["tracks"]["items"]:
            tracks.append(_Track(artist, t["name"]))

        return tracks

    async def get_playlist_tracks(self, ctx: Context, playlist: dict, node: Node) -> list[PartialTrack]:
        tracks = []

        if url := playlist["tracks"]["next"]:
            for t in playlist["tracks"]["items"]:
                artist = t["track"]["artists"][0]["name"]
                name = t["track"]["name"]
                ll_data = await get_data(f"ytsearch:{artist} - {name}", node)
                track_data = ll_data["tracks"][0]
                track = Track(track_data["track"], track_data["info"], context=ctx)
                tracks.append(track)

            while True:
                async with self.session.get(url, headers=self.bearer_headers) as resp:
                    playlist = await resp.json()

                    for t in playlist["items"]:
                        artist = t["track"]["artists"][0]["name"]
                        name = t["track"]["name"]
                        ll_data = await get_data(f"ytsearch:{artist} - {name}", node)
                        track_data = ll_data["tracks"][0]
                        track = Track(track_data["track"], track_data["info"], context=ctx)
                        tracks.append(track)

                    if not playlist["next"]:
                        break

                    url = playlist["next"]
        else:
            for t in playlist["tracks"]["items"]:
                artist = t["track"]["artists"][0]["name"]
                name = t["track"]["name"]
                ll_data = await get_data(f"ytsearch:{artist} - {name}", node)
                track_data = ll_data["tracks"][0]
                track = Track(track_data["track"], track_data["info"], context=ctx)
                tracks.append(track)

        return tracks
