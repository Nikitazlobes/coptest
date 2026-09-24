import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import re
import json
import telebot
import PyPDF2
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAEtqssUoPKmbntEUEMMjyuv8S_CQ8ecuTY')
ADMIN_ID = 1318983685
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://coptest.onrender.com')
DATABASE_URL = os.environ.get('DATABASE_URL')
DB_NAME = 'c-opt-store.db'

# Папка для сохранения картинок
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Создаем бота
bot = telebot.TeleBot(TOKEN, parse_mode=None)

flask_app = Flask(__name__, static_folder='.', static_url_path='')
CORS(flask_app)

def get_db_connection():
    if DATABASE_URL:
        # Для Render всегда подключаемся к PostgreSQL
        url = DATABASE_URL.replace("postgres://", "postgresql://")
        return psycopg2.connect(url, cursor_factory=RealDictCursor)
    else:
        # Резервный SQLite для локальной разработки
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

def db_execute(cur, sql, params=()):
    """ Вспомогательная функция для одинаковых запросов в Postgres и SQLite """
    if DATABASE_URL:
        sql = sql.replace('?', '%s')
    cur.execute(sql, params)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if DATABASE_URL:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT,
                price REAL,
                quantity INTEGER DEFAULT 0,
                image_url TEXT DEFAULT ''
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                items TEXT,
                total REAL,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT COUNT(*) FROM products;")
        row = cur.fetchone()
        count = row['count'] if isinstance(row, dict) else row[0]
        if count == 0:
            cur.execute("INSERT INTO products (name, price, quantity) VALUES (%s, %s, %s)", ("Картридж", 500, 10))
            cur.execute("INSERT INTO products (name, price, quantity) VALUES (%s, %s, %s)", ("Жидкость", 400, 15))
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
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
                total REAL,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            cur.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'new'")
        except sqlite3.OperationalError:
            pass

        try:
            cur.execute("ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''")
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

# --- ВЕБХУК ---
try:
    bot.remove_webhook()
    webhook_url = f"{RENDER_URL}/webhook"
    bot.set_webhook(url=webhook_url)
    print(f"Вебхук успешно установлен на: {webhook_url}", flush=True)
except Exception as e:
    print(f"Ошибка установки вебхука: {e}", flush=True)

# --- МАРШРУТЫ FLASK ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    if os.path.exists(file_path):
        return send_file(file_path)
    return "Файл index.html не найден", 404

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

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
    db_execute(cur, "SELECT * FROM orders WHERE id = ?", (order_id,))
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
                    db_execute(cur, "UPDATE products SET quantity = quantity - ? WHERE name = ?", (prod_count, prod_name))
        except Exception as e:
            print(f"Ошибка списания остатков: {e}")

        db_execute(cur, "UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
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

        db_execute(cur, "UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
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

@flask_app.route('/api/upload-image', methods=['POST'])
def upload_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'Файл не найден'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{int(time.time())}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(filepath)

        image_url = f"/{filepath}"
        return jsonify({'image_url': image_url})
    except Exception as e:
        print(f"Ошибка при загрузке фото: {e}", flush=True)
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/update-product', methods=['POST'])
@flask_app.route('/api/add-product', methods=['POST'])
def update_or_add_product():
    try:
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()

        product_id = data.get('id')
        name = data.get('name')
        price = data.get('price')
        quantity = data.get('quantity', 0)
        image_url = data.get('image_url', '')

        if not name or price is None:
            return jsonify({'success': False, 'error': 'Заполните название и цену'}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        if product_id:
            db_execute(cur, """
                UPDATE products 
                SET name = ?, price = ?, quantity = ?, image_url = ?
                WHERE id = ?
            """, (name, float(price), int(quantity), image_url, product_id))
        else:
            db_execute(cur, """
                INSERT INTO products (name, price, quantity, image_url)
                VALUES (?, ?, ?, ?)
            """, (name, float(price), int(quantity), image_url))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при сохранении/добавлении товара: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/delete-product', methods=['POST'])
def delete_product():
    try:
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()

        product_id = data.get('id')
        if not product_id:
            return jsonify({'success': False, 'error': 'ID товара не передан'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        db_execute(cur, "DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при удалении товара: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/upload-pdf', methods=['POST'])
def api_upload_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не найден в запросе'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400

        markup_rubles = int(request.form.get('markup_rubles', 0))
        
        pdf_reader = PyPDF2.PdfReader(file)
        full_text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                full_text += extracted + "\n"
        
        conn = get_db_connection()
        cur = conn.cursor()
        added_count = 0
        
        pattern = r'(\d+[\s\d]*[.,]\d{2})\s*(\d+)\s*шт\s*\d+[\s\d]*[.,]\d{2}\s*(\d+)?'
        matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
        
        last_end = 0
        for match in matches:
            price_str = match.group(1).replace(' ', '').replace(',', '.')
            qty_str = match.group(2)
            
            try:
                base_price = float(price_str)
                if base_price < 10:
                    continue
                    
                final_price = int(base_price + markup_rubles)
                quantity = int(qty_str) if qty_str else 1
                
                raw_name = full_text[last_end:match.start()].strip()
                last_end = match.end()
                
                clean_name = re.sub(r'^\d+[\.\)]?\s*', '', raw_name).strip()
                clean_name = clean_name.replace('\n', ' ').replace('|', '').strip()
                
                if any(w in clean_name.lower() for w in ["mg opt", "заказ №", "заказчик", "наименование", "итого"]):
                    continue

                if len(clean_name) > 2:
                    db_execute(cur, "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", (clean_name, final_price, quantity))
                    added_count += 1
            except ValueError:
                pass

        conn.commit()
        cur.close()
        conn.close()

        print(f"Успешно спарсено и добавлено товаров: {added_count}", flush=True)
        return jsonify({'success': True, 'added': added_count})

    except Exception as e:
        print(f"Ошибка загрузки PDF: {e}", flush=True)
        return jsonify({'error': str(e)}), 500

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
        items_client_text = ""
        
        for item in cart:
            price = int(item.get('price', 0))
            qty = int(item.get('cartQuantity', item.get('quantity', 1)))
            name = item.get('name', 'Товар')
            
            total += price * qty
            items_text += f"• {name} x {qty} шт. (по {price} руб.)\n"
            items_client_text += f"• {name} x {qty} шт.\n"
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        if DATABASE_URL:
            cur.execute(
                "INSERT INTO orders (user_id, username, items, total) VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, username, items_text, total)
            )
            order_id = cur.fetchone()['id']
        else:
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

        client_text = (
            f"🎉 Ваш заказ успешно оформлен!\n\n"
            f"🔢 Номер заказа: #{order_id}\n\n"
            f"📦 Состав заказа:\n{items_client_text}\n"
            f"💰 Итого к оплате: {total} руб.\n\n"
            f"⏳ Ожидайте подтверждения от администратора."
        )
        
        try:
            bot.send_message(user_id, client_text)
        except Exception as e:
            print(f"Ошибка отправки сообщения клиенту: {e}", flush=True)
            
        return jsonify({'success': True, 'order_id': order_id})

    except Exception as e:
        print(f"Критическая ошибка в /api/order: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)
