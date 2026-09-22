import os
import sqlite3
import telebot
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import re
import json
import threading

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAErKWlTfpV5EQPPSPCeZbAPopcfsJd5d-o')
ADMIN_ID = 1318983685
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://coptest.onrender.com')
DB_NAME = 'c-opt-store.db'

# Создаем бота (без вебхуков)
bot = telebot.TeleBot(TOKEN, parse_mode=None, threaded=False)

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
    
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'new'")
    except sqlite3.OperationalError:
        pass

    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Картридж", 500, 10))
        cur.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Жидкость", 400, 15))
    
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- МАРШРУТЫ FLASK ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    if os.path.exists(file_path):
        return send_file(file_path)
    return "Файл index.html не найден", 404

# --- ТЕЛЕГРАМ БОТ (ЛОГИКА ПОЛЛИНГА) ---

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

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if call.from_user.id != ADMIN_ID:
        return

    data = call.data
    if not data.startswith('order_'):
        return

    parts = data.split('_')
    if len(parts) < 3:
        return

    action = parts[1]
    try:
        order_id = int(parts[2])
    except ValueError:
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()

    if not order:
        cur.close()
        conn.close()
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
            print(f"Ошибка редактирования: {e}")

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
            print(f"Ошибка редактирования: {e}")

    cur.close()
    conn.close()

# --- API МАГАЗИНА ---

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
    try:
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()
            
        user_id = data.get('user_id')
        username = data.get('username', 'Неизвестен')
        cart = data.get('cart', [])
        
        if isinstance(cart, str):
            try:
                cart = json.loads(cart)
            except Exception:
                cart = []

        if not user_id:
            user_id = ADMIN_ID

        if not cart:
            return jsonify({'success': False, 'error': 'Корзина пуста'}), 400
            
        total = 0
        items_text = ""
        
        for item in cart:
            price = int(item.get('price', 0))
            qty = int(item.get('cartQuantity', item.get('quantity', 1)))
            name = item.get('name', 'Товар')
            
            total += price * qty
            items_text += f"• {name} x {qty} шт. (по {price} руб.)\n"
            
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
            print(f"Ошибка отправки уведомления админу: {e}", flush=True)
            
        return jsonify({'success': True, 'order_id': order_id})

    except Exception as e:
        print(f"Критическая ошибка в /api/order: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# Функция запуска бота в фоновом потоке
def run_bot():
    try:
        # Очищаем старый вебхук на всякий случай, чтобы polling не конфликтовал
        bot.remove_webhook()
        print("Запуск бота в режиме Polling...", flush=True)
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"Ошибка в потоке бота: {e}", flush=True)

if __name__ == '__main__':
    # Сбрасываем вебхук программно перед стартом
    try:
        bot.remove_webhook()
    except Exception:
        pass

    # Запускаем бота в отдельном потоке, чтобы он не блокировал Flask
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Запускаем веб-сервер Flask для Mini App
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)
