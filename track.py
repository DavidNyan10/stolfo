from wavelink import NodePool, PartialTrack as _PartialTrack, YouTubeTrack
from wavelink.utils import MISSING

from context import Context


class PartialTrack(_PartialTrack):
    def __init__(self, *args, context: Context, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = context

    async def _search(self):
        node = self._node
        if node is MISSING:
            node = NodePool.get_node()

        tracks = await self._cls.search(query=self.query, node=node, context=self.context)

        return tracks[0]


class Track(YouTubeTrack):
    def __init__(self, *args, context: Context, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = context

    @classmethod
    async def search(
        cls,
        query: str,
        *,
        type=None,
        node=MISSING,
        return_first: bool = False,
        context: Context
    ):
        if node is MISSING:
            node = NodePool.get_node()

        data, resp = await node._get_data("loadtracks", {"identifier": f"ytsearch:{query}"})

        if resp.status != 200:
            raise Exception("Invalid server response.")

        tracks = [cls(t["track"], t["info"], context=context) for t in data["tracks"]]

        if return_first:
            return tracks[0]

        return tracks
