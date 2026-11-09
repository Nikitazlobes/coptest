<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>C-opt EST Store</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #080c14;
            --card-bg: rgba(21, 28, 44, 0.7);
            --card-solid: #111827;
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
            --accent-hover: #4f46e5;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --success-color: #10b981;
            --danger-color: #ef4444;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            -webkit-tap-highlight-color: transparent;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-primary);
            padding-bottom: 90px;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(236, 72, 153, 0.08) 0%, transparent 40%);
            background-attachment: fixed;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes pulseGlow {
            0% { box-shadow: 0 0 15px rgba(99, 102, 241, 0.2); }
            50% { box-shadow: 0 0 25px rgba(168, 85, 247, 0.4); }
            100% { box-shadow: 0 0 15px rgba(99, 102, 241, 0.2); }
        }

        @keyframes addToCartPulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.08); background: #10b981; box-shadow: 0 0 20px rgba(16, 185, 129, 0.5); }
            100% { transform: scale(1); }
        }

        .btn-added-anim {
            animation: addToCartPulse 0.35s ease;
        }

        @keyframes cartBounce {
            0%, 100% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-6px) scale(1.25); color: #10b981; }
        }

        .cart-bounce-anim {
            animation: cartBounce 0.35s ease;
        }

        .tab-content {
            display: none;
            padding: 16px;
            animation: fadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        .tab-content.active {
            display: block;
        }

        .welcome-header {
            padding: 20px 16px 10px 16px;
            animation: fadeIn 0.4s ease;
        }

        .welcome-title {
            font-size: 22px;
            font-weight: 800;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }

        .welcome-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
        }

        .banner-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 18px;
            margin-top: 10px;
            margin-bottom: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .history-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 14px;
            margin-bottom: 10px;
        }

        .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 8px;
            margin-bottom: 8px;
        }

        .history-item-row {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }

        .search-box {
            margin-bottom: 12px;
        }

        .search-input {
            width: 100%;
            background: rgba(17, 24, 39, 0.8);
            border: 1px solid var(--card-border);
            color: white;
            padding: 12px 16px;
            border-radius: 14px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-input:focus {
            border-color: #6366f1;
        }

        .category-scroll {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 12px;
            margin-bottom: 8px;
            scrollbar-width: none;
        }

        .category-scroll::-webkit-scrollbar {
            display: none;
        }

        .cat-chip {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 12px;
            white-space: nowrap;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
        }

        .cat-chip.active {
            background: var(--accent-gradient);
            color: white;
            border-color: transparent;
            font-weight: 600;
        }

        .product-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
            gap: 12px;
            contain: layout style;
        }

        .product-card {
            background: var(--card-solid); 
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            cursor: pointer;
            transform: translateZ(0);
            will-change: transform;
            transition: transform 0.15s ease;
        }

        .product-card:active {
            transform: scale(0.97) translateZ(0);
        }

        .product-img {
            width: 100%;
            height: 125px;
            object-fit: cover;
            border-radius: 12px;
            margin-bottom: 8px;
            background: #0b0f19;
            content-visibility: auto;
        }

        .product-title {
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 6px;
            color: var(--text-primary);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .product-price {
            font-size: 15px;
            font-weight: 700;
            color: #a5b4fc;
            margin-bottom: 10px;
        }

        .btn {
            background: var(--accent-gradient);
            color: #ffffff;
            border: none;
            border-radius: 14px;
            padding: 10px 14px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.2s, transform 0.1s, background 0.3s;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
        }

        .btn:active {
            transform: scale(0.96);
            opacity: 0.9;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.08);
            box-shadow: none;
            border: 1px solid var(--card-border);
            color: var(--text-primary);
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: var(--danger-color);
            box-shadow: none;
        }

        .btn-disabled {
            background: rgba(255, 255, 255, 0.1) !important;
            color: var(--text-secondary) !important;
            box-shadow: none !important;
            cursor: not-allowed !important;
            opacity: 0.6;
        }

        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 72px;
            background: rgba(11, 15, 25, 0.85);
            backdrop-filter: blur(20px);
            border-top: 1px solid var(--card-border);
            display: flex;
            justify-content: space-around;
            align-items: center;
            z-index: 1000;
            padding-bottom: env(safe-area-inset-bottom);
        }

        .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            color: var(--text-secondary);
            font-size: 10px;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            transition: color 0.2s, transform 0.2s;
            flex: 1;
        }

        .nav-item.active {
            color: #818cf8;
        }

        .nav-item.active .nav-icon-wrapper {
            background: rgba(99, 102, 241, 0.15);
            transform: translateY(-3px);
        }

        .nav-icon-wrapper {
            width: 36px;
            height: 36px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 3px;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .nav-icon {
            font-size: 18px;
        }

        .cart-item, .admin-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 14px;
            margin-bottom: 12px;
        }

        .form-group {
            margin-bottom: 12px;
        }

        .form-group label {
            display: block;
            font-size: 11px;
            color: var(--text-secondary);
            margin-bottom: 5px;
            text-transform: uppercase;
        }

        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
            background: rgba(8, 12, 20, 0.6);
            border: 1px solid var(--card-border);
            color: white;
            padding: 12px;
            border-radius: 12px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
            border-color: #6366f1;
        }

        .badge {
            background: rgba(99, 102, 241, 0.2);
            color: #818cf8;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 600;
        }

        #edit-modal, #product-modal, #stats-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            z-index: 2000;
            justify-content: center;
            align-items: center;
            padding: 16px;
        }
        
        .modal-content {
            background: #111827;
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 20px;
            width: 100%;
            max-width: 400px;
            max-height: 90vh;
            overflow-y: auto;
            animation: fadeIn 0.3s ease;
        }

        .admin-stat-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .admin-stat-row:last-child {
            border-bottom: none;
        }
    </style>
