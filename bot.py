import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from keep_alive import keep_alive

keep_alive()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === КОНФИГ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931
INFO_CHANNEL_ID = -1003461235309
INFO_CHANNEL_LINK = "https://t.me/taranov_public"
ADMIN_IDS = [7746957973] 

if not BOT_TOKEN: exit(1)

ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}

# === HELPERS ===
async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания")],
        [KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
    ], resize_keyboard=True)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS: return True
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=user_id)
        if member.status in ['left', 'kicked', 'restricted']: return False
        return True
    except: return True

async def ask_subscription(update: Update):
    kb = [[InlineKeyboardButton("📢 Подписаться", url=INFO_CHANNEL_LINK)], [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]]
    await update.message.reply_text("🚫 Подпишитесь на канал для доступа.", reply_markup=InlineKeyboardMarkup(kb))

async def show_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new=False):
    """Показывает или обновляет статус заказа (удаляет старый, шлет новый)"""
    order = context.user_data.get('order_data')
    if not order:
        await update.message.reply_text("📭 Корзина пуста. Откройте конструктор.", reply_markup=await get_main_keyboard())
        return

    # Удаляем старое сообщение статуса, если оно было
    if 'last_status_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_status_id'])
        except: pass

    rtype = ROOF_TYPES.get(order.get('type'), order.get('type'))
    comment = context.user_data.get('user_comment', 'Нет')
    photo_status = "✅ Фото прикреплено" if context.user_data.get('user_photo') else ""

    text = (
        f"📋 <b>ВАШ ТЕКУЩИЙ ЗАКАЗ</b>\n\n"
        f"🆔 <code>{order.get('id')}</code>\n"
        f"🏗 <b>{rtype}</b> ({order.get('width')}x{order.get('length')} м)\n"
        f"💰 Сумма: <b>{order.get('price', 0):,} руб.</b>\n\n"
        f"📝 <b>Комментарий:</b> {comment}\n"
        f"{photo_status}\n\n"
        f"👇 <i>Чтобы отправить заявку, нажмите кнопку «📞 Отправить телефон» внизу.</i>"
    )

    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=await get_main_keyboard())
    context.user_data['last_status_id'] = msg.message_id

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    await update.message.reply_text("👋 Добро пожаловать! Соберите навес в конструкторе.", reply_markup=await get_main_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "check_sub":
        await query.answer()
        if await check_subscription(update, context):
            await query.message.delete()
            await start(update, context)
        else: await query.message.reply_text("❌ Нет подписки!", ephemeral=True)

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    text = update.message.text.strip()

    # Manual JSON (Desktop)
    if text.startswith('{') and text.endswith('}'):
        try:
            data = json.loads(text)
            await process_json_order(update, context, data)
            return
        except: pass

    if text == "📄 Мой заказ":
        # Удаляем сообщение пользователя для чистоты
        try: await update.message.delete() 
        except: pass
        await show_order_status(update, context)

    elif text == "✏️ Добавить пожелания":
        context.user_data['waiting_for_comment'] = True
        kb = ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True)
        await update.message.reply_text("✍️ Напишите текст или пришлите фото:", reply_markup=kb)

    elif text == "🔙 Отмена":
        context.user_data['waiting_for_comment'] = False
        await show_order_status(update, context)

    elif context.user_data.get('waiting_for_comment'):
        context.user_data['user_comment'] = text
        context.user_data['waiting_for_comment'] = False
        await show_order_status(update, context)

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        await process_json_order(update, context, data)
    except Exception as e: logger.error(e)

async def process_json_order(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_data):
    # Normalization
    order_data = {
        'id': raw_data.get('id'),
        'type': raw_data.get('type') or raw_data.get('t'),
        'width': raw_data.get('width') or raw_data.get('w'),
        'length': raw_data.get('length') or raw_data.get('l'),
        'height': raw_data.get('height') or raw_data.get('h'),
        'height_peak': raw_data.get('height_peak', 0),
        'slope': raw_data.get('slope') or raw_data.get('s'),
        'price': raw_data.get('price') or raw_data.get('pr') or 0,
        'area_floor': raw_data.get('area_floor', '0'),
        'area_roof': raw_data.get('area_roof', '0'),
        'pillar': raw_data.get('pillar', 'Не указано'),
        'material': raw_data.get('material', 'polycarbonate'),
        'paint': raw_data.get('paint', 'none'),
        'color_frame': raw_data.get('color_frame', 'Стандарт'),
        'color_roof': raw_data.get('color_roof', 'Стандарт'),
        'opts': raw_data.get('opts', {})
    }
    context.user_data['order_data'] = order_data
    if 'user_comment' not in context.user_data: context.user_data['user_comment'] = 'Нет'
    
    await show_order_status(update, context, is_new=True)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_comment'):
        context.user_data['user_photo'] = update.message.photo[-1].file_id
        if update.message.caption: context.user_data['user_comment'] = update.message.caption
        context.user_data['waiting_for_comment'] = False
        await show_order_status(update, context)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    
    user = update.effective_user
    contact = update.message.contact
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    photo = context.user_data.get('user_photo')

    if not order:
        await update.message.reply_text("⚠️ Нет заказа.")
        return

    # История
    if 'history' not in context.bot_data: context.bot_data['history'] = []
    context.bot_data['history'].append({'id': order.get('id'), 'price': order.get('price'), 'user': user.first_name})

    # Отчет
    opts = order.get('opts', {})
    opt_list = []
    if opts.get('trusses'): opt_list.append("✅ Усил. фермы")
    if opts.get('gutters'): opt_list.append("✅ Водостоки")
    if opts.get('walls'): opt_list.append("✅ Зашивка")
    if opts.get('found'): opt_list.append("✅ Фундамент")
    if opts.get('install'): opt_list.append("✅ Монтаж")
    opt_str = "\n".join(opt_list) if opt_list else "База"

    report = (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"👤 {user.first_name} (@{user.username or '-'})\n"
        f"📞 <code>{contact.phone_number}</code>\n"
        f"💬 {comment}\n"
        f"➖➖➖➖➖\n"
        f"🆔 <code>{order.get('id')}</code>\n"
        f"🏗 {ROOF_TYPES.get(order.get('type'))}\n"
        f"📏 {order.get('width')}x{order.get('length')} м (H={order.get('height')})\n"
        f"🎨 {order.get('color_frame')} / {order.get('color_roof')}\n"
        f"🛠 <b>Опции:</b>\n{opt_str}\n"
        f"💰 <b>{order.get('price', 0):,} руб.</b>"
    )

    try:
        if photo:
            await context.bot.send_photo(chat_id=ADMIN_CHANNEL_ID, photo=photo, caption=report, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=report, parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(e)

    await update.message.reply_text("✅ <b>Заявка отправлена!</b>\nМенеджер свяжется с вами.", reply_markup=await get_main_keyboard(), parse_mode=ParseMode.HTML)
    context.user_data.clear()

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    h = context.bot_data.get('history', [])
    await update.message.reply_text(f"Заказов: {len(h)}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))
    app.run_polling()

if __name__ == '__main__':
    main()
