import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    POLYMARKET_PRIVATE_KEY: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    PROXY_URL: str = os.getenv("PROXY_URL", "https://clob.polymarket.com")
    CHAIN_ID: int = int(os.getenv("CHAIN_ID", "137"))
    RPC_TOKEN: str = os.getenv("RPC_TOKEN", "")

    BUILDER_API_KEY = os.environ.get("BUILDER_API_KEY")
    BUILDER_SECRET = os.environ.get("BUILDER_SECRET")
    BUILDER_PASS_PHRASE = os.environ.get("BUILDER_PASS_PHRASE")
    RELAYER_URL = os.environ.get("RELAYER_URL", "https://relayer-v2.polymarket.com")

config = Config()
