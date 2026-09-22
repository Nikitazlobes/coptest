import os
import sqlite3
import telebot
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import re

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAErKWlTfpV5EQPPSPCeZbAPopcfsJd5d-o')
ADMIN_ID = 1318983685
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://coptest.onrender.com')
DB_NAME = 'c-opt-store.db'

# Отключаем потоки для стабильной работы вебхуков
bot = telebot.TeleBot(TOKEN, parse_mode=None, threaded=False)

# Указываем корень проекта для статических файлов
flask_app = Flask(__name__, static_folder='.', static_url_path='')
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            quantity INTEGER DEFAULT 0,
            image_url TEXT DEFAULT ''
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT,
            username TEXT,
            items TEXT,
            total INTEGER,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Картридж", 500, 10))
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Жидкость", 400, 15))
    
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- МАРШРУТЫ ДЛЯ МИНИ-ПРИЛОЖЕНИЯ И ВЕБХУКА ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    if os.path.exists(file_path):
        return send_file(file_path)
    return "Файл index.html не найден в корне проекта!", 404

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Ошибка webhook: {e}", flush=True)
    return '', 200

@flask_app.route('/set_webhook', methods=['GET'])
def setup_webhook_route():
    webhook_url = f"{RENDER_URL}/webhook"
    bot.remove_webhook()
    success = bot.set_webhook(url=webhook_url)
    if success:
        return f"✅ Вебхук успешно установлен на: {webhook_url}", 200
    else:
        return "❌ Ошибка установки вебхука", 500

# --- ЛОГИКА БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    web_app = telebot.types.WebAppInfo(url=RENDER_URL)
    markup.add(telebot.types.InlineKeyboardButton("🛍 Открыть магазин C-opt EST", web_app=web_app))
    
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в оптовый магазин C-opt EST!\n\nНажмите кнопку ниже, чтобы открыть витрину товаров.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('order_'))
def handle_order_action(call):
    try:
        bot.answer_callback_query(call.id, text="Обработка...")
    except Exception as e:
        print(f"Ошибка answer_callback_query: {e}")

    if call.from_user.id != ADMIN_ID:
        bot.send_message(call.message.chat.id, "❌ У вас нет прав для этого действия.")
        return

    try:
        parts = call.data.split('_')
        if len(parts) < 3:
            return
        action = parts[1]
        order_id = int(parts[2])
    except Exception as e:
        print(f"Ошибка парсинга callback_data: {e}")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()

    if not order:
        cur.close()
        conn.close()
        bot.send_message(
            call.message.chat.id, 
            f"⚠️ Заказ #{order_id} не найден в базе."
        )
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    current_status = order['status']
    username = order['username']
    user_id = order['user_id']
    items_desc = order['items']
    total = order['total']

    if action == 'confirm':
        if current_status == 'confirmed':
            cur.close()
            conn.close()
            return

        try:
            lines = items_desc.strip().split('\n')
            for line in lines:
                match = re.search(r'•\s+(.*?)\s+x\s+(\d+)\s+шт\.', line)
                if match:
                    prod_name = match.group(1).strip()
                    prod_count = int(match.group(2))
                    cur.execute("UPDATE products SET quantity = quantity - ? WHERE name = ?", (prod_count, prod_name))
        except Exception as e:
            print(f"Ошибка списания остатков: {e}")

        cur.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
        conn.commit()

        try:
            bot.edit_message_text(
                f"✅ ЗАКАЗ #{order_id} ПОДТВЕРЖДЕН\n\nПользователь: @{username}\nID: {user_id}\n\nТовары:\n{items_desc}\nИтого: {total} руб.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
            bot.send_message(user_id, f"🎉 Ваш заказ #{order_id} подтвержден и передан в сборку!")
        except Exception as e:
            print(f"Ошибка редактирования сообщения: {e}")

    elif action == 'cancel':
        if current_status == 'cancelled':
            cur.close()
            conn.close()
            return

        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()

        try:
            bot.edit_message_text(
                f"❌ ЗАКАЗ #{order_id} ОТМЕНЕН\n\nПользователь: @{username}\nID: {user_id}\n\nТовары:\n{items_desc}\nИтого: {total} руб.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
            bot.send_message(user_id, f"😔 Ваш заказ #{order_id} был отменен администратором.")
        except Exception as e:
            print(f"Ошибка редактирования сообщения: {e}")

    cur.close()
    conn.close()

# --- API ДЛЯ МИНИ-ПРИЛОЖЕНИЯ ---

@flask_app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(products)

@flask_app.route('/api/order', methods=['POST'])
def create_order():
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username', 'Неизвестен')
    cart = data.get('cart', [])
    
    if not user_id or not cart:
        return jsonify({'error': 'Некорректные данные'}), 400
        
    total = 0
    items_text = ""
    
    for item in cart:
        total += item['price'] * item['cartQuantity']
        items_text += f"• {item['name']} x {item['cartQuantity']} шт. (по {item['price']} руб.)\n"
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, username, items, total) VALUES (?, ?, ?, ?)",
        (user_id, username, items_text, total)
    )
    order_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    
    markup = telebot.types.InlineKeyboardMarkup()
    btn_confirm = telebot.types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"order_confirm_{order_id}")
    btn_cancel = telebot.types.InlineKeyboardButton("❌ Отменить", callback_data=f"order_cancel_{order_id}")
    markup.add(btn_confirm, btn_cancel)
    
    admin_text = f"🆕 НОВЫЙ ЗАКАЗ #{order_id}\n\nПользователь: @{username} (ID: {user_id})\n\nТовары:\n{items_text}\n💰 Итого: {total} руб."
    
    try:
        bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")
        
    return jsonify({'success': True, 'order_id': order_id})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)
