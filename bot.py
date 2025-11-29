import os
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запускаем веб-сервер для UptimeRobot
keep_alive()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Создаем кнопку с WebApp
    keyboard = [
        [InlineKeyboardButton(
            "🏗️ Создать навес", 
            web_app=WebAppInfo(url="https://kovka007.vercel.app")
        )],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов. Нажмите кнопку ниже чтобы создать навес в конструкторе:",
        reply_markup=reply_markup
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем данные из WebApp"""
    try:
        # Получаем данные из WebApp
        web_app_data = update.effective_message.web_app_data
        data = json.loads(web_app_data.data)
        
        logging.info(f"Получены данные из WebApp: {data}")
        
        # Сохраняем данные заказа
        context.user_data['order_data'] = data
        
        # Просим номер телефона
        from telegram import KeyboardButton, ReplyKeyboardMarkup
        
        keyboard = [
            [KeyboardButton("📞 Отправить номер телефона", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"🎉 Отлично! Ваш навес сконфигурирован!\n\n"
            f"📐 Параметры:\n"
            f"• Размеры: {data.get('dimensions', 'не указаны')}\n"
            f"• Материалы: {data.get('materials', 'не указаны')}\n"
            f"• Стоимость: {data.get('cost', 0)} руб.\n\n"
            f"Для оформления заказа поделитесь номером телефона:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logging.error(f"Ошибка обработки WebApp данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке заказа")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        contact = update.message.contact
        user = update.effective_user
        
        # Получаем данные заказа
        order_data = context.user_data.get('order_data', {})
        
        # Формируем сообщение для админа
        admin_message = (
            f"🚨 НОВЫЙ ЗАКАЗ!\n\n"
            f"👤 Клиент: {user.first_name}\n"
            f"📞 Телефон: {contact.phone_number}\n"
        )
        
        if order_data:
            admin_message += (
                f"📐 Размеры: {order_data.get('dimensions', 'не указаны')}\n"
                f"🧱 Материалы: {order_data.get('materials', 'не указаны')}\n"
                f"💰 Стоимость: {order_data.get('cost', 0)} руб.\n"
            )
        
        # Уведомляем админа
        await context.bot.send_message(chat_id=5216818742, text=admin_message)
        
        # Ответ пользователю
        from telegram import ReplyKeyboardMarkup
        
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
            "В ближайшее время с вами свяжется менеджер для уточнения деталей.\n\n"
            "Спасибо, что выбрали нас!",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        # Очищаем данные заказа
        if 'order_data' in context.user_data:
            del context.user_data['order_data']

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений"""
    await update.message.reply_text(
        "Нажмите /start чтобы начать работу с ботом."
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()
