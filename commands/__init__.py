# -*- coding: utf-8 -*-
import discord
from discord .ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
from typing import List
from . import Stop, Start, Bookies, Script, Order
from core import Bot, Utils, Arb, BOT_GUILD
from contextlib import suppress


DISAPPEARED_TITLE = ":alarm_clock: EVENT WILL DISAPPEAR IN 5 MINUTES"


class BetCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.arbs: List[Arb] = []
        self.last_update_orders_time = datetime.utcnow()
        for loop in [self.update_arbs_loop, self.update_orders_loop]:
            loop.start()

    @tasks.loop(seconds=5)
    async def update_arbs_loop(self):
        now_arbs = await Utils.execute_suppress(self.bot.bclient.get_arbs()) or []
        new, updated = [], []
        for a in now_arbs:
            try:
                i = self.arbs.index(a)
                if self.arbs[i].value != a.value or self.arbs[i].disappeared_at:
                    updated.append(a)
            except ValueError:
                new.append(a)
        disappeared = [a for a in self.arbs if a not in now_arbs]
        self.arbs = now_arbs + disappeared
        if new and self.update_arbs_loop.current_loop:
            await Utils.execute_suppress(self.send_arbs(new))
        if updated:
            await Utils.execute_suppress(self.update_arbs(updated))
        if disappeared:
            await Utils.execute_suppress(self.delete_arbs(disappeared))

    @update_arbs_loop.before_loop
    async def before_update_arbs(self):
        await self.bot.wait_until_ready()
        data = await self.bot.db.get("SELECT channel_id, message_id FROM messages")
        for channel_id, message_id in data:
            channel = self.bot.get_channel(channel_id)
            if channel is not None:
                with suppress(discord.NotFound):
                    lost_msg = await channel.fetch_message(message_id)
                    self.bot.messages[lost_msg.id] = lost_msg
                    continue
            await self.bot.db.set("DELETE FROM messages WHERE message_id=%s", message_id)

    @tasks.loop(seconds=30)
    async def update_orders_loop(self):
        end_time = datetime.utcnow() + timedelta(minutes=1)
        await Utils.execute_suppress(Order.update_orders(self.bot, self.last_update_orders_time, end_time))
        self.last_update_orders_time = end_time

    @update_orders_loop.before_loop
    async def before_update_orders(self):
        day_ago = datetime.utcnow() - timedelta(days=1)
        await self.bot.db.set("DELETE FROM orders WHERE match_time<%s", day_ago)
        await self.bot.wait_until_ready()

    async def send_arbs(self, arbs: List[Arb]):
        send_tasks = []
        for arb in arbs:
            data = await self.bot.db.get('''
                SELECT u.channel_id, u.bookies
                FROM users u
                WHERE active AND
                NOT EXISTS(
                    SELECT True
                    FROM orders o
                    WHERE o.user_id=u.user_id AND o.slug=%s
                )
            ''', arb.slug)
            for channel_id, bookies in data:
                if bookies is None or arb.bookmaker['name'] in bookies.split(","):
                    task = self.send_arb(channel_id, arb)
                    send_tasks.append(task)
        await asyncio.gather(*send_tasks)

    async def send_arb(self, channel_id: int, arb: Arb):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            # channel was deleted -> delete user
            await self.bot.db.set("DELETE FROM users WHERE channel_id=%s", channel_id)
            return
        msg = await channel.send(embed=arb.to_embed(), view=Order.PlaceOrder(arb))
        self.bot.messages[msg.id] = msg
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
        msg = await self.bot.fetch_message(channel_id, message_id)
        now = discord.utils.utcnow()
        if not msg:
            return
        edited_age = now - (msg.edited_at or msg.created_at)
        msg_age = now - msg.created_at
        if msg.embeds[0].title != DISAPPEARED_TITLE:
            if msg_age < timedelta(minutes=10):
                if edited_age < timedelta(seconds=20):
                    return
            else:
                if edited_age < timedelta(minutes=2):
                    return
        new_emb = arb.to_embed()
        view = Order.PlaceOrder(arb)
        if msg.embeds[0].title == Order.PLACED_ORDER_TITLE:
            new_emb.title = Order.PLACED_ORDER_TITLE
            view.children[0].disabled = True
        self.bot.messages[msg.id] = await msg.edit(embed=new_emb, view=view)

    async def delete_arbs(self, arbs: List[Arb]):
        delete_tasks = []
        now_timestamp = int(datetime.utcnow().timestamp())
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            msgs = []
            for channel_id, message_id in data:
                msg = await self.bot.fetch_message(channel_id, message_id)
                if msg is not None:
                    msgs.append(msg)
            if arb.disappeared_at is None:
                arb.disappeared_at = now_timestamp
                for msg in msgs:
                    delete_tasks.append(self.warn_delete_arb(msg, arb))
            elif (now_timestamp - arb.disappeared_at) > 5*60:
                self.arbs.remove(arb)
                await self.bot.db.set("DELETE FROM messages WHERE event_slug=%s", arb.slug)
                for msg in msgs:
                    delete_tasks.append(self.delete_message(msg))
        await asyncio.gather(*delete_tasks)

    async def warn_delete_arb(self, msg: discord.Message, arb: Arb):
        emb = msg.embeds[0]
        if emb.title != Order.PLACED_ORDER_TITLE:
            emb.title = DISAPPEARED_TITLE
            self.bot.messages[msg.id] = await msg.edit(embed=emb, view=Order.PlaceOrder(arb))

    async def delete_message(self, msg: discord.Message):
        self.bot.messages.pop(msg.id, None)
        if msg.embeds[0].title != Order.PLACED_ORDER_TITLE:
            await msg.delete()

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