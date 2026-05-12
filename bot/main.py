import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards import main_keyboard, market_actions_keyboard, markets_keyboard, balance_keyboard, approve_confirmation_keyboard
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

async def safe_edit_text(message, text, parse_mode="HTML", reply_markup=None):
    try:
        await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise e

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
    await message.answer("📊 Available markets:", reply_markup=markets_keyboard(markets))


@dp.message(F.text == "💰 Balance")
async def show_balance(message: Message):
    if not await is_admin(message):
        return
    try:
        balance_info = client.get_wallet_balance()
        print("balance info:", balance_info)

        if balance_info:
            usdc_balance = balance_info.get('usdc_balance', 0)
            usdc_balance_formatted = usdc_balance / 1e6 if usdc_balance else 0

            pusd_balance = balance_info.get('pusd_balance', 0)
            pusd_balance_formatted = pusd_balance / 1e6 if pusd_balance else 0

            # Platform balance is already in pUSD
            platform_balance = balance_info.get('platform_balance', 0)
            platform_balance_formatted = platform_balance / 1e6 if platform_balance else 0

            pol_balance = balance_info.get('pol_balance_formatted', 0)

            allowances = balance_info.get('allowances', {})
            ctf_allowance = allowances.get('conditional_tokens', 0)
            exchange_allowance = allowances.get('exchange', 0)
            ctf_approved = balance_info.get('conditional_tokens_approved', False)

            ctf_allowance_formatted = "∞" if ctf_allowance == 2**256 - 1 else f"{ctf_allowance / 1e6:.2f}"
            exchange_allowance_formatted = "∞" if exchange_allowance == 2**256 - 1 else f"{exchange_allowance / 1e6:.2f}"

            text = (
                f"💰 <b>Wallet Information</b>\n\n"
                f"📊 <b>On-Chain USDC Balance:</b>\n"
                f"   {usdc_balance_formatted:,.2f} USDC\n\n"
                f"🪙 <b>On-Chain pUSD Balance:</b>\n"
                f"   {pusd_balance_formatted:,.2f} pUSD\n\n"
                f"🏦 <b>Polymarket Platform Balance (pUSD):</b>\n"
                f"   {platform_balance_formatted:,.2f} pUSD\n\n"
                f"⛽ <b>POL Balance (for gas):</b>\n"
                f"   {pol_balance:.6f} POL\n\n"
                f"✅ <b>USDC Allowances:</b>\n"
                f"   CTF Contract: {ctf_allowance_formatted} USDC\n"
                f"   Exchange Contract: {exchange_allowance_formatted} USDC\n\n"
                f"🪙 <b>pUSD Allowances:</b>\n"
                f"   CTF Contract: {balance_info.get('pusd_ctf_allowance_formatted', '0')} pUSD\n"
                f"   Exchange Contract: {balance_info.get('pusd_exchange_allowance_formatted', '0')} pUSD\n\n"
                f"🔓 <b>CTF Approval:</b>\n"
                f"   {'✅ Approved' if ctf_approved else '❌ Not approved'}\n\n"
                f"💡 <i>pUSD approvals are needed to trade using platform balance</i>"
            )
        else:
            balance_allowance = client.get_balance_allowance()
            text = f"💰 Balance:\n<b>{balance_allowance.get('balance', '0')} USDC</b>"

        # For new messages, use answer (not edit)
        await message.answer(text, parse_mode="HTML", reply_markup=balance_keyboard())

    except Exception as e:
        logger.error(f"Error showing balance: {e}")
        await message.answer(f"❌ Error getting balance: {e}")


