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
TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_ID = 1318983685
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://coptest.onrender.com')
DATABASE_URL = os.environ.get('DATABASE_URL')
DB_NAME = 'c-opt-store.db'

# Папка для загрузки изображений
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

bot = telebot.TeleBot(TOKEN, parse_mode=None)

flask_app = Flask(__name__, static_folder='.', static_url_path='')
CORS(flask_app)

def get_db_connection():
    if DATABASE_URL:
        url = DATABASE_URL.replace("postgres://", "postgresql://")
        return psycopg2.connect(url, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

def db_execute(cur, sql, params=()):
    if DATABASE_URL:
        sql = sql.replace('?', '%s')
    cur.execute(sql, params)

def get_setting(cur, key, default=None):
    db_execute(cur, "SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    if row:
        return row['value'] if isinstance(row, dict) else row[0]
    return default

def set_setting(cur, key, value):
    db_execute(cur, "DELETE FROM settings WHERE key = ?", (key,))
    db_execute(cur, "INSERT INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def detect_category(product_name: str) -> str:
    """ Автоматическое определение категории по ключевым словам """
    name = product_name.lower()
    
    if any(w in name for w in ['жидкость', 'жижа', 'жижка', 'liq', 'liquid', 'salt', 'солевая', 'щелочь', 'хард', 'hard']):
        return 'Жидкости'
    
    if any(w in name for w in ['картридж', 'катридж', 'испаритель', 'испар', 'coil', 'испарик', 'бак', 'карт', 'сетка']):
        return 'Картриджи и Испарители'
        
    if any(w in name for w in ['pod', 'под', 'набор', 'kit', 'устройство', 'пасито', 'pasito', 'charon', 'чарон', 'xros', 'aegis', 'knight', 'hero']):
        return 'Устройства'
        
    if any(w in name for w in ['одноразка', 'одноразовая', 'puff', 'тяг', 'bar']):
        return 'Одноразки'

    return 'Разное'

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if DATABASE_URL:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT,
                price REAL,
                quantity INTEGER DEFAULT 0,
                image_url TEXT DEFAULT '',
                category TEXT DEFAULT 'Разное'
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        conn.commit()
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
                quantity INTEGER DEFAULT 0,
                image_url TEXT DEFAULT '',
                category TEXT DEFAULT 'Разное'
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    
    cur.close()
    conn.close()

init_db()

# --- ВЕБХУК ---
try:
    bot.remove_webhook()
    webhook_url = f"{RENDER_URL}/webhook"
    bot.set_webhook(url=webhook_url)
    print(f"Вебхук установлен: {webhook_url}", flush=True)
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
    user_id = message.from_user.id
    username = message.from_user.username or "Неизвестен"

    conn = get_db_connection()
    cur = conn.cursor()
    if DATABASE_URL:
        db_execute(cur, "INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username", (user_id, username))
    else:
        db_execute(cur, "INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    cur.close()
    conn.close()

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
        return

    current_status = order['status'] if isinstance(order, dict) else order[5]
    username = order['username'] if isinstance(order, dict) else order[2]
    user_id = order['user_id'] if isinstance(order, dict) else order[1]
    items_desc = order['items'] if isinstance(order, dict) else order[3]
    total = order['total'] if isinstance(order, dict) else order[4]

    if action == 'confirm':
        if current_status == 'confirmed':
            cur.close()
            conn.close()
            return

        db_execute(cur, "UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
        conn.commit()

        try:
            bot.edit_message_text(
                f"✅ ЗАКАЗ #{order_id} ПОДТВЕРЖДЕН\n\nПользователь: @{username}\nID: {user_id}\n\nТовары:\n{items_desc}\nИтого: {total} руб.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
            bot.send_message(user_id, f"🎉 Ваш заказ #{order_id} подтвержден администратором и добавлен в вашу историю!")
        except Exception as e:
            print(f"Ошибка редактирования: {e}")

    elif action == 'cancel':
        if current_status == 'cancelled':
            cur.close()
            conn.close()
            return

        try:
            lines = str(items_desc).strip().split('\n')
            for line in lines:
                match = re.search(r'•\s+(.+?)\s+x\s+(\d+)\s+шт', line)
                if match:
                    prod_name = match.group(1).strip()
                    prod_count = int(match.group(2))
                    db_execute(cur, "UPDATE products SET quantity = quantity + ? WHERE name = ?", (prod_count, prod_name))
        except Exception as e:
            print(f"Ошибка возврата товара: {e}", flush=True)

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

# --- API ЭНДПОИНТЫ ---

@flask_app.route('/api/user-orders', methods=['GET'])
@flask_app.route('/api/orders', methods=['GET'])
def get_user_orders():
    try:
        user_id_raw = request.args.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()

        if user_id_raw and str(user_id_raw).isdigit():
            db_execute(cur, "SELECT * FROM orders WHERE user_id = ? AND status = 'confirmed' ORDER BY id DESC", (int(user_id_raw),))
        else:
            db_execute(cur, "SELECT * FROM orders ORDER BY id DESC")

        rows = cur.fetchall()
        orders = []
        for r in rows:
            r_dict = dict(r) if isinstance(r, dict) else {
                'id': r[0], 'user_id': r[1], 'username': r[2],
                'items': r[3], 'total': r[4], 'status': r[5],
                'created_at': str(r[6]) if len(r) > 6 else ''
            }
            
            raw_items = str(r_dict.get('items', ''))
            
            parsed_items = []
            for line in raw_items.strip().split('\n'):
                match = re.search(r'•\s+(.+?)\s+x\s+(\d+)\s+шт', line)
                if match:
                    parsed_items.append({
                        'name': match.group(1).strip(),
                        'cartQuantity': int(match.group(2)),
                        'quantity': int(match.group(2))
                    })
            
            orders.append({
                'id': r_dict.get('id'),
                'user_id': r_dict.get('user_id'),
                'username': r_dict.get('username'),
                'items': raw_items,
                'items_list': parsed_items,
                'total': float(r_dict.get('total', 0)),
                'status': r_dict.get('status', 'new'),
                'created_at': str(r_dict.get('created_at', ''))
            })

        cur.close()
        conn.close()
        return jsonify(orders)
    except Exception as e:
        print(f"Ошибка получения заказов: {e}", flush=True)
        return jsonify([])

@flask_app.route('/api/admin-stats', methods=['GET'])
def get_admin_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Считаем сумму по всем подтвержденным заказам из базы
        db_execute(cur, "SELECT items, total FROM orders WHERE status = 'confirmed'")
        rows = cur.fetchall()

        orders_from_db = len(rows)
        revenue_from_db = 0
        items_from_db = 0

        for row in rows:
            r_total = row['total'] if isinstance(row, dict) else row[1]
            r_items = row['items'] if isinstance(row, dict) else row[0]
            
            revenue_from_db += float(r_total or 0)
            if r_items:
                matches = re.findall(r'x\s+(\d+)\s+шт', str(r_items))
                for m in matches:
                    items_from_db += int(m)

        # Берем ручную базу (если она задана)
        m_rev = get_setting(cur, 'manual_revenue', None)
        m_items = get_setting(cur, 'manual_items_sold', None)
        m_orders = get_setting(cur, 'manual_orders_count', None)

        base_revenue = int(float(m_rev)) if m_rev is not None else 0
        base_items = int(float(m_items)) if m_items is not None else 0
        base_orders = int(float(m_orders)) if m_orders is not None else 0

        cur.close()
        conn.close()

        # Итоговая статистика = Ручная база + Заказы из базы
        total_revenue = base_revenue + int(revenue_from_db)
        items_sold = base_items + items_from_db
        total_orders = base_orders + orders_from_db

        return jsonify({
            'total_revenue': total_revenue,
            'items_sold': items_sold,
            'total_orders': total_orders
        })
    except Exception as e:
        print(f"Ошибка получения статистики: {e}", flush=True)
        return jsonify({'total_revenue': 0, 'items_sold': 0, 'total_orders': 0}), 500

@flask_app.route('/api/admin-stats/clear', methods=['POST'])
def clear_admin_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        db_execute(cur, "DELETE FROM settings WHERE key IN ('manual_revenue', 'manual_items_sold', 'manual_orders_count')")
        db_execute(cur, "UPDATE orders SET status = 'archived' WHERE status = 'confirmed'")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/admin-stats/edit', methods=['POST'])
def edit_admin_stats():
    """ Установка базовых (ручных) значений статистики """
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        
        new_revenue = int(float(data.get('total_revenue', 0)))
        new_items = int(float(data.get('items_sold', 0)))
        new_orders = int(float(data.get('total_orders', 0)))

        conn = get_db_connection()
        cur = conn.cursor()

        # Сохраняем то, что ввел администратор, как новую точку отсчета
        set_setting(cur, 'manual_revenue', str(new_revenue))
        set_setting(cur, 'manual_items_sold', str(new_items))
        set_setting(cur, 'manual_orders_count', str(new_orders))

        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'total_revenue': new_revenue, 
            'items_sold': new_items, 
            'total_orders': new_orders
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/clear-all-orders', methods=['POST'])
def clear_all_orders():
    """ Полное удаление всей истории заказов для всех пользователей """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        db_execute(cur, "DELETE FROM orders")
        db_execute(cur, "DELETE FROM settings WHERE key IN ('manual_revenue', 'manual_items_sold', 'manual_orders_count')")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/user-stats', methods=['GET'])
def get_user_stats():
    try:
        user_id = request.args.get('user_id')
        if not user_id or not str(user_id).isdigit():
            return jsonify({'orders_count': 0, 'total_spent': 0})

        conn = get_db_connection()
        cur = conn.cursor()

        db_execute(
            cur,
            "SELECT COUNT(*) as count, COALESCE(SUM(total), 0) as total FROM orders WHERE user_id = ? AND status = 'confirmed'",
            (int(user_id),)
        )
        row = cur.fetchone()
        if isinstance(row, dict):
            orders_count = row.get('count', 0)
            total_spent = float(row.get('total', 0))
        else:
            orders_count = row[0] if row else 0
            total_spent = float(row[1]) if row else 0.0

        cur.close()
        conn.close()
        return jsonify({'orders_count': orders_count, 'total_spent': int(total_spent)})
    except Exception:
        return jsonify({'orders_count': 0, 'total_spent': 0})

@flask_app.route('/api/order', methods=['POST'])
def create_order():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        user_id = data.get('user_id')
        username = data.get('username', 'Неизвестен')
        cart = data.get('cart', [])
        
        if isinstance(cart, str):
            try:
                cart = json.loads(cart)
            except Exception:
                cart = []

        if not user_id or not str(user_id).isdigit():
            user_id = ADMIN_ID
        else:
            user_id = int(user_id)

        if not cart:
            return jsonify({'success': False, 'error': 'Корзина пуста'}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()

        if DATABASE_URL:
            db_execute(cur, "INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username", (user_id, username))
        else:
            db_execute(cur, "INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))

        for item in cart:
            p_id = item.get('id')
            qty = int(item.get('cartQuantity', item.get('quantity', 1)))
            name = item.get('name', 'Товар')

            if p_id:
                db_execute(cur, "SELECT name, quantity FROM products WHERE id = ?", (p_id,))
            else:
                db_execute(cur, "SELECT name, quantity FROM products WHERE name = ?", (name,))
                
            prod = cur.fetchone()
            if prod:
                stock = prod['quantity'] if isinstance(prod, dict) else prod[1]
                p_name = prod['name'] if isinstance(prod, dict) else prod[0]
                if qty > stock:
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': f"Товара '{p_name}' осталось только {stock} шт."}), 400
            else:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': f"Товар '{name}' не найден в базе"}), 400

        total = 0
        items_text = ""
        items_client_text = ""
        
        for item in cart:
            price = int(item.get('price', 0))
            qty = int(item.get('cartQuantity', item.get('quantity', 1)))
            name = item.get('name', 'Товар')
            p_id = item.get('id')
            
            total += price * qty
            items_text += f"• {name} x {qty} шт. (по {price} руб.)\n"
            items_client_text += f"• {name} x {qty} шт.\n"
            
            if p_id:
                if DATABASE_URL:
                    db_execute(cur, "UPDATE products SET quantity = GREATEST(0, quantity - ?) WHERE id = ?", (qty, p_id))
                else:
                    db_execute(cur, "UPDATE products SET quantity = MAX(0, quantity - ?) WHERE id = ?", (qty, p_id))
            else:
                if DATABASE_URL:
                    db_execute(cur, "UPDATE products SET quantity = GREATEST(0, quantity - ?) WHERE name = ?", (qty, name))
                else:
                    db_execute(cur, "UPDATE products SET quantity = MAX(0, quantity - ?) WHERE name = ?", (qty, name))
        
        if DATABASE_URL:
            cur.execute(
                "INSERT INTO orders (user_id, username, items, total, status) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (user_id, username, items_text, total, 'new')
            )
            order_id = cur.fetchone()['id']
        else:
            cur.execute(
                "INSERT INTO orders (user_id, username, items, total, status) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, items_text, total, 'new')
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
            print(f"Ошибка отправки клиенту: {e}")
            
        return jsonify({'success': True, 'order_id': order_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products ORDER BY id DESC")
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

        return jsonify({'image_url': f"/{filepath}"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/products', methods=['POST'])
@flask_app.route('/api/update-product', methods=['POST'])
@flask_app.route('/api/add-product', methods=['POST'])
def update_or_add_product():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        product_id = data.get('id')
        name = data.get('name')
        price = data.get('price')
        quantity = data.get('quantity', 0)
        image_url = data.get('image_url', '')
        category = data.get('category')

        if not name or price is None:
            return jsonify({'success': False, 'error': 'Заполните название и цену'}), 400

        if not category or category == 'Разное':
            category = detect_category(name)

        conn = get_db_connection()
        cur = conn.cursor()

        if product_id:
            db_execute(cur, """
                UPDATE products 
                SET name = ?, price = ?, quantity = ?, image_url = ?, category = ?
                WHERE id = ?
            """, (name, float(price), int(quantity), image_url, category, product_id))
        else:
            db_execute(cur, """
                INSERT INTO products (name, price, quantity, image_url, category)
                VALUES (?, ?, ?, ?, ?)
            """, (name, float(price), int(quantity), image_url, category))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/api/delete-product', methods=['POST'])
def delete_product():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
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
                    category = detect_category(clean_name)
                    
                    db_execute(cur, "SELECT id, quantity FROM products WHERE name = ?", (clean_name,))
                    existing = cur.fetchone()
                    if existing:
                        p_id = existing['id'] if isinstance(existing, dict) else existing[0]
                        p_qty = existing['quantity'] if isinstance(existing, dict) else existing[1]
                        new_qty = (p_qty or 0) + quantity
                        db_execute(cur, "UPDATE products SET price = ?, quantity = ?, category = ? WHERE id = ?", (final_price, new_qty, category, p_id))
                    else:
                        db_execute(cur, "INSERT INTO products (name, price, quantity, category) VALUES (?, ?, ?, ?)", (clean_name, final_price, quantity, category))
                    added_count += 1
            except ValueError:
                pass

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'added': added_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/broadcast', methods=['POST'])
def send_broadcast():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        message_text = data.get('message')
        if not message_text:
            return jsonify({'success': False, 'error': 'Текст сообщения не может быть пустым'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        cur.close()
        conn.close()

        sent_count, fail_count = 0, 0
        markup = telebot.types.InlineKeyboardMarkup()
        web_app = telebot.types.WebAppInfo(url=RENDER_URL)
        markup.add(telebot.types.InlineKeyboardButton("🛍 Открыть каталог", web_app=web_app))

        for u in users:
            uid = u['user_id'] if isinstance(u, dict) else u[0]
            try:
                bot.send_message(uid, message_text, reply_markup=markup)
                sent_count += 1
                time.sleep(0.05)
            except Exception as e:
                print(f"Ошибка отправки пользователю {uid}: {e}", flush=True)
                fail_count += 1

        return jsonify({'success': True, 'sent': sent_count, 'failed': fail_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)
