from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Markets"), KeyboardButton(text="📋 My orders")],
            [KeyboardButton(text="💰 Balance"), KeyboardButton(text="❌ Cancel all")],
        ],
        resize_keyboard=True,
    )


def markets_keyboard(markets: list):
    kb = []
    for m in markets[:10]:
        tokens = m.get('tokens', [])
        if tokens:
            token_id = tokens[0].get('token_id', '')
            title = m.get('question', 'Unknown')[:50]
            kb.append(
                [InlineKeyboardButton(text=f"📈 {title}", callback_data=f"market_{token_id}")]
            )
    return InlineKeyboardMarkup(inline_keyboard=kb)


def market_actions_keyboard(token_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Orderbook", callback_data=f"book_{token_id}")],
            [
                InlineKeyboardButton(text="🟢 BUY", callback_data=f"buy_{token_id}"),
                InlineKeyboardButton(text="🔴 SELL", callback_data=f"sell_{token_id}"),
            ],
            [InlineKeyboardButton(text="« Back to markets", callback_data="back_to_markets")],
        ]
    )
