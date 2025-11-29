import os
import logging
import json
import base64
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

keep_alive()

# Настройка подробного логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,  # Изменили на DEBUG для максимальной информации
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8')
    ])
logger = logging.getLogger(__name__)

# Проверяем токен
BOT_TOKEN = os.getenv('BOT_TOKEN')
logger.info(f"🔍 Проверяем токен бота...")
logger.info(f"Токен существует: {BOT_TOKEN is not None}")
logger.info(f"Длина токена: {len(BOT_TOKEN) if BOT_TOKEN else 0}")

if not BOT_TOKEN:
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не установлен!")
    logger.error(
        "Добавьте BOT_TOKEN в Secrets (ключ-замок в боковой панели Replit)")
    exit(1)


def decode_base64_url_safe(data):
    """Декодирует base64 в URL-safe формате"""
    try:
        logger.info(f"🔧 Декодируем base64 данные, длина: {len(data)}")
        # Добавляем отладочную информацию
        logger.debug(f"Первые 50 символов данных: {data[:50]}")

        data = data.replace('-', '+').replace('_', '/')
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding

        decoded_bytes = base64.b64decode(data)
        decoded_string = decoded_bytes.decode('utf-8')
        logger.info(f"✅ Данные успешно декодированы")
        logger.debug(f"Декодированная строка: {decoded_string}")
        return decoded_string
    except Exception as e:
        logger.error(f"❌ Ошибка декодирования base64: {e}", exc_info=True)
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        message = update.message

        logger.info("=" * 60)
        logger.info("🚀 ВЫЗВАНА КОМАНДА /start")
        logger.info(f"👤 Пользователь: ID={user.id}, Имя='{user.first_name}'")
        logger.info(f"📝 Текст сообщения: '{message.text}'")
        logger.info(f"🆔 Chat ID: {message.chat_id}")
        logger.info(f"📅 Дата: {message.date}")

        if context.args:
            logger.info(f"📦 Аргументы команды: {context.args}")
            logger.info(f"📦 Количество аргументов: {len(context.args)}")
            logger.info(f"📦 Первый аргумент: '{context.args[0]}'")

            # Проверяем, есть ли заказ
            if context.args[0].startswith('order_'):
                logger.info("🎯 Обнаружен заказ в аргументах!")
                await process_order(update, context, context.args[0][6:])
                return
        else:
            logger.info("📭 Аргументов команды нет")

        # Обычное приветствие (без заказа)
        await send_welcome_message(update, user)

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике start: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз.")


async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        order_data_encoded: str):
    """Обрабатывает данные заказа"""
    try:
        logger.info(
            f"📦 Обрабатываем заказ, длина данных: {len(order_data_encoded)}")

        order_data_json = decode_base64_url_safe(order_data_encoded)

        if not order_data_json:
            logger.error("❌ Не удалось декодировать данные заказа")
            await update.message.reply_text(
                "❌ Ошибка при обработке данных заказа.")
            return

        logger.info(f"📋 Парсим JSON данные...")
        order_data = json.loads(order_data_json)

        # Сохраняем данные заказа
        context.user_data['order_data'] = order_data
        logger.info("💾 Данные заказа сохранены в user_data")

        # Отправляем сообщение с деталями заказа
        await send_order_details(update, context, order_data)

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        await update.message.reply_text("❌ Ошибка в формате данных заказа.")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка обработки заказа: {e}",
                     exc_info=True)
        await update.message.reply_text(
            "❌ Произошла непредвиденная ошибка при обработке заказа.")


