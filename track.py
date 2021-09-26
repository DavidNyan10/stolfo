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
        print(self.context)

    async def search(self, *args, context: Context, **kwargs):
        self.context = context
        return await super().search(*args, **kwargs)
