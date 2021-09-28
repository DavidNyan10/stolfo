from datetime import datetime
from os import listdir, path

from discord import ClientUser, Game, Intents, Message, Status, VoiceRegion
from discord.ext import commands
from discord.ext.commands import when_mentioned_or

from config import LL_HOST, LL_PORT, LL_PASS, SPOTIFY_ID, SPOTIFY_SECRET, TOKEN
from context import Context
from pool import Node, NodePool
from spotify import Spotify


class Bot(commands.Bot):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.spotify: Spotify
        self.start_time: datetime

        self.loop.create_task(self._on_first_ready())

    async def get_context(self, message: Message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    async def _on_first_ready(self):
        await self.wait_until_ready()

        self.user: ClientUser
        self.spotify = Spotify(client_id=SPOTIFY_ID, client_secret=SPOTIFY_SECRET)
        self.start_time = datetime.utcnow()

        # set presence
        await self.change_presence(activity=Game("nya | a!help"), status=Status.dnd)

        await NodePool.create_node(
            bot=self,
            host=LL_HOST,
            port=LL_PORT,
            password=LL_PASS,
            region=VoiceRegion.frankfurt
        )

        # loading cogs
        self.load_extension("jishaku")
        for file in listdir("./cogs"):
            if file.endswith(".py"):
                ext = f"cogs.{file[:-3]}"
                try:
                    self.load_extension(ext)
                    print(f"{ext} loaded successfully")
                except Exception as e:
                    print(f"Failed to load {ext}: {e}")

        if path.exists("./cogs/private"):
            for file in listdir("./cogs/private"):
                if file.endswith(".py"):
                    ext = f"cogs.private.{file[:-3]}"
                    try:
                        self.load_extension(ext)
                        print(f"{ext} loaded successfully")
                    except Exception as e:
                        print(f"Failed to load {ext}: {e}")

    async def on_wavelink_node_ready(self, node: Node):
        print(f"Wavelink node {node.identifier} is ready")


def main():
    bot = Bot(command_prefix=when_mentioned_or("a!"), intents=Intents.all())
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
