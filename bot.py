import os
import logging
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext
from telegram.ext import Filters
from keep_alive import keep_alive

keep_alive()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

def start(update, context):
    user = update.effective_user
    logger.info(f"Команда /start от {user.first_name} (ID: {user.id})")
    
    # Приветственное сообщение
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов от Ковка007.\n\n"
        "🏗️ *Как сделать заказ:*\n"
        "1. Нажмите кнопку ниже чтобы создать навес в конструкторе\n"
        "2. Настройте параметры навеса\n" 
        "3. Нажмите 'Создать заказ' - данные скопируются автоматически\n"
        "4. Вернитесь в этот чат и *ВСТАВЬТЕ* скопированные данные\n\n"
        "Я обработаю ваш заказ и запрошу контакт для связи!\n\n"
        "📞 Или сразу свяжитесь с менеджером для консультации:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

def handle_message(update, context):
    user = update.effective_user
    text = update.message.text
    logger.info(f"Сообщение от {user.id}: {text[:100]}...")
    
    try:
        # Пытаемся распарсить JSON
        order_data = json.loads(text)
        logger.info(f"Успешно распарсен JSON: {order_data}")
        
        # Проверяем, что это данные заказа
        if all(key in order_data for key in ['id', 't', 'w', 'l', 'h', 'pr']):
            process_order(update, context, order_data)
        else:
            update.message.reply_text(
                "❌ Это не похоже на данные заказа. Пожалуйста, скопируйте данные из конструктора навесов и вставьте их сюда."
            )
            
    except json.JSONDecodeError:
        # Если это не JSON, проверяем не команда ли это
        if text.startswith('/'):
            start(update, context)
        else:
            # Обычное сообщение - просим прислать данные заказа
            update.message.reply_text(
                "📋 *Я жду данные по заказу!*\n\n"
                "Чтобы сделать заказ:\n"
                "1. Нажмите кнопку 'Создать навес' ниже\n"
                "2. Настройте параметры в конструкторе\n"
                "3. Нажмите 'Создать заказ' - данные скопируются\n"
                "4. Вернитесь сюда и *ВСТАВЬТЕ* скопированные данные\n\n"
                "Или свяжитесь с менеджером для помощи:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
                    [InlineKeyboardButton("📞 Помощь менеджера", url="https://t.me/thetaranov")]
                ]),
                parse_mode='Markdown'
            )

def process_order(update, context, order_data):
    """Обрабатывает данные заказа"""
    user = update.effective_user
    logger.info(f"Обрабатываем заказ {order_data.get('id')} от {user.id}")
    
    # Сохраняем данные заказа
    context.user_data['order_data'] = order_data
    
    # Маппинг типов крыши для красивого отображения
    roof_type_map = {
        'single': 'Односкатная',
        'gable': 'Двускатная', 
        'arched': 'Арочная',
        'triangular': 'Треугольная',
        'semiarched': 'Полуарочная'
    }
    
    roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
    
    # Форматируем сообщение с деталями заказа
    message_text = (
        f"🎉 *Заказ получен!* ID: `{order_data.get('id')}`\n\n"
        f"📐 *Параметры навеса:*\n"
        f"• Тип: {roof_type}\n"
        f"• Размер: {order_data.get('w')}×{order_data.get('l')}м\n"
        f"• Высота: {order_data.get('h')}м\n"
        f"• Уклон: {order_data.get('s', 'N/A')}°\n"
        f"💰 *Стоимость:* {order_data.get('pr', 0):,} руб.\n\n"
        f"📞 *Для оформления заказа поделитесь номером телефона:*"
    )
    
    # Создаем клавиатуру с кнопкой для отправки контакта
    keyboard = [[KeyboardButton("📞 Отправить номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    logger.info(f"Детали заказа отправлены пользователю {user.id}")

def handle_contact(update, context):
    """Обрабатывает отправку контакта"""
    user = update.effective_user
    contact = update.message.contact
    order_data = context.user_data.get('order_data', {})
    
    logger.info(f"Контакт от {user.id}: {contact.phone_number}")
    
    # Формируем сообщение для админа
    admin_message = (
        f"🚨 *НОВЫЙ ЗАКАЗ!*\n\n"
        f"👤 *Клиент:* {user.first_name}\n"
        f"📞 *Телефон:* +{contact.phone_number}\n"
        f"🆔 *User ID:* {user.id}\n"
    )
    
    if order_data:
        roof_type_map = {
            'single': 'Односкатная',
            'gable': 'Двускатная', 
            'arched': 'Арочная',
            'triangular': 'Треугольная',
            'semiarched': 'Полуарочная'
        }
        
        roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
        
        admin_message += (
            f"\n📐 *Конфигурация навеса:*\n"
            f"• Тип: {roof_type}\n"
            f"• Размер: {order_data.get('w')}×{order_data.get('l')}м\n"
            f"• Высота: {order_data.get('h')}м\n"
            f"• Стоимость: {order_data.get('pr', 0):,} руб.\n"
            f"• ID заказа: {order_data.get('id', 'N/A')}\n"
        )
    else:
        admin_message += "\n💬 *Клиент хочет обсудить конфигурацию навеса*"
    
    try:
        # Отправляем уведомление админу
        context.bot.send_message(
            chat_id=5216818742, 
            text=admin_message,
            parse_mode='Markdown'
        )
        logger.info(f"Уведомление отправлено админу о заказе {order_data.get('id')}")
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")
    
    # Подтверждение пользователю
    update.message.reply_text(
        "✅ *Отлично! Ваш заказ принят!* 🏗️\n\n"
        "В ближайшее время с вами свяжется наш менеджер для уточнения деталей.\n\n"
        "Спасибо, что выбрали Ковка007! 💙",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    
    # Очищаем данные заказа
    if 'order_data' in context.user_data:
        del context.user_data['order_data']

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.contact, handle_contact))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    logger.info("🤖 Бот запущен (режим копирования данных)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
