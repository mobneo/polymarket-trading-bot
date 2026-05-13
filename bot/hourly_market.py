# bot/hourly_market.py
import logging
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# --- Configuration ---
ET_TIMEZONE = pytz.timezone('US/Eastern')
BASE_SLUG_TEMPLATE = "bitcoin-up-or-down-{month}-{day}-{hour}{ampm}-et"


def get_current_hour_market_slug() -> str:
    """
    Generates the slug for the current hourly Bitcoin market based on ET.
    Example: "bitcoin-up-or-down-may-13-2026-2pm-et"
    """
    now_et = datetime.now(ET_TIMEZONE)

    # --- Изменения начинаются здесь ---
    # 1. Месяц: полное имя на английском в нижнем регистре
    month = now_et.strftime("%B").lower()  # 'may'

    # 2. День: число без ведущего нуля
    day = str(now_et.day)  # '13'

    # 3. Год: четыре цифры
    year = str(now_et.year)  # '2026'

    # 4. Час: в 12-часовом формате без ведущего нуля
    hour_12 = now_et.strftime("%-I")  # '2' (может не работать на Windows)
    # --- Безопасный способ получить час для любой ОС ---
    hour_24 = now_et.hour
    hour_12_display = hour_24 % 12
    if hour_12_display == 0:
        hour_12_display = 12
    hour = str(hour_12_display)  # '2'

    # 5. AM/PM: в нижнем регистре
    ampm = now_et.strftime("%p").lower()  # 'pm'
    # --- Конец изменений ---

    # Собираем slug в правильном порядке: месяц-день-год-час
    slug = f"bitcoin-up-or-down-{month}-{day}-{year}-{hour}{ampm}-et"

    logger.info(f"Generated slug for current hour ({now_et.strftime('%Y-%m-%d %H:%M %Z')}): {slug}")
    return slug


def get_market_expiry_time() -> datetime:
    now_et = datetime.now(ET_TIMEZONE)
    expiry_et = now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return expiry_et


def get_time_until_expiry() -> timedelta:
    expiry = get_market_expiry_time()
    now = datetime.now(ET_TIMEZONE)
    time_left = expiry - now
    if time_left.total_seconds() < 0:
        time_left = timedelta(seconds=0)
    return time_left


class HourlyBitcoinMarket:
    def __init__(self, client):
        self.client = client
        self.slug = get_current_hour_market_slug()
        self.expiry_time = get_market_expiry_time()
        self._event_data = None
        self._market_data = None
        self._order_book = None
        self._clob_token_ids = None

    def _get_event_by_slug(self) -> Optional[Dict[str, Any]]:
        if self._event_data is not None:
            return self._event_data

        import requests
        url = f"https://gamma-api.polymarket.com/events/slug/{self.slug}"

        logger.info(f"Fetching event data from Gamma API: {url}")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            self._event_data = response.json()
            logger.info(f"Successfully fetched event data for slug: {self.slug}")
            return self._event_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch event data from Gamma API: {e}")
            return None

    def find_current_market(self) -> Optional[Dict[str, Any]]:
        if self._market_data is not None:
            return self._market_data

        event_data = self._get_event_by_slug()
        if not event_data or not isinstance(event_data, dict):
            logger.error("Invalid event data received from Gamma API")
            return None

        markets = event_data.get('markets')
        if not markets or not isinstance(markets, list) or len(markets) == 0:
            logger.error(f"No 'markets' list found in event data")
            return None

        self._market_data = markets[0]
        logger.info(f"Found market: {self._market_data.get('question')}")

        clob_token_ids_str = self._market_data.get('clobTokenIds')
        if clob_token_ids_str:
            import json
            try:
                self._clob_token_ids = json.loads(clob_token_ids_str)
                logger.info(f"Loaded CLOB token IDs: {self._clob_token_ids}")
            except json.JSONDecodeError:
                logger.error("Failed to parse clobTokenIds")
                self._clob_token_ids = []

        return self._market_data

    def get_order_book(self) -> Optional[Dict[str, Any]]:
        if self._order_book is not None:
            return self._order_book

        market = self.find_current_market()
        if not market:
            return None

        clob_token_ids = self._clob_token_ids
        if not clob_token_ids or len(clob_token_ids) < 1:
            logger.error("No CLOB token ID found for the Yes outcome")
            return None

        yes_token_id = clob_token_ids[0]

        logger.info(f"Fetching order book for token ID: {yes_token_id}")
        try:
            self._order_book = self.client.get_order_book(yes_token_id)
            return self._order_book
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            return None

    def get_prices(self) -> Optional[Dict[str, float]]:
        order_book = self.get_order_book()
        if not order_book:
            return None

        yes_bid = 0.0
        yes_ask = 0.0

        if order_book.get('bids') and len(order_book['bids']) > 0:
            yes_bid = float(order_book['bids'][0].get('price', 0))

        if order_book.get('asks') and len(order_book['asks']) > 0:
            yes_ask = float(order_book['asks'][0].get('price', 0))

        return {
            'yes_bid': yes_bid,
            'yes_ask': yes_ask,
            'no_bid': 1.0 - yes_ask,
            'no_ask': 1.0 - yes_bid,
        }

    def get_market_info(self) -> Optional[Dict[str, Any]]:
        market = self.find_current_market()
        if not market:
            return None

        prices = self.get_prices()
        if not prices:
            prices = {'yes_bid': 0.0, 'yes_ask': 0.0, 'no_bid': 0.0, 'no_ask': 0.0}

        for key in prices:
            prices[key] = float(prices[key]) if prices[key] is not None else 0.0

        time_left = get_time_until_expiry()

        return {
            'slug': self.slug,
            'question': market.get('question', 'Unknown'),
            'expires_at': self.expiry_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'time_left': str(time_left).split('.')[0] if time_left.total_seconds() > 0 else '0:00:00',
            'yes_bid': prices.get('yes_bid', 0.0),
            'yes_ask': prices.get('yes_ask', 0.0),
            'no_bid': prices.get('no_bid', 0.0),
            'no_ask': prices.get('no_ask', 0.0),
        }

    def get_clob_token_ids(self) -> Optional[list]:
        self.find_current_market()
        return self._clob_token_ids
