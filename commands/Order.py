import discord
from core import Bot, Arb
from core.Utils import show_odd
from typing import Optional, List
from datetime import datetime


PLACED_ORDER_TITLE = ":large_orange_diamond: BET PLACED"
deleted_emb = discord.Embed(
    description=":warning: Sorry, this bet is no longer available.",
    colour=discord.Colour.red()
)


async def go(msg: discord.Message, msg_bet: Optional[discord.Message], arbs: List[Arb], bot: Bot) -> Optional[discord.Message]:
    await msg.channel.typing()

    if msg_bet is None:
        emb = discord.Embed(
            description=":warning: Sorry, this bet is no longer available.",
            colour=discord.Colour.red()
        )
        await msg.reply(embed=emb)
        return None

    if msg_bet.author != bot.user:
        return

    bet_emb = msg_bet.embeds[0]
    event_slug = f"{bet_emb.fields[0].value}|{bet_emb.fields[2].value}"
    arb: Arb = discord.utils.get(arbs, slug=event_slug)
    if not arb:
        return None

    args = msg.content.split(" ")
    if len(args) != 2:
        emb = discord.Embed(
            description=":warning: Provide the odds and the amount. Example: `1.50 300`.",
            colour=discord.Colour.red()
        )
        await msg.reply(embed=emb)
        return None

    placed_odds = float(args[0])
    amount = float(args[1])
    value = ((1/placed_odds + 1/arb.oposition_odds) - 1) * 100
    match_time = datetime.utcfromtimestamp(arb.start_at)
    values = [
        str(msg.author),  # username
        msg.created_at.strftime("%d/%m/%Y %H:%M"),  # date of bet
        "No" if arb.disappeared_at is None else "Yes",  # after deletion
        arb.event_name,
        match_time.strftime("%d/%m/%Y %H:%M"),
        arb.market,
        show_odd(arb.current_odds),
        show_odd(arb.last_acceptable_odds),
        show_odd(placed_odds),
        amount,
        f"{show_odd(value)}%",
        arb.bookmaker,
    ]
    bot.worksheet.append_row(values, table_range="A1:K1")
    await bot.db.set('''
        INSERT INTO orders(user_id, event_slug)
        VALUES (%s, %s)
    ''', msg.author.id, arb.slug)
    emb = discord.Embed(
        title=f"✅ Your bet was saved!",
        description=event_slug,
        colour=discord.Colour.green()
    )
    emb.add_field(name="Placed Odds", value=show_odd(placed_odds), inline=True)
    emb.add_field(name="Amount", value=amount, inline=True)
    emb.add_field(name="Value (Edge)", value=f"{show_odd(value)}%", inline=True)
    emb.add_field(name="Market", value=arb.market, inline=True)
    await msg_bet.reply(embed=emb)
    bet_emb.title = PLACED_ORDER_TITLE
    return await msg_bet.edit(embed=emb)