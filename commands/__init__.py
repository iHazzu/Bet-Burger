# -*- coding: utf-8 -*-
import discord
from discord .ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
from typing import List, Optional, Dict
from . import Stop, Start, Bookies, Script, Order
from core import Bot, Utils, Arb, BOT_GUILD
from contextlib import suppress


DISAPPEARED_TITLE = ":alarm_clock: EVENT WILL DISAPPEAR IN ONE MINUTE"


class BetCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.messages: Dict[int, discord.Message] = {}
        self.arbs: List[Arb] = []
        self.update_loop.start()

    async def fetch_message(self, channel_id: int, message_id: int) -> Optional[discord.Message]:
        msg = self.messages.get(message_id)
        if msg is None:
            channel = self.bot.get_channel(channel_id)
            if channel:
                with suppress(discord.NotFound):
                    msg = await channel.fetch_message(message_id)
        return msg

    @tasks.loop(seconds=5)
    async def update_loop(self):
        now_arbs = await Utils.execute_suppress(self.bot.bclient.get_arbs()) or []
        new, updated = [], []
        for a in now_arbs:
            try:
                i = self.arbs.index(a)
                if self.arbs[i].upated_at != a.upated_at or self.arbs[i].disappeared_at:
                    updated.append(a)
            except ValueError:
                new.append(a)
        disappeared = [a for a in self.arbs if a not in now_arbs]
        self.arbs = now_arbs + disappeared
        if new:
            await Utils.execute_suppress(self.send_arbs(new))
        if updated:
            await Utils.execute_suppress(self.update_arbs(updated))
        if disappeared:
            await Utils.execute_suppress(self.delete_arbs(disappeared))
        if (self.update_loop.current_loop + 1) % 100 == 0:
            await Utils.execute_suppress(self.delete_orders_week_ago())

    @update_loop.before_loop
    async def wait_ready(self):
        await self.bot.wait_until_ready()
        data = await self.bot.db.get("SELECT channel_id, message_id FROM messages")
        for channel_id, message_id in data:
            with suppress(discord.NotFound):
                lost_msg = await self.bot.get_channel(channel_id).fetch_message(message_id)
                asyncio.create_task(lost_msg.delete())
        await self.bot.db.set("DELETE FROM messages")

    async def send_arbs(self, arbs: List[Arb]):
        send_tasks = []
        for arb in arbs:
            data = await self.bot.db.get('''
                SELECT u.channel_id, u.bookies
                FROM users u
                WHERE active=True
                AND NOT EXISTS(
                    SELECT True
                    FROM orders o
                    WHERE o.user_id=u.user_id AND o.event_slug=%s
                )
            ''', arb.slug)
            for channel_id, bookies in data:
                if bookies is None or arb.bookmaker in bookies.split(","):
                    task = self.send_arb(channel_id, arb)
                    send_tasks.append(task)
        await asyncio.gather(*send_tasks)

    async def send_arb(self, channel_id: int, arb: Arb):
        channel = self.bot.get_channel(channel_id)
        msg = await channel.send(embed=arb.to_embed())
        self.messages[msg.id] = msg
        await self.bot.db.set('''
            INSERT INTO messages (event_slug, channel_id, message_id)
            VALUES(%s, %s, %s)
        ''', arb.slug, channel_id, msg.id)

    async def update_arbs(self, arbs: List[Arb]):
        update_tasks = []
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            for channel_id, message_id in data:
                update_tasks.append(self.update_arb(channel_id, message_id, arb))
        await asyncio.gather(*update_tasks)

    async def update_arb(self, channel_id: int, message_id: int, arb: Arb):
        msg = await self.fetch_message(channel_id, message_id)
        if not msg:
            return
        new_emb = arb.to_embed()
        if msg.embeds[0] == Order.PLACED_ORDER_TITLE:
            new_emb.title = Order.PLACED_ORDER_TITLE
        self.messages[msg.id] = await msg.edit(embed=new_emb)

    async def delete_arbs(self, arbs: List[Arb]):
        delete_tasks = []
        now_timestamp = int(datetime.datetime.utcnow().timestamp())
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            msgs = []
            for channel_id, message_id in data:
                msg = await self.fetch_message(channel_id, message_id)
                if msg is not None:
                    msgs.append(msg)
            if arb.disappeared_at is None:
                arb.disappeared_at = now_timestamp
                for msg in msgs:
                    delete_tasks.append(self.warn_delete_arb(msg))
            elif (now_timestamp - arb.disappeared_at) > 60:
                self.arbs.remove(arb)
                await self.bot.db.set("DELETE FROM messages WHERE event_slug=%s", arb.slug)
                for msg in msgs:
                    delete_tasks.append(self.delete_arb(msg))
        await asyncio.gather(*delete_tasks)

    async def warn_delete_arb(self, msg: discord.Message):
        emb = msg.embeds[0]
        emb.title = DISAPPEARED_TITLE
        self.messages[msg.id] = await msg.edit(embed=emb)

    async def delete_arb(self, msg: discord.Message):
        self.messages.pop(msg.id)
        if msg.embeds[0].title != Order.PLACED_ORDER_TITLE:
            await msg.delete()

    async def delete_orders_week_ago(self):
        current_time = datetime.datetime.utcnow()
        one_week_ago = current_time - datetime.timedelta(weeks=1)
        await self.bot.db.set("DELETE FROM orders WHERE created < %s", one_week_ago)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.reference:
            await self.try_place_order(message)

    async def try_place_order(self, msg: discord.Message):
        msg_bet = await self.fetch_message(msg.channel.id, msg.reference.message_id)
        try:
            new_msg_bet = await Order.go(msg, msg_bet, self.arbs, self.bot)
        except Exception as error:
            emb = discord.Embed(
                description=f":warning: Sorry, an error occurred while saving your bet.```prolog\n{error}```",
                colour=discord.Colour.red()
            )
            await msg.reply(embed=emb)
        else:
            if new_msg_bet is not None:
                self.messages[msg_bet.id] = new_msg_bet

    @app_commands.command(name="start")
    @app_commands.guilds(BOT_GUILD)
    async def start_receive_bets(self, interaction: discord.Interaction):
        """Start receiving new bet notifications

        Args:
            interaction: the interaction associated with the command
        """
        await Start.go(interaction=interaction)

    @app_commands.command(name="stop")
    @app_commands.guilds(BOT_GUILD)
    async def stop_receive_bets(self, interaction: discord.Interaction):
        """Stop receiving new bet notifications

        Args:
            interaction: the interaction associated with the command
        """
        await Stop.go(interaction=interaction)

    @app_commands.command(name="bookies")
    @app_commands.guilds(BOT_GUILD)
    async def select_bookies(self, interaction: discord.Interaction):
        """Choose the bookies you want to receive notifications

        Args:
            interaction: the interaction associated with the command
        """

        await Bookies.go(interaction=interaction)

    @commands.command(name="eval")
    async def script(self, ctx: commands.Context, *, code: str):
        """Run a script in the bot

        Args:
            ctx: the context associated with the command
            code: the code to run
        """
        await Script.go(ctx=ctx, code=code)


async def setup(bot: Bot):
    await bot.add_cog(BetCog(bot))