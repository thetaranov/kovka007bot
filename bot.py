import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# Запуск сервера
keep_alive()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# Справочники (должны совпадать с constants.tsx)
ROOF_TYPES = {
    'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный',
    'triangular': 'Треугольный', 'semiarched': 'Полуарочный'
}
MATERIALS = {
    'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'
}
PAINTS = {
    'none': 'Грунт-эмаль (Стандарт)', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет кнопку меню"""
    web_app_url = "https://kovka007.vercel.app"
    keyboard = [[KeyboardButton(text="🏗️ Открыть конструктор", web_app=WebAppInfo(url=web_app_url))]]
    
    await update.message.reply_text(
        "👋 Привет! Нажмите кнопку внизу, чтобы рассчитать навес:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает JSON от сайта"""
    try:
        data_str = update.effective_message.web_app_data.data
        logger.info(f"📥 RAW DATA: {data_str}")
        
        raw_data = json.loads(data_str)
        
        # Нормализация (на случай старой версии сайта)
        order_data = {
            'id': raw_data.get('id'),
            'type': raw_data.get('type') or raw_data.get('t'),
            'width': raw_data.get('width') or raw_data.get('w'),
            'length': raw_data.get('length') or raw_data.get('l'),
            'height': raw_data.get('height') or raw_data.get('h'),
            'slope': raw_data.get('slope') or raw_data.get('s'),
            'price': raw_data.get('price') or raw_data.get('pr') or 0,
            
            # Новые полные поля
            'area_floor': raw_data.get('area_floor', 'Не рассчитано'),
            'area_roof': raw_data.get('area_roof', 'Не рассчитано'),
            'pillar': raw_data.get('pillar', 'Не указано'),
            'material': raw_data.get('material', 'polycarbonate'),
            'paint': raw_data.get('paint', 'none'),
            'color_frame': raw_data.get('color_frame', 'Стандарт'),
            'color_roof': raw_data.get('color_roof', 'Стандарт'),
            'opts': raw_data.get('opts', {})
        }

        context.user_data['order_data'] = order_data
        
        rtype = ROOF_TYPES.get(order_data['type'], order_data['type'])
        
        text = (
            f"✅ <b>Конфигурация получена!</b>\n\n"
            f"🆔 <code>{order_data['id']}</code>\n"
            f"🏗 {rtype}\n"
            f"📏 {order_data['width']}x{order_data['length']} м\n"
            f"💰 <b>{order_data['price']:,} руб.</b>\n\n"
            f"👇 Нажмите кнопку ниже, чтобы отправить телефон."
        )
        
        kb = [[KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]]
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error WebApp: {e}")
        await update.message.reply_text("❌ Ошибка данных.")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    order = context.user_data.get('order_data')
    
    if not order:
        await update.message.reply_text("⚠️ Данные устарели. Соберите навес заново.")
        return

    # Формирование списка опций с галочками
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усиленные фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Боковая зашивка")
    if opts.get('found'): options_list.append("✅ Бетонный фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж под ключ")
    
    options_str = "\n".join(options_list) if options_list else "Базовая комплектация"

    # Формирование сообщения для админа
    admin_report = (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name} (@{user.username or 'нет'})\n"
        f"📞 <b>Телефон:</b> <code>{contact.phone_number}</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>ID:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {ROOF_TYPES.get(order.get('type'), order.get('type'))}\n"
        f"📏 <b>Габариты:</b> {order.get('width')} x {order.get('length')} м\n"
        f"↕️ <b>Высота:</b> {order.get('height')} м\n"
        f"📐 <b>Уклон:</b> {order.get('slope')}°\n"
        f"🧱 <b>Столбы:</b> {order.get('pillar')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📐 <b>Площадь навеса:</b> {order.get('area_floor')} м²\n"
        f"🏠 <b>Площадь кровли:</b> {order.get('area_roof')} м²\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏠 <b>Материал:</b> {MATERIALS.get(order.get('material'), order.get('material'))}\n"
        f"🎨 <b>Покраска:</b> {PAINTS.get(order.get('paint'), order.get('paint'))}\n"
        f"🖌 <b>Цвет каркаса:</b> {order.get('color_frame')}\n"
        f"🌈 <b>Цвет кровли:</b> {order.get('color_roof')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🛠 <b>Опции:</b>\n{options_str}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>ИТОГО: {order.get('price', 0):,} руб.</b>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=admin_report, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Cant send to channel: {e}")
        await update.message.reply_text("⚠️ Заказ принят, но не отправлен в канал.")
        return

    await update.message.reply_text(
        "✅ <b>Заявка принята!</b>\nМенеджер скоро свяжется с вами.",
        reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    context.user_data.clear()

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    logger.info("🚀 Бот запущен (FULL DATA VERSION)")
    application.run_polling()

if __name__ == '__main__':
    main()
