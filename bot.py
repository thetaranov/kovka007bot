import os
import logging
import json
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = json.loads(os.getenv('ADMIN_IDS', '[5216818742]'))

# Хранилище заказов в памяти (для простоты)
orders = []

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я ваш помощник в создании идеального навеса. "
        "Нажмите кнопку ниже, чтобы перейти в конструктор:",
        reply_markup=reply_markup
    )

def handle_contact(update: Update, context: CallbackContext):
    if update.message.contact:
        contact = update.message.contact
        user = update.effective_user
        
        # Сохраняем заказ
        order_data = {
            'user_id': user.id,
            'user_name': f"{user.first_name} {user.last_name or ''}".strip(),
            'phone': contact.phone_number,
            'timestamp': str(update.message.date)
        }
        orders.append(order_data)
        
        # Уведомление клиента
        update.message.reply_text(
            "✅ Отлично! Ваши контактные данные сохранены!\n\n"
            "В ближайшее время с вами свяжется менеджер "
            "для консультации по вашему навесу.\n\n"
            "Спасибо, что выбрали нас! 🏗️",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        # Уведомление админов
        admin_message = (
            f"🚨 НОВЫЙ КОНТАКТ!\n\n"
            f"👤 Клиент: {user.first_name}\n"
            f"📞 Телефон: {contact.phone_number}\n"
            f"⏰ Время: {update.message.date.strftime('%H:%M %d.%m.%Y')}\n"
            f"Всего заказов: {len(orders)}"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message
                )
            except Exception as e:
                logging.error(f"Ошибка уведомления админа {admin_id}: {e}")
    else:
        update.message.reply_text("Пожалуйста, сначала создайте навес в конструкторе.")

def admin_command(update: Update, context: CallbackContext):
    """Команда для админов"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        update.message.reply_text("❌ У вас нет доступа к этой команде")
        return
    
    update.message.reply_text(
        f"📊 Панель администратора\n\n"
        f"• 📦 Всего заказов: {len(orders)}\n\n"
        f"Используйте конструктор: https://kovka007.vercel.app"
    )

def handle_message(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    update.message.reply_text(
        "Используйте команду /start для начала работы."
    )

# Flask app для здоровья
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для заказов навесов работает!"

@app.route('/health')
def health():
    return {"status": "ok", "orders_count": len(orders)}

def main():
    if not BOT_TOKEN:
        logging.error("❌ BOT_TOKEN не установлен!")
        return
    
    # Создаем updater и dispatcher
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Добавляем обработчики
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(MessageHandler(Filters.contact, handle_contact))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Запускаем Flask в отдельном потоке
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000))), daemon=True).start()
    
    # Запускаем бота
    logging.info("🚀 Бот запускается...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
