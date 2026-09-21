import os
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Инициализация Flask приложения
flask_app = Flask(__name__)
CORS(flask_app)

DB_NAME = 'c-opt-store.db'
ADMIN_ID = 123456789  # Замените при необходимости на ваш Telegram ID

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
    
    # Добавляем дефолтные товары, если таблица пуста
    cur.execute("SELECT COUNT(*) FROM products;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", ("Картридж", 500))
        cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", ("Жидкость", 400))
    
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- МАРШРУТЫ ВЕБ-СЕРВЕРА ---

@flask_app.route('/')
def index():
    # Надежный абсолютный путь к index.html в корне проекта
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