@dp.callback_query(F.data == "check_balance")
async def check_balance(callback: CallbackQuery):
    await callback.answer("Updating balance...")
    try:
        balance_info = client.get_wallet_balance()

        if balance_info:
            usdc_balance = balance_info.get('usdc_balance', 0)
            usdc_balance_formatted = usdc_balance / 1e6 if usdc_balance else 0

            pusd_balance = balance_info.get('pusd_balance', 0)
            pusd_balance_formatted = pusd_balance / 1e6 if pusd_balance else 0

            # Get platform balance - this should show pUSD
            platform_balance = balance_info.get('platform_balance', 0)
            platform_balance_formatted = platform_balance / 1e6 if platform_balance else 0

            pol_balance = balance_info.get('pol_balance_formatted', 0)

            allowances = balance_info.get('allowances', {})
            ctf_allowance = allowances.get('conditional_tokens', 0)
            exchange_allowance = allowances.get('exchange', 0)
            ctf_approved = balance_info.get('conditional_tokens_approved', False)

            ctf_allowance_formatted = "∞" if ctf_allowance == 2**256 - 1 else f"{ctf_allowance / 1e6:.2f}"
            exchange_allowance_formatted = "∞" if exchange_allowance == 2**256 - 1 else f"{exchange_allowance / 1e6:.2f}"

            text = (
                f"💰 <b>Wallet Information</b>\n\n"
                f"📊 <b>On-Chain USDC Balance:</b>\n"
                f"   {usdc_balance_formatted:,.2f} USDC\n\n"
                f"🪙 <b>On-Chain pUSD Balance:</b>\n"
                f"   {pusd_balance_formatted:,.2f} pUSD\n\n"
                f"🏦 <b>Polymarket Platform Balance (pUSD):</b>\n"
                f"   {platform_balance_formatted:,.2f} pUSD\n\n"
                f"⛽ <b>POL Balance (for gas):</b>\n"
                f"   {pol_balance:.6f} POL\n\n"
                f"✅ <b>Allowances:</b>\n"
                f"   CTF Contract: {ctf_allowance_formatted} USDC\n"
                f"   Exchange Contract: {exchange_allowance_formatted} USDC\n\n"
                f"🔓 <b>CTF Approval:</b>\n"
                f"   {'✅ Approved' if ctf_approved else '❌ Not approved'}\n\n"
                f"💡 <i>Note: pUSD is Polymarket's native token on the platform</i>"
            )
        else:
            balance_allowance = client.get_balance_allowance()
            text = f"💰 Balance:\n<b>{balance_allowance.get('balance', '0')} USDC</b>"

        # Use safe edit instead of direct edit
        await safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=balance_keyboard())

    except Exception as e:
        logger.error(f"Error checking balance: {e}")
        await callback.message.answer(f"❌ Error: {e}")


@dp.callback_query(F.data == "check_approvals")
async def check_approvals(callback: CallbackQuery):
    await callback.answer("Checking approvals...")
    try:
        balance_info = client.get_wallet_balance()

        if balance_info:
            allowances = balance_info.get('allowances', {})
            ctf_allowance = allowances.get('conditional_tokens', 0)
            exchange_allowance = allowances.get('exchange', 0)
            ctf_approved = balance_info.get('conditional_tokens_approved', False)

            ctf_allowance_status = "✅ Approved" if ctf_allowance > 0 else "❌ Not approved"
            if ctf_allowance == 2**256 - 1:
                ctf_allowance_status = "✅ Fully approved (unlimited)"

            exchange_allowance_status = "✅ Approved" if exchange_allowance > 0 else "❌ Not approved"
            if exchange_allowance == 2**256 - 1:
                exchange_allowance_status = "✅ Fully approved (unlimited)"

            text = (
                f"🔍 <b>Approval Status</b>\n\n"
                f"📝 <b>USDC Allowances:</b>\n"
                f"   CTF Contract: {ctf_allowance_status}\n"
                f"   Exchange Contract: {exchange_allowance_status}\n\n"
                f"🔓 <b>Conditional Tokens:</b>\n"
                f"   Exchange approved: {'✅ Yes' if ctf_approved else '❌ No'}\n\n"
                f"💡 <i>Use the buttons below to set approvals</i>"
            )
        else:
            text = "❌ Unable to get approval information"

        await safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=balance_keyboard())

    except Exception as e:
        logger.error(f"Error checking approvals: {e}")
        await callback.message.answer(f"❌ Error: {e}")

