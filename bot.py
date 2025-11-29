import os
import logging
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запускаем веб-сервер для UptimeRobot
keep_alive()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv('BOT_TOKEN')

def decode_base64_url_safe(data):
    """Декодирует base64 в URL-safe формате"""
    # Заменяем обратно - на + и _ на /
    data = data.replace('-', '+').replace('_', '/')
    # Добавляем padding если нужно
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += '=' * padding
    
    try:
        decoded_bytes = base64.b64decode(data)
        decoded_string = decoded_bytes.decode('utf-8')
        return decoded_string
    except Exception as e:
        logging.error(f"Ошибка декодирования base64: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем, есть ли параметры в команде /start (Deep Link из сайта)
    if context.args and context.args[0].startswith('order_'):
        try:
            # Получаем закодированные данные (после 'order_')
            order_data_encoded = context.args[0][6:]  # Убираем 'order_'
            
            # Декодируем из base64 URL-safe
            order_data_json = decode_base64_url_safe(order_data_encoded)
            if order_data_json:
                order_data = json.loads(order_data_json)
                
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
                options = order_data.get('opt', {})
                
                message_text = (
                    f"🎉 Отлично, {user.first_name}! Ваш навес сконфигурирован!\n\n"
                    f"📐 Параметры навеса:\n"
                    f"• Размер: {dimensions.get('w', 'N/A')}×{dimensions.get('l', 'N/A')}м\n"
                    f"• Высота: {dimensions.get('h', 'N/A')}м\n"
                    f"• Уклон: {dimensions.get('sl', 'N/A')}°\n"
                    f"• Площадь: {order_data.get('area', 'N/A')}м²\n\n"
                    f"🧱 Материалы:\n"
                    f"• Кровля: {materials.get('r', 'N/A')}\n"
                    f"• Столбы: {materials.get('p', 'N/A')}\n\n"
                    f"💰 Предварительная стоимость: {order_data.get('pr', 0):,} руб.\n\n"
                    f"Для оформления заказа поделитесь номером телефона:"
                )
                
                await update.message.reply_text(message_text, reply_markup=reply_markup)
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
        
        # Проверяем, есть ли данные заказа
        order_data = context.user_data.get('order_data', {})
        
        # Формируем сообщение для админа
        admin_message = f"🚨 НОВЫЙ ЗАКАЗ!\n\n👤 Клиент: {user.first_name}\n📞 Телефон: {contact.phone_number}\n"
        
        if order_data:
            dimensions = order_data.get('dims', {})
            materials = order_data.get('mat', {})
            
            admin_message += (
                f"📐 Размер: {dimensions.get('w', 'N/A')}×{dimensions.get('l', 'N/A')}м\n"
                f"🧱 Материалы: {materials.get('r', 'N/A')}, {materials.get('p', 'N/A')}\n"
                f"💰 Стоимость: {order_data.get('pr', 0):,} руб.\n"
                f"🆔 ID конфигурации: {order_data.get('id', 'N/A')}\n"
            )
        else:
            admin_message += "💬 Клиент хочет обсудить конфигурацию навеса\n"
        
        # Уведомляем админа
        try:
            await context.bot.send_message(chat_id=5216818742, text=admin_message)
        except Exception as e:
            logging.error(f"Ошибка уведомления админа: {e}")
        
        # Ответ пользователю
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
            "В ближайшее время с вами свяжется менеджер для уточнения деталей "
            "и согласования окончательной стоимости.\n\n"
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()
