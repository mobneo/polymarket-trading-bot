from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Hourly BTC Market")],
            [KeyboardButton(text="💰 Balance")],
            [KeyboardButton(text="📋 My orders")],
            [KeyboardButton(text="🔄 Clear stuck txs")],
            [KeyboardButton(text="❌ Cancel all")]
        ],
        resize_keyboard=True
    )
    return keyboard

def balance_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Check Balance", callback_data="check_balance"),
                InlineKeyboardButton(text="✅ Approve USDC", callback_data="approve_usdc"),
            ],
            [
                InlineKeyboardButton(text="🔓 Approve CTF", callback_data="approve_ctf"),
                InlineKeyboardButton(text="🔑 Approve All", callback_data="approve_all"),
            ],
            [
                InlineKeyboardButton(text="🪙 Approve pUSD (CTF)", callback_data="approve_pusd_ctf"),
                InlineKeyboardButton(text="🪙 Approve pUSD (Exchange)", callback_data="approve_pusd_exchange"),
            ],
            [
                InlineKeyboardButton(text="🪙 Approve pUSD All", callback_data="approve_pusd_all"),
                InlineKeyboardButton(text="📊 Check Approvals", callback_data="check_approvals"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main"),
            ]
        ]
    )
    return keyboard

def approve_confirmation_keyboard(approve_type: str):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes", callback_data=f"confirm_approve_{approve_type}"),
                InlineKeyboardButton(text="❌ No", callback_data="cancel_approve"),
            ]
        ]
    )
    return keyboard

def market_actions_keyboard(token_id: str):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 Order Book", callback_data=f"book_{token_id}"),
            ],
            [
                InlineKeyboardButton(text="🟢 Buy", callback_data=f"buy_{token_id}"),
                InlineKeyboardButton(text="🔴 Sell", callback_data=f"sell_{token_id}"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Markets", callback_data="back_to_markets"),
            ]
        ]
    )
    return keyboard

def markets_keyboard(markets):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for market in markets[:10]:
        token_id = market.get('tokens', [{}])[0].get('token_id', '')
        if token_id:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"📈 {market.get('question', 'Market')[:30]}...",
                    callback_data=f"market_{token_id}"
                )
            ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")
    ])
    return keyboard

def get_hourly_market_keyboard():
    """Inline keyboard for the hourly BTC market."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Long", callback_data="hourly_buy_yes"),
            InlineKeyboardButton(text="🔴 Short", callback_data="hourly_buy_no"),
        ],
        [
            # InlineKeyboardButton(text="🟢 Buy Down", callback_data="hourly_buy_no"),
            # InlineKeyboardButton(text="🔴 Sell Up", callback_data="hourly_sell_yes"),
        ],
        [
            InlineKeyboardButton(text="🔄 Refresh", callback_data="refresh_hourly_market"),
            InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main"),
        ]
    ])
    return keyboard

def order_type_keyboard():
    """Keyboard for selecting market or limit order"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Market Order", callback_data="order_type_market"),
            InlineKeyboardButton(text="📈 Limit Order", callback_data="order_type_limit"),
        ],
        [
            InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_order_type"),
        ]
    ])
    return keyboard