</head>
<body>

    <!-- Главная вкладка -->
    <div id="tab-home" class="tab-content active">
        <div class="welcome-header">
            <div class="welcome-title" id="welcome-msg">Привет, гость!</div>
            <div class="welcome-subtitle">Оптовый склад · Быстрое оформление</div>
        </div>

        <div style="padding: 0 16px;">
            <div class="banner-card" style="animation: pulseGlow 4s infinite;">
                <div style="font-weight: 700; font-size: 16px; margin-bottom: 6px;">📢 Присоединяйся в канал</div>
                <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 14px;">Следи за новостями, новыми поставками и акциями C-opt EST</div>
                <button class="btn" style="width: auto; padding: 8px 16px;" onclick="window.open('https://t.me/+qSzldxTh8Zk5MDUy', '_blank')">Открыть канал</button>
            </div>

            <button class="btn" style="padding: 14px; font-size: 15px; margin-bottom: 20px;" onclick="switchTab('catalog', document.querySelectorAll('.nav-item')[1])">Перейти в каталог 🛍️</button>

            <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px; color: #a5b4fc;">📜 История заказов</h3>
            <div id="user-orders-history">
                <p style="color: var(--text-secondary); font-size: 13px;">Загрузка истории...</p>
            </div>
        </div>
    </div>

    <!-- Каталог -->
    <div id="tab-catalog" class="tab-content">
        <div style="padding: 4px 4px 10px 4px; display: flex; justify-content: space-between; align-items: center;">
            <h2 style="font-size: 18px; font-weight: 700;">Каталог товаров</h2>
            <span class="badge" id="user-role">Клиент</span>
        </div>

        <div class="search-box">
            <input type="text" id="search-input" class="search-input" placeholder="🔍 Поиск по названию..." oninput="filterProducts()">
        </div>

        <div class="category-scroll">
            <div class="cat-chip active" onclick="selectCategory('all', this)">Все</div>
            <div class="cat-chip" onclick="selectCategory('Жидкости', this)">🧃 Жидкости</div>
            <div class="cat-chip" onclick="selectCategory('Устройства', this)">💨 Устройства</div>
            <div class="cat-chip" onclick="selectCategory('Картриджи и Испарители', this)">⚡ Картриджи</div>
            <div class="cat-chip" onclick="selectCategory('Одноразки', this)">🚬 Одноразки</div>
            <div class="cat-chip" onclick="selectCategory('Разное', this)">📦 Разное</div>
        </div>

        <div class="product-grid" id="product-list">
            <p style="color: var(--text-secondary);">Загрузка товаров...</p>
        </div>
    </div>

    <!-- Корзина -->
    <div id="tab-cart" class="tab-content">
        <h2 style="font-size: 18px; font-weight: 700; margin-bottom: 14px;">Ваша корзина</h2>
        <div id="cart-list">
            <p style="color: var(--text-secondary);">Корзина пуста</p>
        </div>
        <div id="cart-summary" style="margin-top: 20px; display: none;">
            <div style="display: flex; justify-content: space-between; font-weight: bold; font-size: 18px; margin-bottom: 14px; background: var(--card-bg); padding: 16px; border-radius: 16px; border: 1px solid var(--card-border);">
                <span>Итого:</span>
                <span id="cart-total" style="color: #a5b4fc;">0 ₽</span>
            </div>
            <button class="btn" style="padding: 14px; font-size: 16px;" onclick="checkout()">Оформить заказ</button>
        </div>
    </div>

    <!-- Админка -->
    <div id="tab-admin" class="tab-content">
        <h2 style="font-size: 18px; font-weight: 700; margin-bottom: 14px;">Панель управления</h2>
        
        <div class="admin-card" style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8));">
            <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 12px; color: #a5b4fc;">📊 Статистика продаж</h3>
            <div class="admin-stat-row">
                <span style="color: var(--text-secondary); font-size: 13px;">Общая выручка:</span>
                <strong id="admin-total-revenue" style="font-size: 16px; color: #10b981;">0 ₽</strong>
            </div>
            <div class="admin-stat-row">
                <span style="color: var(--text-secondary); font-size: 13px;">Продано товаров:</span>
                <strong id="admin-items-sold" style="font-size: 16px; color: #38bdf8;">0 шт.</strong>
            </div>
            <div class="admin-stat-row">
                <span style="color: var(--text-secondary); font-size: 13px;">Успешных заказов:</span>
                <strong id="admin-total-orders" style="font-size: 16px; color: #c084fc;">0</strong>
            </div>
            <div style="display: flex; gap: 8px; margin-top: 14px;">
                <button class="btn btn-secondary" style="flex: 1; padding: 8px; font-size: 13px;" onclick="openEditStatsModal()">✏ Изменить</button>
                <button class="btn btn-danger" style="flex: 1; padding: 8px; font-size: 13px;" onclick="clearAdminStats()">🗑 Очистить</button>
            </div>
        </div>

        <div class="admin-card">
            <h3 style="font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #a5b4fc;">📢 Рассылка сообщений</h3>
            <div class="form-group">
                <label>Текст сообщения</label>
                <textarea id="broadcast-text" rows="4" placeholder="Введите текст рассылки всем пользователям..."></textarea>
            </div>
            <button class="btn" onclick="sendBroadcast()" id="broadcast-btn">Отправить всем</button>
        </div>

        <div class="admin-card">
            <h3 style="font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #a5b4fc;">➕ Добавить товар</h3>
            <div class="form-group">
                <label>Название товара</label>
                <input type="text" id="add-name" placeholder="Пример: Husky Mint 30ml">
            </div>
            <div class="form-group">
                <label>Категория</label>
                <select id="add-category">
                    <option value="Жидкости">🧃 Жидкости</option>
                    <option value="Устройства">💨 Устройства</option>
                    <option value="Картриджи и Испарители">⚡ Картриджи и Испарители</option>
                    <option value="Одноразки">🚬 Одноразки</option>
                    <option value="Разное">📦 Разное</option>
                </select>
            </div>
            <div class="form-group">
                <label>Цена (руб)</label>
                <input type="number" id="add-price" placeholder="450">
            </div>
            <div class="form-group">
                <label>Количество (шт)</label>
                <input type="number" id="add-quantity" value="10" placeholder="10">
            </div>
            <div class="form-group">
                <label>Ссылка на фото (URL)</label>
                <input type="url" id="add-image-url" placeholder="https://i.ibb.co/example/photo.jpg">
            </div>
            <div class="form-group">
                <label>Или загрузить файл</label>
                <input type="file" id="add-image-file" accept="image/*" style="padding: 6px;">
            </div>
            <button class="btn" onclick="addNewProduct()" id="add-btn">Сохранить в базу</button>
        </div>

        <div class="admin-card">
            <h3 style="font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #a5b4fc;">📄 Загрузить из PDF</h3>
            <div class="form-group">
                <label>PDF-файл с прайсом</label>
                <input type="file" id="pdf-file" accept=".pdf" style="padding: 6px;">
            </div>
            <div class="form-group">
                <label>Наценка (+₽)</label>
                <input type="number" id="markup-rubles" value="150" placeholder="150">
 
