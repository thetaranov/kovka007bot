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
                    process_order_data(update, context, order_data, "Deep Link")
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
    keyboard = [[
        InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")
    ], [
        InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов. Нажмите кнопку ниже чтобы создать навес в конструкторе:",
        reply_markup=reply_markup)

def handle_all_messages(update, context):
    """Обработчик ВСЕХ сообщений для отладки"""
    user = update.effective_user
    text = update.message.text if update.message.text else "НЕТ ТЕКСТА"
    
    logger.info("=" * 50)
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ")
    logger.info(f"👤 От: {user.first_name} (ID: {user.id})")
    logger.info(f"💬 Текст: {text}")
    logger.info(f"📏 Длина текста: {len(text)}")
    
    # Проверяем, является ли сообщение контактом
    if update.message.contact:
        logger.info("📞 Это контакт!")
        handle_contact(update, context)
        return
    
    # Проверяем, является ли сообщение командой /start
    if text.startswith('/start'):
        start(update, context)
        return
    
    # Проверяем, является ли сообщение JSON (данные из WebApp)
    if text.strip().startswith('{') and text.strip().endswith('}'):
        logger.info("🔍 Обнаружен JSON, пробуем распарсить как данные из WebApp")
        try:
            order_data = json.loads(text)
            if 'id' in order_data and order_data['id'].startswith('CFG-'):
                logger.info("✅ Это валидные данные заказа из WebApp!")
                process_order_data(update, context, order_data, "WebApp")
                return
            else:
                logger.warning("⚠️ JSON есть, но не похож на заказ")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
    
    # Обычное текстовое сообщение
    handle_text_message(update, context)

def process_order_data(update, context, order_data, source):
    """Обрабатывает данные заказа из любого источника"""
    logger.info(f"📦 Обрабатываем заказ из {source}")
    logger.info(f"Данные: {order_data}")

    user = update.effective_user

    # Сохраняем данные
    context.user_data['order_data'] = order_data
    logger.info("💾 Данные заказа сохранены в user_data")

    # Форматируем сообщение
    roof_type_map = {
        'single': 'Односкатная',
        'gable': 'Двускатная',
        'arched': 'Арочная',
        'triangular': 'Треугольная',
        'semiarched': 'Полуарочная'
    }

    roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))

    message_text = (
        f"🎉 Отлично, {user.first_name}!\n\n"
        f"📐 Ваш навес:\n"
        f"• Тип: {roof_type}\n"
        f"• Размер: {order_data.get('w', 'N/A')}×{order_data.get('l', 'N/A')}м\n"
        f"• Высота: {order_data.get('h', 'N/A')}м\n"
        f"• Уклон: {order_data.get('s', 'N/A')}°\n"
        f"💰 Стоимость: {order_data.get('pr', 0):,} руб.\n\n"
        f"📞 Для оформления заказа поделитесь номером телефона:")

    keyboard = [[
        KeyboardButton("📞 Отправить номер телефона", request_contact=True)
    ]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    update.message.reply_text(message_text, reply_markup=reply_markup)
    logger.info("✅ Сообщение с деталями заказа отправлено пользователю")

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
        roof_type_map = {
            'single': 'Односкатная',
            'gable': 'Двускатная',
            'arched': 'Арочная',
            'triangular': 'Треугольная',
            'semiarched': 'Полуарочная'
        }

        roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))

        admin_message += (
            f"📐 Конфигурация:\n"
            f"• Тип: {roof_type}\n"
            f"• Размер: {order_data.get('w', 'N/A')}×{order_data.get('l', 'N/A')}м\n"
            f"• Высота: {order_data.get('h', 'N/A')}м\n"
            f"• Стоимость: {order_data.get('pr', 0):,} руб.\n"
            f"• ID: {order_data.get('id', 'N/A')}\n")
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
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))

    if 'order_data' in context.user_data:
        del context.user_data['order_data']

def handle_text_message(update, context):
    """Обработчик обычных текстовых сообщений"""
    text = update.message.text
    user = update.effective_user
    
    logger.info(f"💬 Обычное сообщение: '{text}'")
    
    # Если есть данные заказа, предлагаем отправить контакт
    if context.user_data.get('order_data'):
        keyboard = [[
            KeyboardButton("📞 Отправить номер телефона", request_contact=True)
        ]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        update.message.reply_text(
            "Для оформления заказа нажмите кнопку ниже чтобы поделиться номером телефона:",
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            "Нажмите /start чтобы начать работу с ботом или создать заказ на навес."
        )

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Используем один обработчик для всех сообщений
    dp.add_handler(MessageHandler(Filters.all, handle_all_messages))
    
    logger.info("🤖 Бот запускается с улучшенной обработкой сообщений...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
