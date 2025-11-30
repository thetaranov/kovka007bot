import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

keep_alive()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931  # Ваш ID канала

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

ROOF_TYPES = {
    'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный',
    'triangular': 'Треугольный', 'semiarched': 'Полуарочный'
}
MATERIALS = {
    'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'
}
PAINTS = {
    'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_app_url = "https://kovka007.vercel.app"
    keyboard = [[KeyboardButton(text="🏗️ Открыть конструктор", web_app=WebAppInfo(url=web_app_url))]]
    await update.message.reply_text(
        "👋 Нажмите кнопку внизу, чтобы рассчитать навес:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data_str = update.effective_message.web_app_data.data
        logger.info(f"📥 RAW DATA: {data_str}")
        
        raw_data = json.loads(data_str)
        
        # --- НОРМАЛИЗАЦИЯ ДАННЫХ (ЧТОБЫ НЕ ПАДАЛО ОТ СТАРОГО ФОРМАТА) ---
        # Если пришли старые ключи (w, l, pr), превращаем их в новые
        order_data = {
            'id': raw_data.get('id'),
            'type': raw_data.get('type') or raw_data.get('t'),
            'width': raw_data.get('width') or raw_data.get('w'),
            'length': raw_data.get('length') or raw_data.get('l'),
            'height': raw_data.get('height') or raw_data.get('h'),
            'slope': raw_data.get('slope') or raw_data.get('s'),
            'price': raw_data.get('price') or raw_data.get('pr') or 0,
            # Остальные поля будут доступны только если сайт обновился
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
            f"✅ <b>Расчет получен!</b>\n\n"
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

    # Формируем опции
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усил. фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Зашивка")
    if opts.get('found'): options_list.append("✅ Фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж")
    options_str = ", ".join(options_list) if options_list else "Нет"

    # Отчет для админа
    # Используем .get(key, 'default') чтобы избежать NoneType ошибок
    admin_report = (
        f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n"
        f"👤 {user.first_name} (@{user.username or 'нет'})\n"
        f"📞 <code>{contact.phone_number}</code>\n"
        f"➖➖➖➖➖\n"
        f"🆔 <code>{order.get('id')}</code>\n"
        f"🏗 {ROOF_TYPES.get(order.get('type'), order.get('type'))}\n"
        f"📏 {order.get('width')}x{order.get('length')} м (Выс: {order.get('height')}м)\n"
        f"🎨 Каркас: {order.get('color_frame')}\n"
        f"🌈 Кровля: {order.get('color_roof')}\n"
        f"🛠 Опции: {options_str}\n"
        f"💰 <b>ИТОГО: {order.get('price', 0):,} руб.</b>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=admin_report, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Cant send to channel: {e}")
        await update.message.reply_text("⚠️ Заказ принят, но не отправлен менеджеру (ошибка канала).")
        return

    await update.message.reply_text(
        "✅ <b>Заявка принята!</b>\nМенеджер скоро свяжется с вами.",
        reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    logger.info("🚀 Бот запущен (FIXED VERSION)")
    application.run_polling()

if __name__ == '__main__':
    main()
