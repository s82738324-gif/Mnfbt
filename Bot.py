import asyncio
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "9227515881:AAEyoLwJQwt08OMQcB9u90EZ6ZCYWh6Xyvo"
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# временное хранилище сделок (в памяти; для продакшена — БД)
deals = {}
deal_counter = 0

class OfferForm(StatesGroup):
    waiting_target = State()

# /of <ссылка> <цена> <gram|stars>
@dp.message(F.text.startswith("/of"))
async def cmd_of(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Формат: /of <ссылка_на_NFT> <цена> <gram|stars>")
        return
    _, nft_link, price, currency = parts
    currency = currency.lower()
    if currency not in ("gram", "stars"):
        await message.answer("Валюта должна быть gram или stars")
        return
    if not re.match(r"^https?://", nft_link):
        await message.answer("Ссылка должна начинаться с http:// или https://")
        return
    if not price.isdigit():
        await message.answer("Цена должна быть числом")
        return

    await state.update_data(nft_link=nft_link, price=int(price), currency=currency)
    await message.answer("Кому отправить предложение? Укажите @username или ID пользователя.")
    await state.set_state(OfferForm.waiting_target)

@dp.message(OfferForm.waiting_target)
async def process_target(message: Message, state: FSMContext):
    target = message.text.strip()
    data = await state.get_data()
    await state.clear()

    global deal_counter
    deal_counter += 1
    deal_id = str(deal_counter)
    deals[deal_id] = {
        "seller_id": message.from_user.id,
        "seller_name": message.from_user.full_name,
        "nft_link": data["nft_link"],
        "price": data["price"],
        "currency": data["currency"],
        "status": "pending",
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"accept:{deal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline:{deal_id}"),
    ]])
    text = (
        f"📨 Предложение от {message.from_user.full_name}\n"
        f"NFT: {data['nft_link']}\n"
        f"Цена: {data['price']} {data['currency']}"
    )
    try:
        await bot.send_message(target, text, reply_markup=kb)
        await message.answer("Предложение отправлено.")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")

@dp.callback_query(F.data.startswith("decline:"))
async def decline(cb: CallbackQuery):
    deal_id = cb.data.split(":")[1]
    deals[deal_id]["status"] = "declined"
    await cb.message.edit_text("❌ Предложение отклонено")
    await cb.answer()

@dp.callback_query(F.data.startswith("accept:"))
async def accept(cb: CallbackQuery):
    deal_id = cb.data.split(":")[1]
    deal = deals[deal_id]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"confirm:{deal_id}"),
        InlineKeyboardButton(text="Нет", callback_data=f"cancel:{deal_id}"),
    ]])
    await cb.message.edit_text(
        "Вы хотите отдать этот NFT этому пользователю?",
        reply_markup=kb
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel(cb: CallbackQuery):
    deal_id = cb.data.split(":")[1]
    deals[deal_id]["status"] = "cancelled"
    await cb.message.edit_text("❌ Сделка отменена")
    await cb.answer()

@dp.callback_query(F.data.startswith("confirm:"))
async def confirm(cb: CallbackQuery):
    deal_id = cb.data.split(":")[1]
    deal = deals[deal_id]
    if deal["currency"] == "stars":
        await bot.send_invoice(
            chat_id=cb.from_user.id,
            title="Оплата NFT",
            description=f"NFT: {deal['nft_link']}",
            payload=f"deal:{deal_id}",
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=deal["price"])],
        )
        await cb.message.edit_text("Счёт выставлен. После оплаты сообщите продавцу.")
    else:
        await cb.message.edit_text(
            "Оплата Gram (TON) вне Bot API. Свяжитесь с продавцом вручную."
        )
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def on_paid(message: Message):
    payload = message.successful_payment.invoice_payload
    deal_id = payload.split(":")[1]
    deal = deals.get(deal_id, {})
    deal["status"] = "paid"
    await message.answer(
        "✅ Оплата получена. Передайте NFT продавцу вручную и попросите подтвердить."
    )
    seller_id = deal.get("seller_id")
    if seller_id:
        try:
            await bot.send_message(
                seller_id,
                f"💰 Покупатель оплатил {deal['price']} Stars по сделке #{deal_id}. "
                f"Передайте NFT вручную."
            )
        except Exception:
            pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