async def send_order_details(update: Update,
                             context: ContextTypes.DEFAULT_TYPE,
                             order_data: dict):
    """Отправляет детали заказа и запрашивает контакт"""
    try:
        user = update.effective_user

        # Маппинг для читаемости
        roof_type_map = {
            'single': 'Односкатная',
            'gable': 'Двускатная',
            'arched': 'Арочная',
            'triangular': 'Треугольная',
            'semiarched': 'Полуарочная'
        }

        material_map = {
            'polycarbonate': 'Поликарбонат',
            'metaltile': 'Металлочерепица',
            'decking': 'Профнастил'
        }

        paint_map = {
            'none': 'Без покраски',
            'ral': 'Порошковая покраска RAL',
            'zinc': 'Оцинковка'
        }

        # Извлекаем данные
        dims = order_data.get('dims', {})
        mat = order_data.get('mat', {})
        col = order_data.get('col', {})
        opt = order_data.get('opt', {})

        roof_type = roof_type_map.get(order_data.get('t', ''),
                                      order_data.get('t', 'N/A'))
        roof_material = material_map.get(mat.get('r', ''), mat.get('r', 'N/A'))
        paint_type = paint_map.get(mat.get('pt', ''), mat.get('pt', 'N/A'))
        frame_color = col.get('f', 'Не указан')
        roof_color = col.get('r', 'Не указан')

        # Формируем опции
        options = []
        if opt.get('tr'): options.append("✅ Усиленные фермы")
        if opt.get('gu'): options.append("✅ Водосточная система")
        if opt.get('sw'): options.append("✅ Боковые стенки")
        if opt.get('fd'): options.append("✅ Фундамент")
        if opt.get('in'): options.append("✅ Монтаж")

        options_text = "\n".join(
            options) if options else "❌ Базовая комплектация"

        message_text = (
            f"🎉 Отлично, {user.first_name}! Ваш навес сконфигурирован!\n\n"
            f"📐 Параметры навеса:\n"
            f"• Тип: {roof_type}\n"
            f"• Размер: {dims.get('w', 'N/A')}×{dims.get('l', 'N/A')}м\n"
            f"• Высота: {dims.get('h', 'N/A')}м\n"
            f"• Уклон: {dims.get('sl', 'N/A')}°\n"
            f"• Площадь: {order_data.get('area', 'N/A')}м²\n\n"
            f"🧱 Материалы:\n"
            f"• Кровля: {roof_material}\n"
            f"• Столбы: {mat.get('p', 'N/A')}\n"
            f"• Покраска: {paint_type}\n"
            f"• Цвет каркаса: {frame_color}\n"
            f"• Цвет кровли: {roof_color}\n\n"
            f"⚙️ Дополнительные опции:\n{options_text}\n\n"
            f"💰 Предварительная стоимость: {order_data.get('pr', 0):,} руб.\n\n"
            f"📞 Для оформления заказа поделитесь номером телефона:")

        # Создаем клавиатуру с кнопкой для отправки контакта
        keyboard = [[
            KeyboardButton("📞 Отправить номер телефона", request_contact=True)
        ]]
        reply_markup = ReplyKeyboardMarkup(keyboard,
                                           resize_keyboard=True,
                                           one_time_keyboard=True)

        await update.message.reply_text(message_text,
                                        reply_markup=reply_markup)
        logger.info("✅ Сообщение с деталями заказа отправлено пользователю")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке деталей заказа: {e}",
                     exc_info=True)
        await update.message.reply_text("❌ Ошибка при формировании заказа.")


