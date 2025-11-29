import os
import logging
import json
import sqlite3
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = json.loads(os.getenv('ADMIN_IDS', '[5216818742]'))

# Используем SQLite
DB_FILE = "canopy_bot.db"

def init_db():
    """Инициализация SQLite базы данных"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Таблица заказов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                customer_name TEXT,
                customer_phone TEXT,
                config_data TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✅ SQLite база данных инициализирована")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")

def save_order(telegram_id, customer_name, customer_phone, config_data):
    """Сохраняем заказ в SQLite"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO orders (telegram_id, customer_name, customer_phone, config_data)
            VALUES (?, ?, ?, ?)
        ''', (telegram_id, customer_name, customer_phone, json.dumps(config_data)))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return order_id
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения заказа: {e}")
        return None

# Обработчики команд бота
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    
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
                "🎉 Отлично! Ваш навес сконфигурирован!\n\n"
                "Для оформления заказа поделитесь вашим номером телефона:",
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            logging.error(f"Ошибка декодирования заказа: {e}")
    
    # Обычное приветствие
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", web_app=WebAppInfo(url="https://kovka007.vercel.app"))],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я ваш помощник в создании идеального навеса. "
        "Нажмите кнопку ниже, чтобы перейти в конструктор:",
        reply_markup=reply_markup
    )

async def handle_contact(update: Update, context: CallbackContext):
    if update.message.contact and 'pending_order' in context.user_data:
        contact = update.message.contact
        user = update.effective_user
        
        # Сохраняем заказ
        order_id = save_order(
            user.id,
            f"{user.first_name} {user.last_name or ''}".strip(),
            contact.phone_number,
            context.user_data['pending_order']
        )
        
        # Уведомление клиента
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят!\n\n"
            "В ближайшее время с вами свяжется ваш личный менеджер "
            "для уточнения деталей и согласования итоговой стоимости.\n\n"
            "Спасибо, что выбрали нас! 🏗️",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        # Уведомление админов
        if order_id:
            order_data = context.user_data['pending_order']
            admin_message = (
                f"🚨 НОВЫЙ ЗАКАЗ №{order_id}\n\n"
                f"👤 Клиент: {user.first_name}\n"
                f"📞 Телефон: {contact.phone_number}\n"
                f"💰 Стоимость: {order_data.get('demo_cost', 0)} руб.\n"
                f"⏰ Время: {update.message.date.strftime('%H:%M %d.%m.%Y')}"
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_message
                    )
                except Exception as e:
                    logging.error(f"Ошибка уведомления админа {admin_id}: {e}")
        
        # Очищаем временные данные
        del context.user_data['pending_order']
    else:
        await update.message.reply_text("Пожалуйста, сначала создайте навес в конструкторе.")

async def admin_command(update: Update, context: CallbackContext):
    """Команда для админов"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'new'")
        new_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]
        conn.close()
        
        await update.message.reply_text(
            f"📊 Панель администратора\n\n"
            f"• 🆕 Новых заказов: {new_orders}\n"
            f"• 📦 Всего заказов: {total_orders}\n\n"
            f"Используйте конструктор: https://kovka007.vercel.app"
        )
    except Exception as e:
        logging.error(f"Ошибка БД в admin_command: {e}")
        await update.message.reply_text("❌ Ошибка доступа к базе данных")

async def handle_message(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    await update.message.reply_text(
        "Используйте команду /start для начала работы."
    )

# Flask app для здоровья (обязательно для Render)
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для заказов навесов работает!"

@app.route('/health')
def health():
    return {"status": "ok", "service": "canopy-bot"}

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

async def run_bot():
    """Запуск Telegram бота"""
    logging.info("🚀 Инициализация бота...")
    
    # Инициализируем базу данных
    init_db()
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("✅ Бот запущен и готов к работе!")
    
    # Запускаем polling
    await application.run_polling()

def main():
    """Главная функция"""
    if not BOT_TOKEN:
        logging.error("❌ BOT_TOKEN не установлен!")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logging.info("🌐 Flask сервер запущен")
    
    # Запускаем бота
    asyncio.run(run_bot())

if __name__ == '__main__':
    main()
