import discord
from typing import Optional
from ..Utils import show_odd


class HTTPException(Exception):
    def __init__(self, text: str):
        super().__init__(text)


class Arb:
    def __init__(
            self,
            event_name: str,
            sport: str,
            league: str,
            bookmaker: str,
            link: str,
            start_timestamp: int,
            updated_timestamp: int,
            market: str,
            period: str,
            current_odds: float,
            oposition_odds: float,
            arrow: str,
            oposition_arrow: str
    ):
        self.event_name = event_name
        self.sport = sport
        self.league = league
        self.bookmaker = bookmaker
        self.link = link
        self.start_at = start_timestamp
        self.upated_at = updated_timestamp
        self.disappeared_at: Optional[int] = None
        self.market = market
        self.period = period
        self.current_odds = current_odds
        self.oposition_odds = oposition_odds
        self.arrow = arrow
        self.oposition_arrow = oposition_arrow

    def __eq__(self, other):
        return self.slug == other.slug

    @property
    def value(self) -> float:
        inversion = 1/self.current_odds + 1/self.oposition_odds
        return 100/inversion - 100

    @property
    def last_acceptable_odds(self) -> float:
        inversion = 1/1.005 - 1/self.oposition_odds
        return 1/inversion

    @property
    def slug(self):
        return f"{self.event_name}|{self.bookmaker}"

    def to_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"🔔 {self.bookmaker.upper()} | {show_odd(self.current_odds)} | {show_odd(self.value)}%",
            colour=0x2a2ac7
        )
        emb.add_field(name="Event Name", value=self.event_name, inline=True)
        emb.add_field(name="Sport", value=self.sport, inline=True)
        emb.add_field(name="Bookie", value=self.bookmaker, inline=True)
        emb.add_field(name="Match Starts", value=f"<t:{self.start_at}:R>", inline=True)
        emb.add_field(name="Market", value=f"{self.market} + [{self.period}]" if self.period else self.market, inline=True)
        emb.add_field(name="Current Odds", value=show_odd(self.current_odds), inline=True)
        emb.add_field(name="Last Acceptable Odds", value=show_odd(self.last_acceptable_odds), inline=True)
        emb.add_field(name="Value (Edge)", value=f"{show_odd(self.value)}%", inline=True)
        emb.add_field(name="Bet Link", value=f"[Go to {self.bookmaker}]({self.link})", inline=True)
        emb.set_thumbnail(url="https://cdn.discordapp.com/attachments/1131671133419212840/1131672060528165066/bet_img.png")
        return emb