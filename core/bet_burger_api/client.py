from aiohttp import ClientSession
from typing import List, Optional, Dict
from .types import HTTPException, Arb
import json
from discord.utils import find


API_URL = "https://{}.betburger.com/api/v1/{}"


class BetClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.directories = {}
        self.filters: List[Dict] = []
        self.bookmakers = {}
        self.required_bookmaker_id: Optional[int] = None
        with open("core/bet_burger_api/headers.json") as f:
            self.headers = json.load(f)
        with open("core/bet_burger_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)

    async def connect(self, api_key: str):
        self.api_key = api_key
        self.session = ClientSession()
        self.directories = await self._make_request("directories")
        bet_filters = await self._make_request("search_filters")
        self.filters = [find(lambda f: f['title'] == "BOT-ALL", bet_filters)]
        self.required_bookmaker_id = int(self.filters[0]['bookmakers2'][0])
        for bookmaker_id in self.filters[0]["bookmakers1"]:
            bookmaker_id = int(bookmaker_id)
            if bookmaker_id == self.required_bookmaker_id:
                continue
            bookmaker = find(lambda b: b['id'] == bookmaker_id, self.directories["bookmakers"]["arbs"])
            bookmaker_filter = find(lambda f: f['title'] == f"BOT-{bookmaker['name'].upper()}", bet_filters)
            self.bookmakers[bookmaker_id] = bookmaker
            self.filters.append(bookmaker_filter)

    async def _make_request(self, endpoint: str, params: Optional[Dict] = None, domain="api-pr"):
        url = API_URL.format(domain, endpoint)
        params = params or {}
        params['access_token'] = self.api_key
        params['locale'] = "en"
        async with self.session.get(url=url, params=params, headers=self.headers) as resp:
            if resp.ok:
                return await resp.json()
            text = await resp.text()
            raise HTTPException(f"Unable to access BetBurger API. Please check if the API_KEY is valid.\n{text}")

    async def get_arbs(self) -> List[Arb]:
        arbs = []
        for i, fil in enumerate(self.filters):
            params = {'search_filter[]': [fil['id']], 'per_page': 20}
            data = await self._make_request("arbs/pro_search", params, domain="rest-api-pr")
            if len(data['arbs']) >= 20 and i == 0:
                # The general filter reached the maximum number of arbs (20)
                # So let's search using filters for each bookmaker separately
                continue
            for a in data["arbs"]:
                bet1 = find(lambda b: b['id'] == a['bet1_id'], data["bets"])
                bet2 = find(lambda b: b['id'] == a['bet2_id'], data["bets"])
                if bet1['bookmaker_id'] == self.required_bookmaker_id:
                    bet1, bet2 = bet2, bet1
                sport = find(lambda m: m['id'] == a['sport_id'], self.directories['sports'])
                bookmaker = self.bookmakers[bet1['bookmaker_id']]
                if not bet1['bookmaker_event_direct_link']:
                    raise HTTPException("Invalid Bet Burger API_KEY.")
                if bookmaker['url'][-1] == bet1['bookmaker_event_direct_link'][0] == "/":
                    link = bookmaker['url'][:-1] + bet1['bookmaker_event_direct_link']
                else:
                    link = bookmaker['url'] + bet1['bookmaker_event_direct_link']
                market_dir = find(lambda m: m['id'] == bet1['market_and_bet_type'], self.directories['market_variations'])
                market_text_model = self.market_acronyms[market_dir['title']]
                market = market_text_model.replace("%s", str(bet1['market_and_bet_type_param']))
                arb = Arb(
                    event_name=bet1['event_name'],
                    sport=sport['name'],
                    bookmaker=bookmaker['name'],
                    link=link,
                    start_timestamp=a['started_at'],
                    updated_timestamp=a['updated_at'],
                    market=market,
                    current_odds=bet1['koef'],
                    oposition_odds=bet2['koef']
                )
                if arb not in arbs:
                    arbs.append(arb)
            if i == 0:
                # General filter got all arbs
                break
        return arbs

    async def close(self):
        await self.session.close()