from discord.ext import commands
import discord
from .database import DataBase
from .bet_burger_api import BetClient
from typing import Optional
from gspread import Worksheet


class Bot(commands.Bot):
    def __init__(self):
        self.db = DataBase(5)
        self.bclient = BetClient()
        self.worksheet: Optional[Worksheet] = None
        super().__init__(
            command_prefix="!",
            intents=discord.Intents(messages=True, message_content=True, guilds=True),
            max_messages=None
        )

    async def terminate(self) -> None:
        self.db.close()
        await self.bclient.close()
        await self.close()