@dp.callback_query(F.data == "approve_usdc")
async def approve_usdc_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("usdc")
    await callback.message.edit_text(
        "⚠️ <b>Confirm USDC Approval</b>\n\n"
        "This will approve the Exchange and Conditional Tokens contracts to spend your USDC.\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "approve_ctf")
async def approve_ctf_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("ctf")
    await callback.message.edit_text(
        "⚠️ <b>Confirm CTF Approval</b>\n\n"
        "This will allow the Exchange contract to manage your Conditional Tokens.\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "approve_all")
async def approve_all_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("all")
    await callback.message.edit_text(
        "⚠️ <b>Confirm All Approvals</b>\n\n"
        "This will:\n"
        "1. Approve USDC for CTF contract\n"
        "2. Approve USDC for Exchange contract\n"
        "3. Approve Conditional Tokens for Exchange contract\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("confirm_approve_"))
async def execute_approval(callback: CallbackQuery):
    approve_type = callback.data.split("_")[2]
    await callback.answer(f"Processing {approve_type} approval...")

    try:
        status_message = await callback.message.edit_text(
            f"🔄 Processing {approve_type} approval...\nPlease wait (up to 5 minutes)..."
        )

        if approve_type == "usdc":
            tx_hashes = client.approve_usdc()
            if tx_hashes and len(tx_hashes) > 0:
                text = (
                    f"✅ <b>USDC Approval Successful!</b>\n\n"
                    f"Transaction hashes:\n"
                )
                for tx_hash in tx_hashes:
                    text += f"<code>{tx_hash}</code>\n"
                explorer_url = "https://amoy.polygonscan.com" if not client.is_mainnet else "https://polygonscan.com"
                text += f"\n🔗 <a href='{explorer_url}/tx/{tx_hashes[0]}'>View on Explorer</a>"
            else:
                text = "❌ USDC approval failed or already approved"

        elif approve_type == "ctf":
            tx_hash = client.approve_conditional_tokens()
            if tx_hash and tx_hash != True:
                explorer_url = "https://amoy.polygonscan.com" if not client.is_mainnet else "https://polygonscan.com"
                text = (
                    f"✅ <b>CTF Approval Successful!</b>\n\n"
                    f"Transaction hash:\n<code>{tx_hash}</code>\n\n"
                    f"🔗 <a href='{explorer_url}/tx/{tx_hash}'>View on Explorer</a>"
                )
            elif tx_hash == True:
                text = "✅ CTF approval already set"
            else:
                text = "❌ CTF approval failed"

        elif approve_type == "all":
            result = client.setup_all_approvals()
            text = "✅ <b>All Approvals Completed!</b>\n\n"
            if result.get('usdc_approvals') and len(result['usdc_approvals']) > 0:
                text += "USDC approvals:\n"
                for tx_hash in result['usdc_approvals']:
                    text += f"<code>{tx_hash}</code>\n"
            if result.get('ctf_approval') and result['ctf_approval'] != True:
                text += f"\nCTF approval:\n<code>{result['ctf_approval']}</code>\n"
            text += "\n🔗 Check explorer for details"
        elif approve_type == "pusd_ctf":
            tx_hash = client.approve_pusd_for_ctf()
            if tx_hash and tx_hash != True:
                explorer_url = "https://polygonscan.com" if client.is_mainnet else "https://amoy.polygonscan.com"
                text = (
                    f"✅ <b>pUSD CTF Approval Successful!</b>\n\n"
                    f"Transaction hash:\n<code>{tx_hash}</code>\n\n"
                    f"🔗 <a href='{explorer_url}/tx/{tx_hash}'>View on Explorer</a>\n\n"
                    f"Now the CTF contract can spend your platform pUSD."
                )
            elif tx_hash == True:
                text = "✅ pUSD CTF approval already set"
            else:
                text = "❌ pUSD CTF approval failed"

        elif approve_type == "pusd_exchange":
            tx_hash = client.approve_pusd_for_exchange()
            if tx_hash and tx_hash != True:
                explorer_url = "https://polygonscan.com" if client.is_mainnet else "https://amoy.polygonscan.com"
                text = (
                    f"✅ <b>pUSD Exchange Approval Successful!</b>\n\n"
                    f"Transaction hash:\n<code>{tx_hash}</code>\n\n"
                    f"🔗 <a href='{explorer_url}/tx/{tx_hash}'>View on Explorer</a>\n\n"
                    f"Now the Exchange contract can spend your platform pUSD."
                )
            elif tx_hash == True:
                text = "✅ pUSD Exchange approval already set"
            else:
                text = "❌ pUSD Exchange approval failed"

        elif approve_type == "pusd_all":
            result = client.approve_pusd_all()
            text = "✅ <b>All pUSD Approvals Completed!</b>\n\n"
            if result.get('ctf_approval') and result['ctf_approval'] != True:
                text += f"CTF approval:\n<code>{result['ctf_approval']}</code>\n\n"
            if result.get('exchange_approval') and result['exchange_approval'] != True:
                text += f"Exchange approval:\n<code>{result['exchange_approval']}</code>\n"
            if not result.get('ctf_approval') and not result.get('exchange_approval'):
                text += "All approvals were already set!"
            text += "\n🔗 Check explorer for details"
        else:
            text = "❌ Unknown approval type"

        await status_message.edit_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        await asyncio.sleep(2)
        balance_info = client.get_wallet_balance()

        if balance_info:
            usdc_balance = balance_info.get('usdc_balance', 0)
            usdc_balance_formatted = usdc_balance / 1e6 if usdc_balance else 0
            platform_balance = balance_info.get('platform_balance', 0)
            platform_balance_formatted = platform_balance / 1e6 if platform_balance else 0
            balance_text = f"💰 Updated Balance:\n<b>On-Chain: {usdc_balance_formatted:,.2f} USDC</b>\n<b>Platform: {platform_balance_formatted:,.2f} USDC</b>"
            await callback.message.answer(balance_text, parse_mode="HTML", reply_markup=balance_keyboard())
        else:
            await callback.message.answer("💰 Use /start to return to menu", reply_markup=main_keyboard())

    except Exception as e:
        logger.error(f"Error executing approval: {e}")
        await callback.message.edit_text(
            f"❌ <b>Approval Failed</b>\n\nError: {str(e)}",
            parse_mode="HTML"
        )


@dp.callback_query(F.data == "cancel_approve")
async def cancel_approval(callback: CallbackQuery):
    await callback.answer("Approval cancelled")
    await check_balance(callback)


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)


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

@dp.message(F.text == "🔄 Clear stuck txs")
async def clear_stuck_transactions(message: Message):
    if not await is_admin(message):
        return
    try:
        await message.answer("🔄 Clearing stuck transactions...")
        result = client.clear_pending_transactions()
        if result:
            await message.answer("✅ Stuck transactions cleared!\nPlease try approval again.", reply_markup=balance_keyboard())
        else:
            await message.answer("✅ No stuck transactions found.\nYou can try approval now.", reply_markup=balance_keyboard())
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


@dp.callback_query(F.data == "approve_pusd_ctf")
async def approve_pusd_ctf_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("pusd_ctf")
    await callback.message.edit_text(
        "⚠️ <b>Confirm pUSD Approval for CTF Contract</b>\n\n"
        "This will approve the CTF contract to spend your pUSD on Polymarket.\n\n"
        "This is necessary for interacting with markets using pUSD.\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "approve_pusd_exchange")
async def approve_pusd_exchange_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("pusd_exchange")
    await callback.message.edit_text(
        "⚠️ <b>Confirm pUSD Approval for Exchange Contract</b>\n\n"
        "This will approve the Exchange contract to spend your pUSD on Polymarket.\n\n"
        "This is necessary for trading on Polymarket.\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "approve_pusd_all")
async def approve_pusd_all_request(callback: CallbackQuery):
    keyboard = approve_confirmation_keyboard("pusd_all")
    await callback.message.edit_text(
        "⚠️ <b>Confirm All pUSD Approvals</b>\n\n"
        "This will:\n"
        "1. Approve CTF contract to spend your pUSD\n"
        "2. Approve Exchange contract to spend your pUSD\n\n"
        "These approvals are required for trading on Polymarket with pUSD.\n\n"
        "Do you want to continue?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("book_"))
async def show_order_book(callback: CallbackQuery):
    token_id = callback.data.split("_", 1)[1]
    try:
        book = client.get_order_book(token_id)
        text = f"📖 Orderbook for token:\n<code>{token_id[:10]}...</code>\n\n"

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
            f"✅ Order placed!\n"
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
    logger.info("Starting Polymarket Trading Bot...")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
