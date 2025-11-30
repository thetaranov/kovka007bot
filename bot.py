import os
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запуск Flask (если нужно)
keep_alive()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    logger.info(f"--- START от {user.id} ---")

    # ССЫЛКА НА ВАШ САЙТ
    web_app_url = "https://kovka007.vercel.app"
    
    keyboard = [
        [InlineKeyboardButton("🏗️ Открыть конструктор", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Нажмите кнопку ниже, чтобы собрать навес:",
        reply_markup=reply_markup
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных WebApp (Стандартный)"""
    logger.info("⚡ Сработал стандартный фильтр WebApp!")
    await process_data(update, update.effective_message.web_app_data.data)

async def catch_all_debugger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ЛОВУШКА: Ловит всё, что не поймали другие, и проверяет на наличие данных"""
    logger.info("🔍 Ловушка поймала сообщение!")
    
    # Проверяем, есть ли в сообщении данные WebApp, даже если фильтр не сработал
    if update.effective_message.web_app_data:
        logger.info("✅ В сообщении НАЙДЕНЫ данные WebApp (через ловушку)!")
        await process_data(update, update.effective_message.web_app_data.data)
    else:
        logger.info("❌ Это обычное сообщение, не WebApp.")

async def process_data(update: Update, data_str):
    """Единая функция обработки JSON"""
    try:
        logger.info(f"📦 RAW DATA: {data_str}")
        order_data = json.loads(data_str)
        
        # Сохраняем для контакта
        context.user_data['order_data'] = order_data
        
        # Формируем ответ
        text = (
            f"🎉 <b>ЗАКАЗ ПОЛУЧЕН!</b>\n\n"
            f"🆔 <code>{order_data.get('id')}</code>\n"
            f"📏 Размер: {order_data.get('w')} x {order_data.get('l')} м\n"
            f"💰 Сумма: <b>{order_data.get('pr')} руб.</b>\n\n"
            f"👇 <i>Нажмите кнопку ниже, чтобы отправить телефон менеджеру:</i>"
        )
        
        kb = [[KeyboardButton("📞 Отправить телефон", request_contact=True)]]
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        logger.info("✅ Ответ пользователю отправлен")
        
    except Exception as e:
        logger.error(f"🔥 Ошибка обработки: {e}")
        await update.message.reply_text("Ошибка обработки данных заказа.")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = update.message.contact.phone_number
    data = context.user_data.get('order_data', {})
    
    # ОТПРАВКА АДМИНУ (Вставьте свой ID, если нужно)
    # await context.bot.send_message(chat_id=ADMIN_ID, text=...)

    await update.message.reply_text(
        f"✅ Спасибо, {user.first_name}! Менеджер свяжется с вами по номеру {phone}.",
        reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True)
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # 1. Команда старт
    application.add_handler(CommandHandler("start", start))
    
    # 2. Обработчик WebApp данных (приоритетный)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    
    # 3. Обработчик контакта
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # 4. ЛОВУШКА (Должна быть последней)
    # Она поймает сообщение с данными, если пункт 2 не сработает по какой-то причине
    application.add_handler(MessageHandler(filters.ALL, catch_all_debugger))

    logger.info("🚀 Бот запущен! Ожидаем данные...")
    application.run_polling()

if __name__ == '__main__':
    main()
