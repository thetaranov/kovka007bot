import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запуск сервера для uptime
keep_alive()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

# ВАШ ID КАНАЛА (Добавил минус, так как это стандарт для каналов)
ADMIN_CHANNEL_ID = -1003250531931

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# Словари для перевода на русский
ROOF_TYPES = {
    'single': 'Односкатный',
    'gable': 'Двускатный',
    'arched': 'Арочный',
    'triangular': 'Треугольный',
    'semiarched': 'Полуарочный'
}

MATERIALS = {
    'polycarbonate': 'Сотовый поликарбонат',
    'metaltile': 'Металлочерепица',
    'decking': 'Профнастил'
}

PAINTS = {
    'none': 'Грунт-эмаль (Стандарт)',
    'ral': 'Эмаль RAL',
    'polymer': 'Полимерно-порошковая'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет кнопку меню"""
    user = update.effective_user
    logger.info(f"--- START от {user.id} ---")

    # Ссылка на ваше WebApp
    web_app_url = "https://kovka007.vercel.app"
    
    keyboard = [
        [KeyboardButton(text="🏗️ Открыть конструктор", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Нажмите кнопку внизу экрана, чтобы собрать свой идеальный навес:",
        reply_markup=reply_markup
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает данные от сайта и сохраняет их"""
    try:
        data_str = update.effective_message.web_app_data.data
        logger.info(f"📥 Получены данные: {data_str}")
        
        order_data = json.loads(data_str)
        # Сохраняем данные во временную память бота, привязанную к пользователю
        context.user_data['order_data'] = order_data
        
        # Данные для предпросмотра
        rtype = ROOF_TYPES.get(order_data.get('type'), 'Навес')
        price = order_data.get('price', 0)
        
        text = (
            f"✅ <b>Конфигурация получена!</b>\n\n"
            f"🆔 Заказ: <code>{order_data.get('id')}</code>\n"
            f"🏗 Тип: {rtype}\n"
            f"📏 Размер: {order_data.get('width')}x{order_data.get('length')} м\n"
            f"💰 Предварительно: <b>{price:,} руб.</b>\n\n"
            f"📞 <b>Остался 1 шаг:</b> Нажмите кнопку ниже, чтобы отправить номер телефона для связи."
        )
        
        # Кнопка для отправки контакта
        kb = [[KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]]
        
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка при чтении данных заказа.")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финальный этап: берет телефон и данные, отправляет в канал"""
    user = update.effective_user
    contact = update.message.contact
    
    # Достаем сохраненные данные заказа
    order = context.user_data.get('order_data')
    
    if not order:
        await update.message.reply_text("⚠️ Данные заказа устарели. Пожалуйста, откройте конструктор и нажмите 'Оформить' снова.")
        return

    # 1. Формируем список опций
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усиленные фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Боковая зашивка")
    if opts.get('found'): options_list.append("✅ Фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж")
    
    options_str = "\n".join(options_list) if options_list else "Базовая комплектация"
    
    # 2. Собираем красивое сообщение для админа
    admin_report = (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name} {user.last_name or ''}\n"
        f"🔗 <b>Username:</b> @{user.username if user.username else 'Скрыт'}\n"
        f"📞 <b>Телефон:</b> <code>{contact.phone_number}</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>ID Заказа:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {ROOF_TYPES.get(order.get('type'), order.get('type'))}\n"
        f"📏 <b>Габариты:</b> {order.get('width')} x {order.get('length')} м\n"
        f"↕️ <b>Высота:</b> {order.get('height')} м\n"
        f"📐 <b>Уклон:</b> {order.get('slope')}°\n"
        f"🧱 <b>Столб:</b> {order.get('pillar')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏠 <b>Материал:</b> {MATERIALS.get(order.get('material'), order.get('material'))}\n"
        f"🎨 <b>Покраска:</b> {PAINTS.get(order.get('paint'), order.get('paint'))}\n"
        f"🖌 <b>Каркас:</b> {order.get('color_frame')}\n"
        f"🌈 <b>Кровля:</b> {order.get('color_roof')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🛠 <b>Опции:</b>\n{options_str}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>ИТОГО: {order.get('price'):,} руб.</b>"
    )

    # 3. Отправляем в канал
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHANNEL_ID, 
            text=admin_report, 
            parse_mode=ParseMode.HTML
        )
        logger.info("✅ Заказ успешно отправлен в канал")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в канал: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text="⚠️ Заказ принят, но не удалось уведомить менеджера. Пожалуйста, напишите нам напрямую."
        )
        return

    # 4. Ответ клиенту
    await update.message.reply_text(
        "🎉 <b>Спасибо! Ваша заявка принята.</b>\n\n"
        "Мы уже получили расчет вашего навеса.\n"
        "Менеджер свяжется с вами в ближайшее время для уточнения деталей.\n\n"
        "<i>С уважением, команда Kovka007</i>",
        reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    
    # Очищаем память
    context.user_data.clear()

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    logger.info("🚀 Бот запущен! Работает с каналом.")
    application.run_polling()

if __name__ == '__main__':
    main()
