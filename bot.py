import os
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запускаем Flask сервер для поддержки жизни (актуально для Render/Heroku)
keep_alive()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# === ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветствие с кнопкой WebApp"""
    user = update.effective_user
    logger.info(f"User {user.id} started bot")

    # ВАЖНО: Используем WebAppInfo вместо url, чтобы работала отправка данных обратно
    # Замените URL на ваш актуальный адрес Vercel
    web_app_url = "https://kovka007.vercel.app"
    
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес (Конструктор)", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для расчета стоимости навесов.\n"
        "Нажмите кнопку ниже, чтобы открыть 3D-конструктор, собрать навес и оформить заказ прямо в Telegram:",
        reply_markup=reply_markup
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Этот обработчик ловит данные, отправленные через Telegram.WebApp.sendData
    """
    user = update.effective_user
    # Получаем данные из service message
    data = update.effective_message.web_app_data.data
    
    logger.info(f"Получены данные из WebApp от {user.id}: {data}")

    try:
        order_data = json.loads(data)
        await process_order_data(update, context, order_data, "WebApp")
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Ошибка обработки данных заказа.")

async def handle_text_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик для ручной вставки JSON (резервный метод)
    """
    text = update.message.text.strip()
    
    # Проверяем, похоже ли на JSON заказа
    if text.startswith('{') and 'CFG-' in text:
        try:
            order_data = json.loads(text)
            await process_order_data(update, context, order_data, "Ручной ввод")
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Неверный формат данных.")
    else:
        # Если это просто текст, можно вернуть инструкцию
        await start(update, context)

async def process_order_data(update: Update, context: ContextTypes.DEFAULT_TYPE, order_data, source):
    """Логика обработки заказа"""
    
    # Сохраняем данные во временное хранилище (user_data)
    context.user_data['order_data'] = order_data
    
    roof_type_map = {
        'single': 'Односкатная',
        'gable': 'Двускатная', 
        'arched': 'Арочная',
        'triangular': 'Треугольная',
        'semiarched': 'Полуарочная'
    }
    
    roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
    price = order_data.get('pr', 0)
    
    message_text = (
        f"🎉 *Заказ сформирован!*\n"
        f"🆔 ID: `{order_data.get('id')}`\n\n"
        f"📐 *Конфигурация:*\n"
        f"• Тип: {roof_type}\n"
        f"• Габариты: {order_data.get('w')}x{order_data.get('l')} м\n"
        f"• Высота: {order_data.get('h')} м\n\n"
        f"💰 *Итоговая стоимость: {price:,} руб.*\n\n"
        f"👇 Нажмите кнопку ниже, чтобы отправить ваш контакт для связи с менеджером."
    )
    
    # Кнопка запроса контакта
    keyboard = [[KeyboardButton("📞 Отправить телефон", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение контакта и отправка уведомления админу"""
    user = update.effective_user
    contact = update.message.contact
    order_data = context.user_data.get('order_data', {})
    
    # Формируем сообщение для админа (замените ID на свой)
    ADMIN_ID = 5216818742
    
    admin_text = (
        f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n"
        f"👤 Клиент: {user.first_name} (@{user.username})\n"
        f"📞 Телефон: {contact.phone_number}\n"
        f"-------------------\n"
        f"🆔 Заказ: {order_data.get('id', 'Нет ID')}\n"
        f"💰 Сумма: {order_data.get('pr', 0)} руб.\n"
        f"📝 JSON: <code>{json.dumps(order_data)}</code>"
    )
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Не удалось отправить админу: {e}")

    # Ответ пользователю
    await update.message.reply_text(
        "✅ <b>Спасибо! Ваша заявка принята.</b>\n\n"
        "Менеджер получил данные вашего проекта и скоро свяжется с вами.",
        reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True),
        parse_mode='HTML'
    )

def main():
    """Запуск бота"""
    # Создаем Application (вместо Updater)
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    
    # Обработчик данных из WebApp (сервисное сообщение)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    # Обработчик контактов
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # Обработчик текстовых сообщений (резервный JSON или обычный текст)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_json))

    logger.info("🤖 Бот запущен (Async v20.7)")
    
    # Запуск polling
    application.run_polling()

if __name__ == '__main__':
    main()
