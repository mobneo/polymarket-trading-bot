from py_clob_client_v2 import ClobClient, ApiCreds
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams, OrderArgs, OrderType
import logging

logger = logging.getLogger(__name__)


class PolymarketClient:
    def __init__(self, private_key: str, proxy_url: str, chain_id: int = 137):
        self.client = ClobClient(
            host=proxy_url,
            key=private_key,
            chain_id=chain_id,
        )

        try:
            creds = self.client.create_or_derive_api_key()
            logger.info("API credentials generated successfully")

            self.client = ClobClient(
                host=proxy_url,
                key=private_key,
                chain_id=chain_id,
                creds=creds,
            )
            logger.info("Polymarket client initialized with full authentication")
        except Exception as e:
            logger.error(f"Failed to create API credentials: {e}")
            raise

    def get_markets(self, limit: int = 20):
        try:
            return self.client.get_markets()
        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

    def get_order_book(self, token_id: str):
        try:
            return self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Failed to get order book: {e}")
            return {}

    def place_order(self, token_id: str, price: float, size: float, side: str):
        try:
            order = OrderArgs(price=price, size=size, side=side, token_id=token_id)
            signed = self.client.create_order(order)
            # return self.client.post_order(signed, OrderType.GTC)
            return self.client.post_order(signed)
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    def get_orders(self):
        try:
            return self.client.get_open_orders()
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []

    def cancel_order(self, order_id: str):
        try:
            return self.client.cancel_order(order_id)
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise

    def cancel_all(self):
        try:
            return self.client.cancel_all()
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            raise

    def get_balance_allowance(self):
        try:
            return self.client.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None
