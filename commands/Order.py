import discord
from core import Arb, Interaction, Bot
from core.Utils import show_odd
from typing import Optional, Dict, Union
from datetime import datetime, timedelta
from gspread import Cell
from discord.utils import find
from contextlib import suppress

PLACED_ORDER_TITLE = ":large_orange_diamond: BET PLACED"


class PlaceOrder(discord.ui.View):
    def __init__(self, arb: Arb):
        super().__init__(timeout=None)
        self.arb = arb

    @discord.ui.button(emoji="💶", label="Place Order", style=discord.ButtonStyle.blurple)
    async def place_order(self, interaction: Interaction, button: discord.ui.Button):
        bot = interaction.client
        user = interaction.user
        data = await bot.db.get("SELECT last_stake_amount FROM users WHERE user_id=%s", user.id)
        if not data:
            return

        last_stake_amount = data[0][0]
        form = OrderForm(self.arb, data[0][0])
        try:
            await interaction.response.send_modal(form)
        except discord.NotFound:
            return
        await form.wait()
        if not form.interaction:
            return
        await form.interaction.response.defer()

        placed_odds = round(float(form.bookie_odds.value), 2)
        chance_odds = round(float(form.chance_odds.value), 2)
        stake_amount = round(float(form.stake_amount.value), 2)
        comment = form.comment.value or ""
        value = 1 / (1 / placed_odds + 1 / self.arb.oposition_odds) - 1
        match_time = datetime.utcfromtimestamp(self.arb.start_at)
        updated_timedelta = (datetime.utcnow() - datetime.utcfromtimestamp(self.arb.upated_at))

        values = [
            str(user),  # username
            (interaction.created_at + timedelta(hours=2)).strftime("%d.%m.%Y %H:%M:%S"),
            (match_time + timedelta(hours=2)).strftime("%d.%m.%Y %H:%M:%S"),
            "",  # time to event (empty)
            self.arb.sport,
            self.arb.league,
            self.arb.event_name,
            self.arb.market,
            self.arb.period,
            self.arb.current_odds,
            self.arb.oposition_odds,
            self.arb.last_acceptable_odds,
            placed_odds,
            chance_odds,
            stake_amount,
            "",  # soft bookie clv (empty)
            "",  # soft bookie drop (empty)
            "",  # pinn clv (empty)
            "",  # pinn drop (empty)
            value,
            "",  # status (empty)
            self.arb.bookmaker['name'],
            self.arb.arrow,
            self.arb.oposition_arrow,
            updated_timedelta.seconds,
            "No" if self.arb.disappeared_at is None else "Yes",  # after deletion,
            comment,
            f"{self.arb.bet_id}/{self.arb.bookmaker['id']}"
        ]
        bot.worksheet.append_row(values, table_range="A1:AB1")

        await bot.db.set('''
            INSERT INTO orders(user_id, bet_id, bookmaker_id, match_time, slug)
            VALUES (%s, %s, %s, %s, %s)
        ''', user.id, self.arb.bet_id, self.arb.bookmaker['id'], match_time, self.arb.slug)
        if stake_amount != last_stake_amount:
            await bot.db.set("UPDATE users SET last_stake_amount=%s WHERE user_id=%s", stake_amount, user.id)

        bet_emb = interaction.message.embeds[0]
        bet_emb.title = PLACED_ORDER_TITLE
        button.disabled = True
        with suppress(discord.NotFound):
            bot.messages[interaction.message.id] = await interaction.message.edit(embed=bet_emb, view=self)

        emb = discord.Embed(
            title=f"✅ Your bet was saved!",
            description=f"{self.arb.event_name} | {self.arb.bookmaker['name']}",
            colour=discord.Colour.green()
        )
        emb.add_field(name="Placed Odds", value=show_odd(placed_odds), inline=True)
        emb.add_field(name="Chance Odds", value=show_odd(chance_odds), inline=True)
        emb.add_field(name="Amount", value=f"{stake_amount:.2f}", inline=True)
        emb.add_field(name="Value (Edge)", value=f"{show_odd(100*value)}%", inline=True)
        emb.add_field(name="Market", value=self.arb.show_market_p(), inline=True)
        await form.interaction.followup.send(embed=emb)


class OrderForm(discord.ui.Modal):
    bookie_odds = discord.ui.TextInput(
        label="init",
        style=discord.TextStyle.short,
    )
    chance_odds = discord.ui.TextInput(
        label=f"2. Chance placed odds",
        style=discord.TextStyle.short,
    )
    stake_amount = discord.ui.TextInput(
        label=f"3. Stake amount placed",
        style=discord.TextStyle.short,
    )
    comment = discord.ui.TextInput(
        label=f"4. Additional comment",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="None"
    )

    def __init__(self, arb: Arb, default_stake: float):
        self.bookie_odds.label = f"1. {arb.bookmaker['name']} placed odds"
        self.bookie_odds.default = show_odd(arb.current_odds)
        self.chance_odds.default = show_odd(arb.current_odds)
        self.stake_amount.default = str(default_stake)
        self.interaction: Optional[Interaction] = None
        super().__init__(title=f"PLACE ORDER", timeout=120)

    async def on_submit(self, interaction: Interaction):
        self.interaction = interaction
        
        
async def update_orders(bot: Bot, start_time: datetime, end_time: datetime):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id, bookmaker_id, match_time
        FROM orders
        WHERE match_time>=%s AND match_time<%s
    ''', start_time, end_time)
    for bet_id, bookmaker_id, match_time in data:
        cells = bot.worksheet.findall(f"{bet_id}/{bookmaker_id}", in_column=28)
        bets = await bot.bclient.get_bets(bet_id)
        bet = find(lambda b: b['bookmaker_id'] == bookmaker_id, bets)
        pinn_bet = find(lambda b: b['bookmaker_id'] == bot.bclient.oposition_bookmaker_id, bets)
        updated_time = match_time
        if bet:
            updated_time = datetime.strptime(bet['event_time'], "[%Y-%m-%d %H:%M:%S]")
        to_update = []
        if updated_time == match_time:
            for cell in cells:
                to_update.append(Cell(cell.row, 16, get_bet_koef(bet)))
                to_update.append(Cell(cell.row, 18,  get_bet_koef(pinn_bet)))
        else:
            local_match_time = (updated_time + timedelta(hours=2)).strftime("%d/%m/%y %H:%M")
            for cell in cells:
                to_update.append(Cell(cell.row, 3, local_match_time))
            await bot.db.set("UPDATE orders SET match_time=%s WHERE bet_id=%s", updated_time, bet_id)
        bot.worksheet.update_cells(to_update)


def get_bet_koef(bet: Optional[Dict]) -> Union[str, int]:
    if bet is None:
        return "?"
    return round(bet['koef'], 2)