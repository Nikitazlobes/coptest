import os
import sqlite3
import telebot
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import io
import re
from pypdf import PdfReader
import uuid

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('BOT_TOKEN', '8855611435:AAErKWlTfpV5EQPPSPCeZbAPopcfsJd5d-o')
ADMIN_ID = 1318983685
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://coptest.onrender.com')
DB_NAME = 'c-opt-store.db'

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ВАЖНО: threaded=False отключает конфликтующие потоки для Webhook
bot = telebot.TeleBot(TOKEN, parse_mode=None, threaded=False)
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

# --- ВЕБХУК ДЛЯ TELEGRAM ---

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    # Безопасное получение обновлений без жесткой привязки к content-type
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Ошибка webhook: {e}", flush=True)
    
    # Всегда возвращаем 200 OK, чтобы Telegram не дублировал нажатия
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
    # 1. МГНОВЕННО снимаем часики загрузки с кнопки
    try:
        bot.answer_callback_query(call.id, text="Обработка...")
    except Exception as e:
        print(f"Answer callback error: {e}", flush=True)

    # 2. Проверка прав администратора
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, text="❌ Отказано в доступе!", show_alert=True)
        bot.send_message(
            call.message.chat.id,
            f"❌ Доступ запрещен. Ваш ID не является админским."
        )
        return

    try:
        parts = call.data.split('_')
        if len(parts) < 3:
            return
        action = parts[1]
        order_id = int(parts[2])
    except Exception as e:
        print(f"Parsing error: {e}", flush=True)
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()

    # 3. ЕСЛИ ЗАКАЗ НЕ НАЙДЕН (БД была стерта после деплоя)
    if not order:
        cur.close()
        conn.close()
        bot.answer_callback_query(call.id, text="⚠️ Ошибка: Заказ не найден!", show_alert=True)
        bot.send_message(
            call.message.chat.id, 
            f"⚠️ Заказ #{order_id} не найден в базе. Возможно, он был удален при обновлении сервера (Render)."
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
            print(f"Stock error: {e}", flush=True)

        cur.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            bot.edit_message_text(
                f"✅ ЗАКАЗ #{order_id} ПОДТВЕРЖДЕН\n\Проблема с неработающими кнопками «Подтвердить» и «Отменить» (например, при подтверждении добавления товара или оформлении заказа в вашем магазине) чаще всего связана с тем, как вебхук маршрутизирует разные типы входящих данных (Updates) от Telegram. Команда `/start` приходит как объект `message`, а кнопки могут отправлять данные совершенно иначе.

Вот основные причины и пути решения в зависимости от типа используемых кнопок:

**1. Если это Inline-кнопки (прикреплены под самим сообщением)**
Такие кнопки отправляют не обычное текстовое сообщение, а объект `callback_query`.
*   **Парсинг JSON вебхука:** Убедитесь, что скрипт, принимающий вебхук, проверяет наличие ключа `callback_query` во входящем JSON. Если ваш код настроен реагировать только на ключ `message`, нажатия на инлайн-кнопки будут игнорироваться.
*   **Обработчик (Handler):** В коде должен быть зарегистрирован отдельный хэндлер, который ловит конкретную `callback_data` (например, `callback_data="confirm"` и `callback_data="cancel"`).
*   **Ответ на Callback:** Телеграм требует обязательно вызывать метод `answerCallbackQuery` после обработки нажатия. Если этого не сделать, на кнопке будет долго висеть иконка загрузки (часики), а затем она может "отвалиться".

**2. Если это Reply-кнопки (находятся внизу, вместо клавиатуры телефона)**
При нажатии они отправляют обычный текст от имени пользователя («Подтвердить» или «Отменить»).
*   **Текстовый фильтр:** Ваш бот должен перехватывать объект `message` и проверять поле `message.text`.
*   **Проверка регистра:** Убедитесь, что ожидаемый текст в коде в точности совпадает с текстом на кнопке (включая заглавные буквы и отсутствие случайных пробелов).

**План отладки:**
Временно добавьте логирование (сохранение в файл или вывод в консоль сервера) абсолютно всех входящих JSON-запросов, которые приходят на URL вашего вебхука. Нажмите на неработающую кнопку и посмотрите:
1. Приходит ли вообще запрос от Telegram на ваш сервер в этот момент.
2. В каком объекте лежат данные (`message` или `callback_query`).

Какую библиотеку вы используете для разработки (например, `aiogram`, `pyTelegramBotAPI`, `Telegraf` для Node.js)?