async def send_welcome_message(update: Update, user):
    """Отправляет приветственное сообщение"""
    try:
        logger.info("📝 Отправляем приветственное сообщение")

        keyboard = [[
            InlineKeyboardButton("🏗️ Создать навес",
                                 url="https://kovka007.vercel.app")
        ],
                    [
                        InlineKeyboardButton("📞 Связаться с менеджером",
                                             url="https://t.me/thetaranov")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = (f"Привет, {user.first_name}! 👋\n\n"
                        "Я бот для заказов навесов от Ковка007.\n\n"
                        "С моей помощью вы можете:\n"
                        "• 🏗️ Создать навес в нашем конструкторе\n"
                        "• 📐 Рассчитать стоимость\n"
                        "• 📞 Оформить заказ\n\n"
                        "Нажмите кнопку ниже чтобы начать создание навеса:")

        await update.message.reply_text(welcome_text,
                                        reply_markup=reply_markup)
        logger.info("✅ Приветственное сообщение отправлено")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке приветствия: {e}", exc_info=True)


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает отправку контакта"""
    try:
        user = update.effective_user
        contact = update.message.contact

        logger.info("=" * 50)
        logger.info(f"📞 ПОЛУЧЕН КОНТАКТ ОТ ПОЛЬЗОВАТЕЛЯ")
        logger.info(f"👤 Пользователь: ID={user.id}, Имя='{user.first_name}'")
        logger.info(f"📱 Контакт: +{contact.phone_number}")

        order_data = context.user_data.get('order_data', {})

        # Отправляем уведомление админу
        await send_admin_notification(context, user, contact, order_data)

        # Отправляем подтверждение пользователю
        await update.message.reply_text(
            "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
            "В ближайшее время с вами свяжется наш менеджер для уточнения деталей.\n\n"
            "Спасибо, что выбрали Ковка007! 💙",
            reply_markup=ReplyKeyboardMarkup(
                [[]], resize_keyboard=True)  # Убираем клавиатуру
        )
        logger.info("✅ Подтверждение отправлено пользователю")

        # Очищаем данные заказа
        if 'order_data' in context.user_data:
            del context.user_data['order_data']
            logger.info("🗑️ Данные заказа очищены")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки контакта: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке контакта.")


async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, user,
                                  contact, order_data: dict):
    """Отправляет уведомление админу"""
    try:
        ADMIN_CHAT_ID = 5216818742  # Замените на ваш chat_id

        admin_message = f"🚨 НОВЫЙ ЗАКАЗ ОТ КЛИЕНТА!\n\n"
        admin_message += f"👤 Клиент: {user.first_name}"
        if user.last_name:
            admin_message += f" {user.last_name}"
        if user.username:
            admin_message += f" (@{user.username})"
        admin_message += f"\n📞 Телефон: +{contact.phone_number}\n"
        admin_message += f"🆔 User ID: {user.id}\n\n"

        if order_data:
            dims = order_data.get('dims', {})
            mat = order_data.get('mat', {})
            col = order_data.get('col', {})
            opt = order_data.get('opt', {})

            roof_type_map = {
                'single': 'Односкатная',
                'gable': 'Двускатная',
                'arched': 'Арочная',
                'triangular': 'Треугольная',
                'semiarched': 'Полуарочная'
            }

            material_map = {
                'polycarbonate': 'Поликарбонат',
                'metaltile': 'Металлочерепица',
                'decking': 'Профнастил'
            }

            roof_type = roof_type_map.get(order_data.get('t', ''),
                                          order_data.get('t', 'N/A'))

            admin_message += f"📐 КОНФИГУРАЦИЯ НАВЕСА:\n"
            admin_message += f"• Тип: {roof_type}\n"
            admin_message += f"• Размер: {dims.get('w', 'N/A')}×{dims.get('l', 'N/A')}м\n"
            admin_message += f"• Высота: {dims.get('h', 'N/A')}м\n"
            admin_message += f"• Уклон: {dims.get('sl', 'N/A')}°\n"
            admin_message += f"• Площадь: {order_data.get('area', 'N/A')}м²\n\n"

            admin_message += f"🧱 МАТЕРИАЛЫ:\n"
            admin_message += f"• Кровля: {material_map.get(mat.get('r', ''), mat.get('r', 'N/A'))}\n"
            admin_message += f"• Столбы: {mat.get('p', 'N/A')}\n"
            admin_message += f"• Цвет каркаса: {col.get('f', 'Не указан')}\n"
            admin_message += f"• Цвет кровли: {col.get('r', 'Не указан')}\n\n"

            # Опции
            options = []
            if opt.get('tr'): options.append("• Усиленные фермы")
            if opt.get('gu'): options.append("• Водосточная система")
            if opt.get('sw'): options.append("• Боковые стенки")
            if opt.get('fd'): options.append("• Фундамент")
            if opt.get('in'): options.append("• Монтаж")

            if options:
                admin_message += f"⚙️ ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ:\n" + "\n".join(
                    options) + "\n\n"

            admin_message += f"💰 СТОИМОСТЬ: {order_data.get('pr', 0):,} руб.\n"
            admin_message += f"🆔 ID КОНФИГУРАЦИИ: {order_data.get('id', 'N/A')}\n"

            logger.info(f"📤 Отправляем уведомление админу о заказе")
        else:
            admin_message += "💬 Клиент хочет обсудить конфигурацию навеса\n"
            logger.info(
                "📤 Отправляем уведомление админу о запросе на консультацию")

        await context.bot.send_message(chat_id=ADMIN_CHAT_ID,
                                       text=admin_message)
        logger.info(
            f"✅ Уведомление отправлено админу (chat_id: {ADMIN_CHAT_ID})")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления админу: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    try:
        user = update.effective_user
        text = update.message.text

        logger.info(f"💬 Текстовое сообщение от {user.id}: '{text}'")

        # Если есть данные заказа, предлагаем отправить контакт
        if context.user_data.get('order_data'):
            keyboard = [[
                KeyboardButton("📞 Отправить номер телефона",
                               request_contact=True)
            ]]
            reply_markup = ReplyKeyboardMarkup(keyboard,
                                               resize_keyboard=True,
                                               one_time_keyboard=True)

            await update.message.reply_text(
                "Для оформления заказа нажмите кнопку ниже чтобы поделиться номером телефона:",
                reply_markup=reply_markup)
        else:
            await update.message.reply_text(
                "Нажмите /start чтобы начать работу с ботом или создать заказ на навес."
            )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"🔥 Ошибка в боте: {context.error}", exc_info=True)

    if update and update.effective_user:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз или свяжитесь с менеджером: @thetaranov"
            )
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение об ошибке: {e}")


def main():
    """Основная функция запуска бота"""
    try:
        logger.info("🤖 ЗАПУСКАЕМ БОТА...")
        logger.info(f"🔑 Токен: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}")

        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.CONTACT,
                                               handle_contact))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Обработчик ошибок
        application.add_error_handler(error_handler)

        logger.info("🔄 Запускаем polling...")

        # Запускаем бота
        application.run_polling(poll_interval=1.0,
                                timeout=10,
                                drop_pending_updates=True)

    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ БОТА: {e}",
                     exc_info=True)


if __name__ == '__main__':
    main()
