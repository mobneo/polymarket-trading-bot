import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards import main_keyboard, market_actions_keyboard, markets_keyboard
from bot.polymarket_client import PolymarketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
client = PolymarketClient(
    config.POLYMARKET_PRIVATE_KEY, config.PROXY_URL, config.CHAIN_ID
)


class OrderForm(StatesGroup):
    waiting_price = State()
    waiting_size = State()


async def is_admin(message: Message) -> bool:
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Access denied")
        return False
    return True


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not await is_admin(message):
        return
    await message.answer(
        "🤖 Polymarket Trading Bot\nSelect an action:",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "📊 Markets")
async def show_markets(message: Message):
    if not await is_admin(message):
        return
    markets = client.get_markets(20)
    print("Markets:", markets)
    await message.answer("📊 Available markets:", reply_markup=markets_keyboard(markets))


@dp.message(F.text == "💰 Balance")
async def show_balance(message: Message):
    if not await is_admin(message):
        return
    try:
        balance_allowance = client.get_balance_allowance()
        await message.answer(f"💰 Balance:\n<b>{balance_allowance["balance"]} USDC</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")


@dp.message(F.text == "📋 My orders")
async def show_orders(message: Message):
    if not await is_admin(message):
        return
    try:
        orders = client.get_orders()
        if not orders:
            await message.answer("📋 No open orders")
            return

        text = "📋 Open orders:\n\n"
        for o in orders[:10]:
            text += f"ID: <code>{o.get('id', '?')[:10]}...</code>\n"
            text += f"Price: {o.get('price', '?')} | Size: {o.get('size', '?')}\n"
            text += f"Side: {o.get('side', '?')}\n\n"
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")


@dp.message(F.text == "❌ Cancel all")
async def cancel_all_orders(message: Message):
    if not await is_admin(message):
        return
    try:
        client.cancel_all()
        await message.answer("✅ All orders have been cancelled")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")


@dp.callback_query(F.data.startswith("market_"))
async def show_market(callback: CallbackQuery):
    token_id = callback.data.split("_", 1)[1]
    await callback.message.edit_text(
        f"🎯 Token: <code>{token_id}</code>\nSelect an action:",
        parse_mode="HTML",
        reply_markup=market_actions_keyboard(token_id),
    )


@dp.callback_query(F.data == "back_to_markets")
async def back_to_markets(callback: CallbackQuery):
    markets = client.get_markets(20)
    await callback.message.edit_text(
        "📊 Available markets:", reply_markup=markets_keyboard(markets)
    )


@dp.callback_query(F.data.startswith("book_"))
async def show_order_book(callback: CallbackQuery):
    token_id = callback.data.split("_", 1)[1]
    try:
        book = client.get_order_book(token_id)
        text = f"📖 Orderbook for the token:\n<code>{token_id[:10]}...</code>\n\n"

        asks = book.get("asks", [])[:3]
        if asks:
            text += "🔴 ASKS (sell):\n"
            for a in asks:
                text += f"  Price: {a.get('price', '?')}, Size: {a.get('size', '?')}\n"

        bids = book.get("bids", [])[:3]
        if bids:
            text += "\n🟢 BIDS (buy):\n"
            for b in bids:
                text += f"  Price: {b.get('price', '?')}, Size: {b.get('size', '?')}\n"

        await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"❌ Error: {e}")


@dp.callback_query(F.data.startswith("buy_"))
async def start_buy(callback: CallbackQuery, state: FSMContext):
    token_id = callback.data.split("_", 1)[1]
    await state.update_data(token_id=token_id, side="BUY")
    await state.set_state(OrderForm.waiting_price)
    await callback.message.answer("🟢 BUY\nEnter price (0-1):")


@dp.callback_query(F.data.startswith("sell_"))
async def start_sell(callback: CallbackQuery, state: FSMContext):
    token_id = callback.data.split("_", 1)[1]
    await state.update_data(token_id=token_id, side="SELL")
    await state.set_state(OrderForm.waiting_price)
    await callback.message.answer("🔴 SELL\nEnter price (0-1):")


@dp.message(OrderForm.waiting_price)
async def process_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        if not 0 <= price <= 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid price. Please enter a number between 0 and 1:")
        return

    await state.update_data(price=price)
    await state.set_state(OrderForm.waiting_size)
    await message.answer(f"Price: {price}\nEnter quantity:")


@dp.message(OrderForm.waiting_size)
async def process_size(message: Message, state: FSMContext):
    try:
        size = float(message.text)
        if size <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid quantity. Please enter a positive number:")
        return

    data = await state.get_data()
    await state.clear()

    try:
        result = client.place_order(
            token_id=data["token_id"],
            price=data["price"],
            size=size,
            side=data["side"],
        )
        await message.answer(
            f"✅ The order has been placed!\n"
            f"Token: <code>{data['token_id'][:15]}...</code>\n"
            f"Side: {data['side']}\n"
            f"Price: {data['price']}\n"
            f"Size: {size}",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        await message.answer(f"❌ Placement error: {e}", reply_markup=main_keyboard())


def main():
    """Entry point for the bot"""
    logger.info("Starting Polymarket Trading Bot...")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
