import os
import logging
import json
import base64
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN не установлен!")
    exit(1)

# Создаем приложение бота
application = Application.builder().token(BOT_TOKEN).build()

def decode_base64_url_safe(data):
    """Декодирует base64 в URL-safe формате"""
    try:
        data = data.replace('-', '+').replace('_', '/')
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding
        
        decoded_bytes = base64.b64decode(data)
        decoded_string = decoded_bytes.decode('utf-8')
        return decoded_string
    except Exception as e:
        logging.error(f"Ошибка декодирования base64: {e}")
        return None

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_data: dict):
    """Обработка данных заказа"""
    # Сохраняем данные заказа
    context.user_data['order_data'] = order_data
    
    # Просим номер телефона
    keyboard = [
        [KeyboardButton("📞 Отправить номер телефона", request_contact=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    # Форматируем сообщение с данными заказа
    dimensions = order_data.get('dims', {})
    materials = order_data.get('mat', {})
    colors = order_data.get('col', {})
    
    # Расшифровываем тип крыши
    roof_type_map = {
        'single': 'Односкатная',
        'gable': 'Двускатная', 
        'arched': 'Арочная',
        'triangular': 'Треугольная',
        'semiarched': 'Полуарочная'
    }
    
    # Расшифровываем материалы
    material_map = {
        'polycarbonate': 'Поликарбонат',
        'metaltile': 'Металлочерепица',
        'decking': 'Профнастил'
    }
    
    roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
    roof_material = material_map.get(materials.get('r', ''), materials.get('r', 'N/A'))
    
    # Берем названия цветов как есть (они уже на русском)
    frame_color = colors.get('f', 'Не указан')
    roof_color = colors.get('r', 'Не указан')
    
    message_text = (
        f"🎉 Отлично, {update.effective_user.first_name}! Ваш навес сконфигурирован!\n\n"
        f"📐 Параметры навеса:\n"
        f"• Тип: {roof_type}\n"
        f"• Размер: {dimensions.get('w', 'N/A')}×{dimensions.get('l', 'N/A')}м\n"
        f"• Высота: {dimensions.get('h', 'N/A')}м\n"
        f"• Уклон: {dimensions.get('sl', 'N/A')}°\n"
        f"• Площадь: {order_data.get('area', 'N/A')}м²\n\n"
        f"🧱 Материалы:\n"
        f"• Кровля: {roof_material}\n"
        f"• Столбы: {materials.get('p', 'N/A')}\n"
        f"• Цвет каркаса: {frame_color}\n"
        f"• Цвет кровли: {roof_color}\n\n"
        f"💰 Предварительная стоимость: {order_data.get('pr', 0):,} руб.\n\n"
        f"Для оформления заказа поделитесь номером телефона:"
    )
    
    await update.message.reply_text(message_text, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    logging.info(f"Команда /start от пользователя {user.id}")
    if context.args:
        logging.info(f"Аргументы: {context.args}")
    
    # Проверяем, есть ли параметры в команде /start (Deep Link из сайта)
    if context.args and context.args[0].startswith('order_'):
        try:
            order_data_encoded = context.args[0][6:]
            
            logging.info(f"Получены закодированные данные: {order_data_encoded}")
            
            order_data_json = decode_base64_url_safe(order_data_encoded)
            
            if order_data_json:
                order_data = json.loads(order_data_json)
                logging.info(f"Декодированные данные заказа: {order_data}")
                
                await process_order(update, context, order_data)
                return
            else:
                await update.message.reply_text("❌ Ошибка при обработке данных заказа")
                
        except Exception as e:
            logging.error(f"Ошибка обработки заказа: {e}")
            await update.message.reply_text("❌ Произошла ошибка при обработке заказа")
    
    # Если параметров нет - обычное приветствие
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов. Нажмите кнопку ниже чтобы создать навес в конструкторе:",
        reply_markup=reply_markup
    )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        contact = update.message.contact
        user = update.effective_user
        
        order_data = context.user_data.get('order_data', {})
        
        admin_message = f"🚨 НОВЫЙ ЗАКАЗ!\n\n👤 Клиент: {user.first_name}\n📞 Телефон: {contact.phone_number}\n"
        
        if order_data:
            dimensions = order_data.get('dims', {})
            materials = order_data.get('mat', {})
            colors = order_data.get('col', {})
            
            roof_type_map = {
                'single': 'Односкатная',
                'gable': 'Двускатная', 
                'arched': 'Арочная',
                'triangular': 'Треугольная',
                'semiarched': 'Полуарочная'
            }
            
            roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
            
            admin_message += (
                f"📐 Тип: {roof_type}\n"
                f"📏 Размер: {dimensions.get('w', 'N/A')}×{dimensions.get('l', 'N/A')}м\n"
                f"📏 Высота: {dimensions.get('h', 'N/A')}м\n"
                f"🧱 Материалы: {materials.get('r', 'N/A')}, {materials.get('p', 'N/A')}\n"
                f"🎨 Цвет каркаса: {colors.get('f', 'Не указан')}\n"
                f"🎨 Цвет кровли: {colors.get('r', 'Не указан')}\n"
                f"💰 Стоимость: {order_data.get('pr', 0):,} руб.\n"
                f"🆔 ID конфигурации: {order_data.get('id', 'N/A')}\n"
            )
        else:
            admin_message += "💬 Клиент хочет обсудить конфигурацию навеса\n"
        
        try:
            await context.bot.send_message(chat_id=5216818742, text=admin_message)
        except Exception as e:
            logging.error(f"Ошибка уведомления админа: {e}")
        
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
            "В ближайшее время с вами свяжется менеджер для уточнения деталей.\n\n"
            "Спасибо, что выбрали нас!",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        if 'order_data' in context.user_data:
            del context.user_data['order_data']

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажмите /start чтобы начать работу с ботом.")

# Добавляем обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Flask app для здоровья
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для навесов работает!"

@app.route('/health')
def health():
    return {"status": "ok", "service": "canopy-bot"}

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def run_bot():
    """Запуск бота в отдельном потоке"""
    logging.info("🚀 Запускаем бота...")
    try:
        # Используем polling с настройками для Replit
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
    except Exception as e:
        logging.error(f"Ошибка запуска бота: {e}")
        # Перезапуск через 5 секунд
        import time
        time.sleep(5)
        run_bot()

def main():
    """Главная функция"""
    logging.info("=== ЗАПУСК ПРИЛОЖЕНИЯ ===")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logging.info("🌐 Flask сервер запущен")
    
    # Запускаем бота в основном потоке
    run_bot()

if __name__ == '__main__':
    main()
