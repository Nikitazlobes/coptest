import logging
import json
import os
import threading
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# НАСТРОЙКИ
TOKEN = "8855611435:AAEnvtZL04SkDtGcAzcY28qqMK7KbWZspYI"
WEB_APP_URL = "https://c-opt-est-app.onrender.com"
ADMIN_ID = 1318983685

logging.basicConfig(level=logging.INFO)

# --- ПОДКЛЮЧЕНИЕ К POSTGRESQL ---
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        url = urlparse(DATABASE_URL)
        return psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
    else:
        # Локальный запасной вариант (если переменная не подставилась)
        return psycopg2.connect("postgres://c_opt_db_user:gSs9s6k72n6MaJirs0lZOmfq5N0kQMIO@dpg-daoj6dajnfac73969kcg-a/c_opt_db")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Таблица товаров
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )
    """)
    
    # Таблица заказов (для статистики)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            items TEXT,
            total INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Проверяем, есть ли товары, если пусто — добавляем дефолтные
    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price) VALUES (%s, %s)", ("Картридж C-opt 0.6 Ohm", 350))
        cur.execute("INSERT INTO products (name, price) VALUES (%s, %s)", ("Жидкость EST Salt 30ml", 550))
        
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- WEB СЕРВЕР ---
flask_app = Flask(__name__)
CORS(flask_app)

import os

@flask_app.route('/')
def index():
    return send_file(os.path.join(os.path.dirname(__file__), 'index.html'))

@flask_app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price FROM products ORDER BY id ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    products = [{"id": r[0], "name": r[1], "price": r[2]} for r in rows]
    return jsonify(products)

@flask_app.route('/api/products', methods=['POST'])
def add_product():
    data = request.json
    
    if data.get('user_id') != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, price) VALUES (%s, %s)", (data.get("name"), data.get("price")))
    conn.commit()
    cur.close()
    conn.close()
        
    return jsonify({"success": True})

# --- ЭНДПОИНТ ДЛЯ СТАТИСТИКИ ПРОДАЖ В АДМИНКЕ ---
@flask_app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get('user_id', type=int)
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Всего заказов и общая сумма выручки
    cur.execute("SELECT COUNT(*), COALESCE(SUM(total), 0) FROM orders;")
    total_orders, total_revenue = cur.fetchone()
    
    # Последние заказы
    cur.execute("SELECT username, items, total, created_at FROM orders ORDER BY id DESC LIMIT 10;")
    rows = cur.fetchall()
    
    recent_orders = [
        {
            "username": r[0],
            "items": r[1],
            "total": r[2],
            "created_at": str(r[3])
        } for r in rows
    ]
    
    cur.close()
    conn.close()
    
    return jsonify({
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "recent_orders": recent_orders
    })

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
    
    username = user.username if user.username else user.first_name
    items_str = str(data.get('items'))
    total_price = data.get('total')
    
    # Сохраняем заказ в базу данных PostgreSQL
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (user_id, username, items, total) VALUES (%s, %s, %s, %s)",
            (user.id, username, items_str, total_price)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка сохранения заказа в БД: {e}")

    order_text = (
        f"🎉 **Новый заказ!**\n\n"
        f"👤 Покупатель: @{username} (ID: {user.id})\n"
        f"📦 Позиции: {items_str}\n"
        f"💰 Итоговая сумма: {total_price} ₽"
    )
    
    await update.message.reply_text(order_text, parse_mode="Markdown")
    
    if user.id != ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Копия заказа (Вам как Админу):**\n\n{order_text}", parse_mode="Markdown")
        except:
            pass

if __name__ == '__main__':
    # 1. Запускаем Flask-сервер в фоновом потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 2. Запускаем Telegram бота с защитой от конфликтов getUpdates
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    print("🚀 Сервер и Бот успешно запущены с поддержкой PostgreSQL и статистики!")
    
    # drop_pending_updates=True автоматически сбрасывает все старые зависшие запросы в Telegram
    app.run_polling(drop_pending_updates=True)
