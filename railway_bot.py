import os
import logging
import psycopg2
import json
import asyncio
from threading import Thread
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_IDS = json.loads(os.getenv('ADMIN_IDS', '[]'))
CONSTRUCTOR_URL = os.getenv('CONSTRUCTOR_URL', 'https://kovka007.vercel.app')

# Инициализация базы данных
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            phone TEXT,
            full_name TEXT,
            ref_code TEXT UNIQUE,
            referred_by INTEGER,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
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
    
    # Таблица бригад
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id SERIAL PRIMARY KEY,
            name TEXT,
            master_name TEXT,
            contact_info TEXT,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully")

# Функции работы с базой данных
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
    
    # Обработка реферала
    if ref_code and ref_code.startswith('ref_'):
        cursor.execute("SELECT id FROM users WHERE ref_code = %s", (ref_code,))
        referrer = cursor.fetchone()
        if referrer:
            cursor.execute('''
                UPDATE users SET referred_by = %s 
                WHERE telegram_id = %s AND referred_by IS NULL
            ''', (referrer[0], telegram_id))
    
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
        [InlineKeyboardButton("🏗️ Создать навес", web_app=WebAppInfo(url=CONSTRUCTOR_URL))],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system")],
        [InlineKeyboardButton("📞 Связаться с менеджером", callback_data="contact_manager")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Добро пожаловать, {user.first_name}! 👋\n\n"
        "Я ваш помощник в создании идеального навеса. Вот что я могу:\n\n"
        "• 🏗️ Помочь создать 3D-конструкцию навеса\n"
        "• 📊 Рассчитать стоимость\n"
        "• 👥 Связать вас с персональным менеджером\n"
        "• 💰 Предложить выгодные условия по реферальной программе\n\n"
        "Выберите действие:",
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
            "✅ Отлично! Ваш заказ принят!\n\n"
            "В ближайшее время с вами свяжется ваш личный менеджер для уточнения деталей "
            "и согласования итоговой стоимости.\n\n"
            "Спасибо, что выбрали нас! 🙏",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)  # Убираем клавиатуру
        )
        
        # Уведомление админов
        order_data = context.user_data['pending_order']
        admin_message = (
            f"🚨 ПОСТУПИЛ НОВЫЙ ЗАКАЗ! №{order_id}\n\n"
            f"👤 Клиент: {user.first_name} {user.last_name or ''}\n"
            f"📞 Телефон: {contact.phone_number}\n"
            f"📐 Конфигурация: {order_data.get('config_id', 'N/A')}\n"
            f"💰 Предварительная стоимость: {order_data.get('demo_cost', 0)} руб.\n"
            f"⏰ Время: {update.message.date.strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Отправляем уведомление всем админам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id, 
                    text=admin_message,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📞 Позвонить", callback_data=f"call_{contact.phone_number}"),
                        InlineKeyboardButton("💬 Написать", callback_data=f"msg_{user.id}")
                    ]])
                )
            except Exception as e:
                logging.error(f"Failed to notify admin {admin_id}: {e}")
        
        # Очищаем временные данные
        del context.user_data['pending_order']

async def ref_system_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if user:
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start=ref_{user[5]}"  # ref_code
        
        await query.edit_message_text(
            f"👥 Реферальная программа\n\n"
            f"Приглашайте друзей и получайте бонусы!\n\n"
            f"🔗 Ваша реферальная ссылка:\n"
            f"`{ref_link}`\n\n"
            f"💎 Текущий баланс: {user[7]} руб.\n\n"
            f"За каждого приглашенного друга, который сделает заказ, "
            f"вы получаете 5% от суммы его заказа на бонусный счет.",
            parse_mode='Markdown'
        )

async def admin_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Статистика
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'new'")
    new_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📊 Все заказы", callback_data="admin_orders")],
        [InlineKeyboardButton("🆕 Новые заказы", callback_data="admin_new_orders")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("🏗️ Бригады", callback_data="admin_teams")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👨‍💼 Панель администратора\n\n"
        f"📈 Статистика:\n"
        f"• 🆕 Новых заказов: {new_orders}\n"
        f"• 📦 Всего заказов: {total_orders}\n"
        f"• 👥 Пользователей: {total_users}",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: CallbackContext):
    if update.message.text and not update.message.text.startswith('/'):
        await update.message.reply_text(
            "Используйте кнопки меню для навигации или команду /start для начала работы."
        )

# Flask app для здоровья (требуется Railway)
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для навесов работает!"

@app.route('/health')
def health():
    return {"status": "ok", "service": "telegram-bot"}

@app.route('/webhook', methods=['POST'])
def webhook():
    # Эндпоинт для будущих webhook интеграций
    return {"status": "webhook_received"}

def run_flask():
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

async def run_bot():
    """Запуск Telegram бота"""
    logging.info("Initializing bot...")
    init_db()
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(CallbackQueryHandler(ref_system_handler, pattern="^ref_system$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Bot started successfully!")
    
    # Запускаем polling
    await application.run_polling()

def main():
    """Главная функция запуска"""
    # Проверяем обязательные переменные
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN not set!")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logging.info("Flask server started")
    
    # Запускаем бота в основном потоке
    asyncio.run(run_bot())

if __name__ == '__main__':
    main()