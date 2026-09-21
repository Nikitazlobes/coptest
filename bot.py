import os
import sqlite3
import telebot
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from threading import Thread

# Настройки
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAEnv')  # Лучше вынести в переменные окружения Render или вписать сюда
ADMIN_ID = int(os.environ.get('ADMIN_ID', 1318983685))  # Замените на ваш Telegram ID (число)
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
    
    # Таблица товаров с полем quantity (количество)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            quantity INTEGER DEFAULT 0
        )
    """)
    
    # Таблица заказов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT,
            username TEXT,
            items TEXT,
            total INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Добавим дефолтные товары, если таблица пуста
    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Картридж", 500, 10))
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Жидкость", 400, 15))
    
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- ЛОГИКА TELEGRAM БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    web_app = telebot.types.WebAppInfo(url="https://coptest.onrender.com")
    markup.add(telebot.types.InlineKeyboardButton("🛍 Открыть магазин C-opt EST", web_app=web_app))
    
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в оптовый магазин C-opt EST!\n\nНажмите кнопку ниже, чтобы открыть витрину товаров.",
        reply_markup=markup
    )

# --- ВЕБ-СЕРВЕР FLASK И API ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    return send_file(file_path)

# Получить список товаров
@flask_app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, quantity FROM products ORDER BY id ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    products = [{"id": r[0], "name": r[1], "price": r[2], "quantity": r[3]} for r in rows]
    return jsonify(products)

# Добавить товар с указанием количества (для админки)
@flask_app.route('/api/products', methods=['POST'])
def add_product():
    data = request.json
    if data.get('user_id') != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    name = data.get('name')
    price = data.get('price')
    quantity = data.get('quantity', 0)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", (name, price, quantity))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

# Оформление заказа
@flask_app.route('/api/order', methods=['POST'])
def create_order():
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username', 'Аноним')
    items = data.get('items', []) # Список товаров в корзине [{id, name, price, count}]
    total = data.get('total', 0)

    if not items:
        return jsonify({"error": "Корзина пуста"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    items_description = ""
    for item in items:
        prod_id = item.get('id')
        count = item.get('count', 1)
        name = item.get('name')
        items_description += f"• {name} x {count} шт.\n"
        
        # Уменьшаем количество товара на складе
        cur.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?", (count, prod_id))

    # Сохраняем заказ в базу
    cur.execute(
        "INSERT INTO orders (user_id, username, items, total) VALUES (?, ?, ?, ?)",
        (user_id, username, items_description, total)
    )
    conn.commit()
    cur.close()
    conn.close()

    # Отправляем уведомление администратору в личку
    admin_message = (
        f"🚨 **Новый заказ!**\n\n"
        f"👤 Покупатель: @{username} (ID: `{user_id}`)\n\n"
        f"📦 **Состав заказа:**\n{items_description}\n"
        f"💰 **Итого:** {total} руб."
    )
    try:
        bot.send_message(ADMIN_ID, admin_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки уведомления админу: {e}")

    return jsonify({"status": "success", "message": "Заказ успешно оформлен"})

# Статистика продаж для админки
@flask_app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get('user_id', type=int)
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Считаем общее количество заказов и общую выручку
    cur.execute("SELECT COUNT(*), SUM(total) FROM orders")
    row = cur.fetchone()
    total_orders = row[0] if row[0] else 0
    total_revenue = row[1] if row[1] else 0
    
    cur.close()
    conn.close()

    return jsonify({
        "total_orders": total_orders,
        "total_revenue": total_revenue
    })

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запуск Telegram-бота
    bot.infinity_polling()
