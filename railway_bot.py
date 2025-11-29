import os
import logging
import json
import asyncio
from threading import Thread
from flask import Flask

# Используем pg8000 вместо psycopg2
try:
    import pg8000
    from pg8000 import dbapi
except ImportError:
    # Fallback на SQLite если pg8000 не установлен
    import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_IDS = json.loads(os.getenv('ADMIN_IDS', '[]'))

# Функции работы с базой данных
def get_db_connection():
    """Устанавливает соединение с PostgreSQL используя pg8000"""
    if DATABASE_URL:
        try:
            # Парсим DATABASE_URL
            import urllib.parse
            url = urllib.parse.urlparse(DATABASE_URL)
            
            conn = dbapi.connect(
                host=url.hostname,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                database=url.path[1:]  # убираем первый /
            )
            return conn
        except Exception as e:
            logging.error(f"Ошибка подключения к PostgreSQL: {e}")
    
    # Fallback на SQLite
    logging.info("Используется SQLite база данных")
    return sqlite3.connect('canopy_bot.db')

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username TEXT,
                phone TEXT,
                full_name TEXT,
                ref_code TEXT UNIQUE,
                balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица заказов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                configuration_id TEXT,
                dimensions TEXT,
                materials TEXT,
                demo_cost REAL,
                status TEXT DEFAULT 'new',
                customer_name TEXT,
                customer_phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        logging.info("✅ База данных инициализирована успешно")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")
    finally:
        conn.close()

def get_user(telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(telegram_id, username, ref_code=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    user_ref_code = f"ref_{telegram_id}"
    
    cursor.execute('''
        INSERT INTO users (telegram_id, username, ref_code) 
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username
        RETURNING id
    ''', (telegram_id, username, user_ref_code))
    
    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return user_id

def create_order(user_id, order_data, customer_name, customer_phone):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO orders (user_id, configuration_id, dimensions, materials, demo_cost, customer_name, customer_phone)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        user_id, 
        order_data.get('config_id'),
        json.dumps(order_data.get('dimensions', {})),
        json.dumps(order_data.get('materials', {})),
        order_data.get('demo_cost', 0),
        customer_name,
        customer_phone
    ))
    
    order_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return order_id

# Обработчики команд бота
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    ref_code = context.args[0] if context.args else None
    
    user_id = create_user(user.id, user.username, ref_code)
    
    # Проверяем, пришел ли заказ из конструктора
    if context.args and context.args[0].startswith('order_'):
        try:
            import base64
            order_data_encoded = context.args[0].replace('order_', '')
            order_data_json = base64.b64decode(order_data_encoded).decode('utf-8')
            order_data = json.loads(order_data_json)
            context.user_data['pending_order'] = order_data
            
            keyboard = [
                [KeyboardButton("📞 Отправить номер телефона", request_contact=True)]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                "Отлично! Ваш навес сконфигурирован. Для оформления заказа нам нужен ваш номер телефона.",
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            logging.error(f"Error decoding order data: {e}")
    
    # Обычное приветствие
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", web_app=WebAppInfo(url="https://kovka007.vercel.app"))],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! Я бот для заказов навесов 🏗️",
        reply_markup=reply_markup
    )

async def handle_contact(update: Update, context: CallbackContext):
    if update.message.contact and 'pending_order' in context.user_data:
        contact = update.message.contact
        user = update.effective_user
        
        # Сохраняем контактные данные
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET phone = %s, full_name = %s 
            WHERE telegram_id = %s
        ''', (contact.phone_number, f"{user.first_name} {user.last_name or ''}".strip(), user.id))
        conn.commit()
        conn.close()
        
        # Создаем заказ
        user_db = get_user(user.id)
        order_id = create_order(
            user_db[0], 
            context.user_data['pending_order'],
            f"{user.first_name} {user.last_name or ''}".strip(),
            contact.phone_number
        )
        
        # Уведомление клиента
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят! Менеджер свяжется с вами скоро.",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        # Уведомление админов
        order_data = context.user_data['pending_order']
        admin_message = f"🆕 Новый заказ #{order_id}\nКлиент: {user.first_name}\nТелефон: {contact.phone_number}"
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, admin_message)
            except Exception as e:
                logging.error(f"Failed to notify admin: {e}")
        
        del context.user_data['pending_order']

# Flask app для здоровья
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для навесов работает!"

@app.route('/health')
def health():
    return {"status": "ok"}

def run_flask():
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

async def run_bot():
    """Запуск Telegram бота"""
    logging.info("Initializing bot...")
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    logging.info("🤖 Бот запускается...")
    await application.run_polling()

def main():
    if not BOT_TOKEN:
        logging.error("❌ BOT_TOKEN not set!")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота
    asyncio.run(run_bot())

if __name__ == '__main__':
    main()
