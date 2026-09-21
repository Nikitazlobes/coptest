import os
import sqlite3
import telebot
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from threading import Thread

# Токен вашего бота и настройки
TOKEN = 'ВАШ_ТОКЕН_БОТА'  # Замените на токен вашего бота от BotFather
ADMIN_ID = 123456789     # Замените на ваш Telegram ID
DB_NAME = 'c-opt-store.db'

bot = telebot.TeleBot(TOKEN)
flask_app = Flask(__name__)
CORS(flask_app)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT,
            price INTEGER
        )
    """)
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
    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", ("Картридж", 500))
        cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", ("Жидкость", 400))
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- ЛОГИКА TELEGRAM БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    # Замените ссылку ниже на вашу актуальную с Render
    web_app = telebot.types.WebAppInfo(url="https://coptest.onrender.com")
    markup.add(telebot.types.InlineKeyboardButton("🛍 Открыть магазин C-opt EST", web_app=web_app))
    
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в оптовый магазин C-opt EST!\n\nНажмите кнопку ниже, чтобы открыть витрину товаров.",
        reply_markup=markup
    )

# --- ВЕБ-СЕРВЕР FLASK ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    return send_file(file_path)

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
    cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", (data.get('name'), data.get('price')))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке, чтобы он не блокировал бота
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запуск бота в режиме бесконечного опроса
    bot.infinity_polling()
