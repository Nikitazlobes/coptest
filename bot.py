import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, MenuButtonWebApp

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
WEBAPP_URL = "https://your-domain.com/index.html"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Открыть Магазин / Админку", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в **TGShop Manager**.\n"
        "Нажмите на кнопку ниже, чтобы открыть каталог или добавить новые товары.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def main():
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=WEBAPP_URL))
    )
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
