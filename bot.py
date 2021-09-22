from os import listdir

import lavalink
from discord import ClientUser, Message
from discord.ext import commands
from discord.ext.commands import when_mentioned_or

from config import LL_HOST, LL_PORT, LL_PASS, LL_REGION, TOKEN
from context import Context


class Bot(commands.Bot):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.lavalink: lavalink.Client

        self.loop.create_task(self._on_first_ready())

    async def get_context(self, message: Message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    async def _on_first_ready(self):
        await self.wait_until_ready()
        self.user: ClientUser

        # lavalink logic
        self.lavalink = lavalink.Client(self.user.id)
        self.lavalink.add_node(LL_HOST, LL_PORT, LL_PASS, LL_REGION, name="main-node")
        self.add_listener(self.lavalink.voice_update_handler, "on_socket_response")

        # loading cogs
        self.load_extension("jishaku")
        for file in listdir("./cogs"):
            if file.endswith(".py"):
                try:
                    self.load_extension(f"cogs.{file[:-3]}")
                except Exception as e:
                    print(f"Failed to load cogs.{file[:-3]}: {e}")


def main():
    bot = Bot(command_prefix=when_mentioned_or("a!"))
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
