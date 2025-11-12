import os
import ast
from dotenv import load_dotenv
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.keyboard import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from datetime import datetime, timedelta


load_dotenv()
# === НАСТРОЙКИ ===
TOKEN = os.getenv("BOT_TOKEN")  # строка токена из .env
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

_admin_env = os.getenv("ADMIN_ID", "[]")
try:
    ADMIN_ID = list(ast.literal_eval(_admin_env))
except Exception:
    ADMIN_ID = []
ADMIN_ID = [721585818,708244245,8182853266]  # Telegram ID администратора

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === СОЗДАЁМ БАЗУ ===
async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            student_name TEXT,
            employee_name TEXT,
            next_lesson TEXT,
            hours INTEGER,
            rate REAL,
            total REAL,
            created_at TEXT
        )
        """)
        await db.commit()


# === СОСТОЯНИЯ ДЛЯ ФОРМЫ ===
class Form(StatesGroup):
    chat_id = State()
    student_name = State()
    employee_name = State()
    next_lesson = State()
    hours = State()
    rate = State()




# Клавиатура для сотрудника
employee_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Заполнить форму")]
    ],
    resize_keyboard=True
)

# Клавиатура для администратора
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Отчёт за всё время")],
        [KeyboardButton(text="🧹 Очистить таблицу")],
        [KeyboardButton(text="📝 Заполнить форму")]
    ],
    resize_keyboard=True
)

# Кнопка "📊 Отчёт за всё время"
@dp.message(F.text == "📊 Отчёт за всё время")
async def report_all_button(message: Message):
    await report_all(message)






# === НАЧАЛО ===
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_ID:
        await message.answer(
            "Здравствуйте, администратор!\n\n"
            "Вы можете получить отчёт или очистить таблицу:",
            reply_markup=admin_kb
        )
    else:
        await message.answer(
            "Здравствуйте! Выберите действие:",
            reply_markup=employee_kb
        )

# === НАЧАЛО ЗАПОЛНЕНИЯ ФОРМЫ ===
@dp.message(F.text == "📝 Заполнить форму")
async def form_start(message: Message, state: FSMContext):
    await message.answer("Введите номер чата:")
    await state.set_state(Form.chat_id)


@dp.message(Form.chat_id)
async def form_chat_id(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.text)
    await message.answer("Введите имя ученика:")
    await state.set_state(Form.student_name)


@dp.message(Form.student_name)
async def form_student_name(message: Message, state: FSMContext):
    await state.update_data(student_name=message.text)
    await message.answer("Введите ваше фио:")
    await state.set_state(Form.employee_name)


@dp.message(Form.employee_name)
async def form_employee_name(message: Message, state: FSMContext):
    await state.update_data(employee_name=message.text)
    await message.answer("Введите дату следующего занятия (например, 10.10.2025):")
    await state.set_state(Form.next_lesson)


@dp.message(Form.next_lesson)
async def form_next_lesson(message: Message, state: FSMContext):
    await state.update_data(next_lesson=message.text)
    await message.answer("Введите количество часов:")
    await state.set_state(Form.hours)


@dp.message(Form.hours)
async def form_hours(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число!")
        return
    await state.update_data(hours=int(message.text))
    await message.answer("Введите оплату за 1 час:")
    await state.set_state(Form.rate)


@dp.message(Form.rate)
async def form_rate(message: Message, state: FSMContext):
    try:
        rate = float(message.text)
    except ValueError:
        await message.answer("Введите число!")
        return

    data = await state.get_data()
    total = data["hours"] * rate

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect("database.db") as db:
        await db.execute("""
            INSERT INTO records (chat_id, student_name, employee_name, next_lesson, hours, rate, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["chat_id"], data["student_name"], data["employee_name"],
            data["next_lesson"], data["hours"], rate, total, created_at
        ))
        await db.commit()
    # Отправляем подтверждение сотруднику
    await message.answer(f"✅ Запись сохранена!\n\n"
                         f"Чат: {data['chat_id']}\n"
                         f"Ученик: {data['student_name']}\n"
                         f"Сотрудник: {data['employee_name']}\n"
                         f"Дата занятия: {data['next_lesson']}\n"
                         f"Сумма оплаты: {total} ₽")

    # Отправляем копию админу
    text = (
        f"📩 Новая запись от сотрудника:\n"
        f"Чат: {data['chat_id']}\n"
        f"Ученик: {data['student_name']}\n"
        f"Сотрудник: {data['employee_name']}\n"
        f"Дата занятия: {data['next_lesson']}\n"
        f"Часы: {data['hours']}\n"
        f"сумму оплаты от ученика: {rate}\n"
        f"💰 Итого: {total} ₽"
    )
    try:
        for i in ADMIN_ID:
            await bot.send_message(i, text)
    except:
        pass

    await state.clear()


# === ОТЧЁТ ЗА ВСЁ ВРЕМЯ ===
@dp.message(Command("report_all"))
async def report_all(message: Message):
    if message.from_user.id not in ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    async with aiosqlite.connect("database.db") as db:
        async with db.execute("""
            SELECT employee_name, SUM(total),SUM(hours)
            FROM records
            GROUP BY employee_name
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Нет данных.")
        return

    text = "📊 Отчёт за всё время:\n\n"
    for name, total, hours in rows:
        text += f"👨‍🏫 {name}: {total:.2f}₽. 💳Заработал {hours} * 700 = {hours*700}₽\n"

    await message.answer(text)

@dp.message(F.text == "🧹 Очистить таблицу")
async def clear_table_confirm(message: Message):
    if message.from_user.id not in ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    # Кнопки подтверждения
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear")
        ]
    ])

    await message.answer(
        "⚠️ Вы уверены, что хотите удалить все записи из базы данных?",
        reply_markup=kb
    )

# Если админ подтвердил очистку
@dp.callback_query(F.data == "confirm_clear")
async def confirm_clear(callback: CallbackQuery):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("DELETE FROM records")
        await db.commit()

    await callback.message.edit_text("🧹 Таблица успешно очищена!")
    await callback.answer("Данные удалены.")


# Если админ отменил очистку
@dp.callback_query(F.data == "cancel_clear")
async def cancel_clear(callback: CallbackQuery):
    await callback.message.edit_text("❌ Очистка таблицы отменена.")
    await callback.answer("Отмена.")



# === ЗАПУСК ===
async def main():
    await init_db()

    
    # Рассылка админам при старте
    text = "СЛАВА ЯЙЦАМ! МИШАНЯ ОПЛАТИЛ СЕРВЕР"  # [attached_file:1]
    for admin_id in ADMIN_ID:
        try:
            await bot.send_message(admin_id, text)  # [attached_file:1]
        except Exception:
            pass  # Игнорируем ошибки доставки, чтобы не сорвать запуск [attached_file:1]

    await dp.start_polling(bot)  # Запуск поллинга [attached_file:1]

    
    

if __name__ == "__main__":
    asyncio.run(main())
    
