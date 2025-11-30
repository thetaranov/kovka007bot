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

def decode_base64_simple(data):
    """Упрощенное декодирование base64"""
    try:
        logger.info(f"Декодируем base64, длина: {len(data)}")
        data = data.replace('-', '+').replace('_', '/')
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding
        
        decoded_bytes = base64.b64decode(data)
        decoded_string = decoded_bytes.decode('utf-8')
        logger.info(f"Успешно декодировано: {decoded_string}")
        return decoded_string
    except Exception as e:
        logger.error(f"Ошибка декодирования: {e}")
        return None

def start(update, context):
    user = update.effective_user
    logger.info(f"=== КОМАНДА START ===")
    logger.info(f"Пользователь: {user.first_name} (ID: {user.id})")
    logger.info(f"Полный текст: {update.message.text}")
    
    if context.args:
        logger.info(f"Аргументы: {context.args}")
        logger.info(f"Первый аргумент: '{context.args[0]}'")
        
        if context.args[0].startswith('order_'):
            order_data_encoded = context.args[0][6:]
            logger.info(f"Найден заказ через Deep Link! Длина данных: {len(order_data_encoded)}")
            
            order_data_json = decode_base64_simple(order_data_encoded)
            
            if order_data_json:
                try:
                    order_data = json.loads(order_data_json)
                    logger.info("✅ Успешно распарсены данные заказа:")
                    logger.info(f"ID: {order_data.get('id')}")
                    process_order_data(update, context, order_data)
                    return
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка JSON: {e}")
                    update.message.reply_text("❌ Ошибка в данных заказа")
                except Exception as e:
                    logger.error(f"Ошибка обработки: {e}")
                    update.message.reply_text("❌ Ошибка обработки заказа")
            else:
                update.message.reply_text("❌ Не удалось расшифровать данные заказа")
    else:
        logger.info("Нет аргументов в команде /start")
    
    # Обычное приветствие
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов. Нажмите кнопку ниже чтобы создать навес в конструкторе:",
        reply_markup=reply_markup
    )

def handle_webapp_data(update, context):
    """Обрабатывает данные из WebApp"""
    try:
        user = update.effective_user
        text = update.message.text
        
        logger.info(f"=== ДАННЫЕ ИЗ WEBAPP ===")
        logger.info(f"Пользователь: {user.first_name} (ID: {user.id})")
        logger.info(f"Полученные данные: {text}")
        
        # Пытаемся распарсить JSON
        order_data = json.loads(text)
        
        if 'id' in order_data and order_data['id'].startswith('CFG-'):
            logger.info("✅ Получены валидные данные заказа из WebApp")
            process_order_data(update, context, order_data)
        else:
            logger.warning("❌ Получены невалидные данные из WebApp")
            update.message.reply_text("❌ Получены неверные данные заказа")
            
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON из WebApp: {e}")
        # Если это не JSON, возможно это обычное сообщение
        handle_message(update, context)
    except Exception as e:
        logger.error(f"❌ Ошибка обработки данных WebApp: {e}")
        update.message.reply_text("❌ Ошибка обработки заказа")

def process_order_data(update, context, order_data):
    """Обрабатывает данные заказа"""
    logger.info(f"📦 Обрабатываем заказ {order_data.get('id')}")
    
    user = update.effective_user
    
    # Сохраняем данные
    context.user_data['order_data'] = order_data
    
    # Форматируем сообщение
    roof_type_map = {
        'single': 'Односкатная',
        'gable': 'Двускатная', 
        'arched': 'Арочная',
        'triangular': 'Треугольная',
        'semiarched': 'Полуарочная'
    }
    
    roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
    dims = order_data.get('dims', {})
    
    message_text = (
        f"🎉 Заказ {order_data.get('id')} получен!\n\n"
        f"📐 Параметры навеса:\n"
        f"• Тип: {roof_type}\n"
        f"• Размер: {dims.get('w', 'N/A')}×{dims.get('l', 'N/A')}м\n"
        f"• Высота: {dims.get('h', 'N/A')}м\n"
        f"• Уклон: {dims.get('sl', 'N/A')}°\n"
        f"💰 Стоимость: {order_data.get('pr', 0):,} руб.\n\n"
        f"📞 Для оформления заказа поделитесь номером телефона:"
    )
    
    keyboard = [[KeyboardButton("📞 Отправить номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    update.message.reply_text(message_text, reply_markup=reply_markup)
    logger.info("✅ Сообщение с деталями заказа отправлено")

def handle_contact(update, context):
    contact = update.message.contact
    user = update.effective_user
    order_data = context.user_data.get('order_data', {})
    
    logger.info(f"=== ПОЛУЧЕН КОНТАКТ ===")
    logger.info(f"Телефон: {contact.phone_number}")
    logger.info(f"Данные заказа: {order_data}")

    # Формируем сообщение для админа
    admin_message = f"🚨 НОВЫЙ ЗАКАЗ!\n\n👤 Клиент: {user.first_name}\n📞 Телефон: {contact.phone_number}\n"
    
    if order_data:
        dims = order_data.get('dims', {})
        admin_message += (
            f"📐 Конфигурация:\n"
            f"• Размер: {dims.get('w', 'N/A')}×{dims.get('l', 'N/A')}м\n"
            f"• Высота: {dims.get('h', 'N/A')}м\n"
            f"• Стоимость: {order_data.get('pr', 0):,} руб.\n"
            f"• ID: {order_data.get('id', 'N/A')}\n"
        )
    else:
        admin_message += "💬 Клиент хочет обсудить конфигурацию\n"

    try:
        # Отправляем админу
        context.bot.send_message(chat_id=5216818742, text=admin_message)
        logger.info("✅ Уведомление отправлено админу")
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")

    update.message.reply_text(
        "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
        "В ближайшее время с вами свяжется менеджер для уточнения деталей.\n\n"
        "Спасибо, что выбрали нас!",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
    )

    if 'order_data' in context.user_data:
        del context.user_data['order_data']

def handle_message(update, context):
    text = update.message.text
    
    # Пытаемся определить, это данные из WebApp или обычное сообщение
    if text.strip().startswith('{') and text.strip().endswith('}'):
        logger.info("🔍 Обнаружены данные в формате JSON, пробуем обработать как WebApp данные")
        handle_webapp_data(update, context)
    else:
        update.message.reply_text("Нажмите /start чтобы начать работу с ботом.")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.contact, handle_contact))
    dp.add_handler(MessageHandler(Filters.text, handle_message))
    
    logger.info("🤖 Бот запускается...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
