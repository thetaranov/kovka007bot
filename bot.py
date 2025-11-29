import os
import logging
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

keep_alive()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

def decode_base64_url_safe(data):
    """Декодирует base64 в URL-safe формате"""
    try:
        logger.info(f"🔧 Декодируем base64 данные, длина: {len(data)}")
        data = data.replace('-', '+').replace('_', '/')
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding
        
        decoded_bytes = base64.b64decode(data)
        decoded_string = decoded_bytes.decode('utf-8')
        logger.info(f"✅ Данные успешно декодированы")
        return decoded_string
    except Exception as e:
        logger.error(f"❌ Ошибка декодирования base64: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    logger.info("=" * 50)
    logger.info(f"🚀 НОВЫЙ ЗАПРОС /start")
    logger.info(f"👤 Пользователь: ID={user.id}, Имя='{user.first_name}', Фамилия='{user.last_name}', Username=@{user.username}")
    logger.info(f"💬 Текст сообщения: '{update.message.text}'")
    
    if context.args:
        logger.info(f"📦 Аргументы команды: {context.args}")
        logger.info(f"📦 Первый аргумент: '{context.args[0]}'")
        logger.info(f"📦 Всего аргументов: {len(context.args)}")
    else:
        logger.info("📭 Аргументов команды нет")
    
    # Проверяем, есть ли параметры в команде /start (Deep Link из сайта)
    if context.args and context.args[0].startswith('order_'):
        try:
            order_data_encoded = context.args[0][6:]
            
            logger.info(f"🎯 Обнаружен заказ, длина данных: {len(order_data_encoded)}")
            logger.info(f"📄 Закодированные данные: {order_data_encoded[:50]}...")
            
            order_data_json = decode_base64_url_safe(order_data_encoded)
            
            if order_data_json:
                logger.info(f"📋 Декодированный JSON: {order_data_json}")
                order_data = json.loads(order_data_json)
                
                # Логируем все поля заказа
                logger.info("📊 ДЕТАЛИ ЗАКАЗА:")
                logger.info(f"   🆔 ID: {order_data.get('id')}")
                logger.info(f"   🏠 Тип крыши: {order_data.get('t')}")
                
                dims = order_data.get('dims', {})
                logger.info(f"   📐 Размеры: {dims.get('w')}x{dims.get('l')}x{dims.get('h')}м")
                logger.info(f"   📐 Уклон: {dims.get('sl')}°")
                logger.info(f"   📏 Площадь: {order_data.get('area')}м²")
                
                mat = order_data.get('mat', {})
                logger.info(f"   🧱 Материалы: кровля={mat.get('r')}, столбы={mat.get('p')}, покраска={mat.get('pt')}")
                
                col = order_data.get('col', {})
                logger.info(f"   🎨 Цвета: каркас='{col.get('f')}', кровля='{col.get('r')}'")
                
                opt = order_data.get('opt', {})
                logger.info(f"   ⚙️ Опции: фермы={opt.get('tr')}, водостоки={opt.get('gu')}, стены={opt.get('sw')}, фундамент={opt.get('fd')}, монтаж={opt.get('in')}")
                
                logger.info(f"   💰 Стоимость: {order_data.get('pr'):,} руб.")
                
                # Сохраняем данные заказа
                context.user_data['order_data'] = order_data
                logger.info("💾 Данные заказа сохранены в user_data")
                
                # Запрашиваем контакт
                keyboard = [
                    [KeyboardButton("📞 Отправить номер телефона", request_contact=True)]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                
                # Форматируем сообщение с данными заказа
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
                
                roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
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
                
                options_text = "\n".join(options) if options else "❌ Базовая комплектация"
                
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
                    f"📞 Для оформления заказа поделитесь номером телефона:"
                )
                
                await update.message.reply_text(message_text, reply_markup=reply_markup)
                logger.info("✅ Сообщение с деталями заказа отправлено пользователю")
                return
            else:
                logger.error("❌ Не удалось декодировать данные заказа")
                await update.message.reply_text("❌ Ошибка при обработке данных заказа. Пожалуйста, попробуйте еще раз.")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            await update.message.reply_text("❌ Ошибка в формате данных заказа.")
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка обработки заказа: {e}", exc_info=True)
            await update.message.reply_text("❌ Произошла непредвиденная ошибка при обработке заказа.")
    
    # Если параметров нет - обычное приветствие
    logger.info("📝 Отправка обычного приветственного сообщения")
    
    keyboard = [
        [InlineKeyboardButton("🏗️ Создать навес", url="https://kovka007.vercel.app")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/thetaranov")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для заказов навесов от Ковка007.\n\n"
        "Нажмите кнопку ниже чтобы создать навес в нашем конструкторе:",
        reply_markup=reply_markup
    )
    
    logger.info("✅ Приветственное сообщение отправлено")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    
    logger.info("=" * 50)
    logger.info(f"📞 ПОЛУЧЕН КОНТАКТ ОТ ПОЛЬЗОВАТЕЛЯ")
    logger.info(f"👤 Пользователь: ID={user.id}, Имя='{user.first_name}'")
    logger.info(f"📱 Контакт: +{contact.phone_number}, Имя='{contact.first_name}'")
    
    order_data = context.user_data.get('order_data', {})
    
    # Формируем сообщение для админа
    admin_message = f"🚨 НОВЫЙ ЗАКАЗ ОТ КЛИЕНТА!\n\n"
    admin_message += f"👤 Клиент: {user.first_name}"
    if user.last_name:
        admin_message += f" {user.last_name}"
    if user.username:
        admin_message += f" (@{user.username})"
    admin_message += f"\n📞 Телефон: +{contact.phone_number}\n"
    admin_message += f"🆔 User ID: {user.id}\n\n"
    
    if order_data:
        logger.info("📋 Отправляем заказ с конфигурацией")
        
        dims = order_data.get('dims', {})
        mat = order_data.get('mat', {})
        col = order_data.get('col', {})
        opt = order_data.get('opt', {})
        
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
        
        roof_type = roof_type_map.get(order_data.get('t', ''), order_data.get('t', 'N/A'))
        
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
            admin_message += f"⚙️ ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ:\n" + "\n".join(options) + "\n\n"
        
        admin_message += f"💰 СТОИМОСТЬ: {order_data.get('pr', 0):,} руб.\n"
        admin_message += f"🆔 ID КОНФИГУРАЦИИ: {order_data.get('id', 'N/A')}\n"
        
        logger.info(f"📤 Отправляем уведомление админу о заказе со стоимостью {order_data.get('pr', 0):,} руб.")
    else:
        admin_message += "💬 Клиент хочет обсудить конфигурацию навеса\n"
        logger.info("📤 Отправляем уведомление админу о запросе на консультацию")
    
    try:
        # Отправляем сообщение админу (замените CHAT_ID на ваш)
        ADMIN_CHAT_ID = 5216818742  # Замените на ваш chat_id
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)
        logger.info(f"✅ Уведомление отправлено админу (chat_id: {ADMIN_CHAT_ID})")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления админу: {e}")
    
    # Отправляем подтверждение пользователю
    await update.message.reply_text(
        "✅ Отлично! Ваш заказ принят! 🏗️\n\n"
        "В ближайшее время с вами свяжется наш менеджер для уточнения деталей и согласования заказа.\n\n"
        "📞 Ожидайте звонка с номера +7 (XXX) XXX-XX-XX\n\n"
        "Спасибо, что выбрали Ковка007! 💙",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)  # Убираем клавиатуру
    )
    logger.info("✅ Подтверждение отправлено пользователю")
    
    # Очищаем данные заказа
    if 'order_data' in context.user_data:
        del context.user_data['order_data']
        logger.info("🗑️ Данные заказа очищены из user_data")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    logger.info(f"💬 Текстовое сообщение от пользователя {user.id}: '{text}'")
    
    # Если есть данные заказа, предлагаем отправить контакт
    if context.user_data.get('order_data'):
        keyboard = [
            [KeyboardButton("📞 Отправить номер телефона", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "Для оформления заказа нажмите кнопку ниже чтобы поделиться номером телефона:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Нажмите /start чтобы начать работу с ботом или создать заказ на навес."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"🔥 Ошибка в боте: {context.error}", exc_info=True)
    
    if update and update.effective_user:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз или свяжитесь с менеджером: @thetaranov"
            )
        except:
            pass

def main():
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("🤖 Бот запускается...")
        logger.info(f"🔑 Токен: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запуске бота: {e}", exc_info=True)

if __name__ == '__main__':
    main()
