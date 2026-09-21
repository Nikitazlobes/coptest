import logging
import json
import os
import threading
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# НАСТРОЙКИ (Вставьте URL после публикации на Render)
TOKEN = "8535899033:AAGyIlaImgOZmWYUOxNBfbHVBLJm_MuC1ek"
WEB_APP_URL = "https://c-opt-est-app.onrender.com" # ЗАМЕНИТЕ НА ВАШ ССЫЛКУ RENDER
ADMIN_ID = 1318983685

logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ (JSON ФАЙЛ) ---
DB_FILE = "products.json"

def init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump([
                {"id": 1, "name": "Картридж C-opt 0.6 Ohm", "price": 350},
                {"id": 2, "name": "Жидкость EST Salt 30ml", "price": 550}
            ], f, ensure_ascii=False)

init_db()

# --- WEB СЕРВЕР (ДЛЯ РАБОТЫ ВИРИНЫ И БАЗЫ ДАННЫХ) ---
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/')
def index():
    # Отдаем файл интерфейса магазина
    return send_file('index.html')

@flask_app.route('/api/products', methods=['GET'])
def get_products():
    # Отдаем товары из базы для всех клиентов
    with open(DB_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)
    return jsonify(products)

@flask_app.route('/api/products', methods=['POST'])
def add_product():
    # Принимаем новый товар из админки
    data = request.json
    
    # Жесткая проверка: только ваш ID может сохранять товары!
    if data.get('user_id') != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403
        
    with open(DB_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)
        
    new_product = {
        "id": data.get("id"),
        "name": data.get("name"),
        "price": data.get("price")
    }
    products.append(new_product)
    
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=4)
        
    return jsonify({"success": True})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# --- TELEGRAM БОТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🛍 Открыть магазин C-opt EST", web_app=WebAppInfo(url=WEB_APP_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Добро пожаловать в оптовый магазин **C-opt EST**!\n\n"
        "Нажмите кнопку ниже, чтобы открыть витрину товаров.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = json.loads(update.message.web_app_data.data)
    user = update.message.from_user
    
    order_text = (
        f"🎉 **Новый заказ!**\n\n"
        f"👤 Покупатель: @{user.username if user.username else user.first_name} (ID: {user.id})\n"
        f"📦 Позиции: {data.get('items')}\n"
        f"💰 Итоговая сумма: {data.get('total')} ₽"
    )
    
    await update.message.reply_text(order_text, parse_mode="Markdown")
    
    # Если заказывает не админ, отправляем вам (админу) уведомление
    if user.id != ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Копия заказа (Вам как Админу):**\n\n{order_text}", parse_mode="Markdown")
        except:
            pass # Если бот не может написать админу

if __name__ == '__main__':
    # 1. Запускаем базу данных (веб-сервер) в фоновом режиме
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Запускаем самого бота
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    print("🚀 Сервер и Бот успешно запущены!")
    app.run_polling()
