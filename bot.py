import os
import sqlite3
import telebot
import time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from threading import Thread
import io
import re
from pypdf import PdfReader
import uuid

# Настройки
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAErKWlTfpV5EQPPSPCeZbAPopcfsJd5d-o')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 1318983685))
DB_NAME = 'c-opt-store.db'

# Папка для загрузки картинок
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
flask_app = Flask(__name__, static_folder='static', static_url_path='/static')
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

# --- ЛОГИКА TELEGRAM БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    print(f"Получена команда /start от пользователя {message.from_user.id}")
    markup = telebot.types.InlineKeyboardMarkup()
    web_app = telebot.types.WebAppInfo(url="https://coptest.onrender.com")
    markup.add(telebot.types.InlineKeyboardButton("🛍 Открыть магазин C-opt EST", web_app=web_app))
    
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в оптовый магазин C-opt EST!\n\nНажмите кнопку ниже, чтобы открыть витрину товаров.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('order_'))
def handle_order_action(call):
    # 1. САМОЕ ПЕРВОЕ ДЕЙСТВИЕ — мгновенно гасим кнопку, чтобы она не крутилась
    try:
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"Ошибка ответа Telegram: {e}")

    # 2. Проверка прав (всплывающее окно убрано, чтобы не вызывать зависание)
    if call.from_user.id != ADMIN_ID:
        bot.send_message(
            call.message.chat.id, 
            f"❌ Доступ запрещен.\nВаш ID: `{call.from_user.id}`\nID администратора в коде: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
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

    # 3. Защита от сброшенной базы данных
    if not order:
        cur.close()
        conn.close()
        bot.send_message(
            call.message.chat.id, 
            f"⚠️ Заказ #{order_id} не найден в базе данных (вероятно, база была очищена при перезапуске сервера)."
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
            print(f"Ошибка при списании товаров со склада: {e}")

        cur.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            bot.edit_message_text(
                f"✅ ЗАКАЗ #{order_id} ПОДТВЕРЖДЕН\n\n"
                f"👤 Покупатель: @{username} (ID: {user_id})\n\n"
                f"📦 Состав заказа:\n{items_desc}\n"
                f"💰 Итого: {total} руб.\n\n"
                f"(Товары списаны со склада)",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception as e:
            print(f"Ошибка редактирования сообщения (confirm): {e}")
        
        try:
            bot.send_message(user_id, f"✅ Ваш заказ **#{order_id}** подтвержден администратором!", parse_mode="Markdown")
        except Exception:
            pass

    elif action == 'cancel':
        if current_status == 'cancelled':
            cur.close()
            conn.close()
            return

        if current_status == 'confirmed':
            try:
                lines = items_desc.strip().split('\n')
                for line in lines:
                    match = re.search(r'•\s+(.*?)\s+x\s+(\d+)\s+шт\.', line)
                    if match:
                        prod_name = match.group(1).strip()
                        prod_count = int(match.group(2))
                        cur.execute("UPDATE products SET quantity = quantity + ? WHERE name = ?", (prod_count, prod_name))
            except Exception as e:
                print(f"Ошибка при возврате товаров на склад: {e}")

        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            bot.edit_message_text(
                f"❌ ЗАКАЗ #{order_id} ОТМЕНЕН\n\n"
                f"👤 Покупатель: @{username} (ID: {user_id})\n\n"
                f"📦 Состав заказа:\n{items_desc}\n"
                f"💰 Итого: {total} руб.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception as e:
            print(f"Ошибка редактирования сообщения (cancel): {e}")
        
        try:
            bot.send_message(
                user_id, 
                f"❌ К сожалению, ваш заказ **#{order_id}** был отменен администратором.\n\n"
                f"📦 **Состав:**\n{items_desc}\n"
                f"💰 **Сумма:** {total} руб.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление клиенту: {e}")

# --- ВЕБ-СЕРВЕР FLASK И API ---

@flask_app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'index.html')
    return send_file(file_path)

@flask_app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, quantity, image_url FROM products ORDER BY id ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    products = [{"id": r[0], "name": r[1], "price": r[2], "quantity": r[3], "image_url": r[4]} for r in rows]
    return jsonify(products)

@flask_app.route('/api/products', methods=['POST'])
def add_product():
    data = request.json
    if data.get('user_id') != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    name = data.get('name')
    price = data.get('price')
    quantity = data.get('quantity', 0)
    image_url = data.get('image_url', '')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, price, quantity, image_url) VALUES (?, ?, ?, ?)", (name, price, quantity, image_url))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

@flask_app.route('/api/upload-image', methods=['POST'])
def upload_image():
    user_id = request.form.get('user_id', type=int)
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    if 'image' not in request.files:
        return jsonify({"error": "Файл не найден"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400

    try:
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        image_url = f"/static/uploads/{filename}"
        return jsonify({"status": "success", "image_url": image_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route('/api/order', methods=['POST'])
def create_order():
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username', 'Аноним')
    items = data.get('items', [])
    total = data.get('total', 0)

    if not items:
        return jsonify({"error": "Корзина пуста"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    items_description = ""
    for item in items:
        count = item.get('count', 1)
        name = item.get('name')
        items_description += f"• {name} x {count} шт.\n"

    cur.execute(
        "INSERT INTO orders (user_id, username, items, total, status) VALUES (?, ?, ?, ?, 'new')",
        (user_id, username, items_description, total)
    )
    order_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()

    # 1. Уведомление для администратора
    admin_message = (
        f"🚨 Новый заказ #{order_id}!\n\n"
        f"👤 Покупатель: @{username} (ID: {user_id})\n\n"
        f"📦 Состав заказа:\n{items_description}\n"
        f"💰 Итого: {total} руб."
    )
    
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"order_confirm_{order_id}"),
        telebot.types.InlineKeyboardButton("❌ Отменить", callback_data=f"order_cancel_{order_id}")
    )

    try:
        bot.send_message(ADMIN_ID, admin_message, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка отправки уведомления админу: {e}")

    # 2. Уведомление для клиента
    client_message = (
        f"🎉 **Ваш заказ успешно оформлен!**\n\n"
        f"🔢 **Номер заказа:** #{order_id}\n\n"
        f"📦 **Состав заказа:**\n{items_description}\n"
        f"💰 **Итого к оплате:** {total} руб.\n\n"
        f"⏳ Ожидайте подтверждения от администратора."
    )

    try:
        bot.send_message(user_id, client_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки уведомления клиенту: {e}")

    return jsonify({"status": "success", "message": "Заказ успешно оформлен"})

@flask_app.route('/api/user-stats', methods=['GET'])
def get_user_stats():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({"orders_count": 0, "total_spent": 0})

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(total) FROM orders WHERE user_id = ? AND status = 'confirmed'", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    orders_count = row[0] if row[0] else 0
    total_spent = row[1] if row[1] else 0

    return jsonify({
        "orders_count": orders_count,
        "total_spent": total_spent
    })

@flask_app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get('user_id', type=int)
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*), SUM(total) FROM orders WHERE status = 'confirmed'")
    row = cur.fetchone()
    total_orders = row[0] if row[0] else 0
    total_revenue = row[1] if row[1] else 0
    
    cur.close()
    conn.close()

    return jsonify({
        "total_orders": total_orders,
        "total_revenue": total_revenue
    })

@flask_app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    user_id = request.form.get('user_id', type=int)
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден"}), 400

    file = request.files['file']
    markup_rubles = float(request.form.get('markup_rubles', 0))

    if file.filename == "":
        return jsonify({"error": "Файл не выбран"}), 400

    try:
        pdf_reader = PdfReader(io.BytesIO(file.read()))
        extracted_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

        conn = get_db_connection()
        cur = conn.cursor()

        added_count = 0
        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]
            match_end = re.search(r'([\d\s,\.]+)\s*(\d+)\s*шт', line)
            
            if match_end:
                price_str = match_end.group(1).replace(' ', '').replace(',', '.')
                qty_str = match_end.group(2)
                name = line[:match_end.start()].strip()
                
                while name and (name[0].isdigit() or name[0] in '.-—) '):
                    name = name[1:]
                name = name.strip()
                
                try:
                    final_price = int(float(price_str) + markup_rubles)
                    quantity = int(qty_str)
                    
                    if name:
                        cur.execute(
                            "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                            (name, final_price, quantity)
                        )
                        added_count += 1
                except ValueError:
                    pass
                i += 1
            else:
                name_parts = []
                price_data = None
                
                while i < len(lines):
                    subline = lines[i]
                    price_match = re.search(r'([\d\s,\.]+)\s*(\d+)\s*шт', subline)
                    if price_match:
                        price_str = price_match.group(1).replace(' ', '').replace(',', '.')
                        qty_str = price_match.group(2)
                        leftover = subline[:price_match.start()].strip()
                        if leftover:
                            name_parts.append(leftover)
                        
                        final_price = int(float(price_str) + markup_rubles)
                        price_data = (final_price, int(qty_str))
                        i += 1
                        break
                    else:
                        name_parts.append(subline)
                        i += 1

                if price_data and name_parts:
                    full_name = " ".join(name_parts)
                    while full_name and (full_name[0].isdigit() or full_name[0] in '.-—) '):
                        full_name = full_name[1:]
                    full_name = full_name.strip()
                    
                    price, quantity = price_data
                    if full_name:
                        cur.execute(
                            "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                            (full_name, price, quantity)
                        )
                        added_count += 1
                i += 1

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "success", "added": added_count})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route('/api/update-product', methods=['POST'])
def update_product():
    data = request.json
    user_id = data.get('user_id')
    if user_id != ADMIN_ID:
        return jsonify({"error": "Доступ запрещен"}), 403

    product_id = data.get('id')
    name = data.get('name')
    price = data.get('price')
    quantity = data.get('quantity', 0)
    image_url = data.get('image_url', '')

    if not product_id:
        return jsonify({"error": "ID товара не указан"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE products SET name = ?, price = ?, quantity = ?, image_url = ? WHERE id = ?",
            (name, price, quantity, image_url, product_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route('/api/delete-product', methods=['POST'])
def delete_product():
    data = request.json
    user_id = data.get('user_id')
    product_id = data.get('id')

    if user_id != ADMIN_ID:
        return jsonify({'error': 'Доступ запрещен'}), 403

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    try:
        bot.remove_webhook()
        print("Вебхук успешно сброшен перед запуском polling.")
    except Exception as e:
        print(f"Ошибка сброса вебхука: {e}")

    print("Бот начал опрос Telegram...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Ошибка polling: {e}")
            time.sleep(5)
