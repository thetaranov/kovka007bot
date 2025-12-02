import os
import logging
import json
import io
import csv
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PicklePersistence
from keep_alive import keep_alive

# Запуск сервера
keep_alive()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931
INFO_CHANNEL_ID = -1003461235309
INFO_CHANNEL_LINK = "https://t.me/taranov_public"
ADMIN_IDS = [7746957973, 5216818742] 

if not BOT_TOKEN: exit(1)

# === СПРАВОЧНИКИ ===
ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}
STATUS_MAP = {1: "🟡 Ожидает", 2: "🔵 В работе", 3: "🟢 Сдан"}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания/фото")],
        [KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
    ], resize_keyboard=True)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return True
    if update.effective_user.id in ADMIN_IDS: return True
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=update.effective_user.id)
        if member.status in ['left', 'kicked', 'restricted']: return False
        return True
    except: return True

async def ask_subscription(update: Update):
    kb = [[InlineKeyboardButton("📢 Подписаться", url=INFO_CHANNEL_LINK)], [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]]
    await update.message.reply_text("🚫 <b>Доступ ограничен!</b>\nПодпишитесь на канал.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

def format_order_message(order, user_name, user_link, phone, comment, status_code=1, for_admin=True):
    """Форматирует сообщение для клиента или админа"""
    rtype = ROOF_TYPES.get(order.get('type'), order.get('type'))
    mat = MATERIALS.get(order.get('material'), order.get('material'))
    paint = PAINTS.get(order.get('paint'), order.get('paint'))
    
    opts = order.get('opts', {})
    opt_list = []
    if opts.get('trusses'): opt_list.append("✅ Усил. фермы")
    if opts.get('gutters'): opt_list.append("✅ Водостоки")
    if opts.get('walls'): opt_list.append("✅ Зашивка")
    if opts.get('found'): opt_list.append("✅ Фундамент")
    if opts.get('install'): opt_list.append("✅ Монтаж")
    opt_str = "\n".join(opt_list) if opt_list else "Базовая"

    header = f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\nСтатус: {STATUS_MAP.get(status_code, '?')}" if for_admin else "📋 <b>ВАШ ЗАКАЗ:</b>"
    
    user_info = (
        f"👤 <b>Клиент:</b> {user_name}\n"
        f"🔗 <b>Link:</b> {user_link}\n"
        f"📞 <b>Phone:</b> <code>{phone}</code>\n"
        f"💬 <b>Пожелания:</b> {comment}\n"
    ) if for_admin else ""
    
    return (
        f"{header}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"{user_info if for_admin else ''}"
        f"🆔 <b>ID:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {rtype}\n"
        f"📏 <b>Длина:</b> {order.get('length')} м\n"
        f"📏 <b>Ширина:</b> {order.get('width')} м\n"
        f"↕️ <b>Высота (столб):</b> {order.get('height')} м\n"
        f"🏔 <b>Высота (общ):</b> ~{order.get('height_peak')} м\n"
        f"📐 <b>Уклон:</b> {order.get('slope')}°\n"
        f"🧱 <b>Сечение:</b> {order.get('pillar')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔲 <b>S пола:</b> {order.get('area_floor')} м²\n"
        f"🏠 <b>S кровли:</b> {order.get('area_roof')} м²\n"
        f"🏠 <b>Материал:</b> {mat}\n"
        f"🎨 <b>Покраска:</b> {paint}\n"
        f"🖌 <b>Цвет:</b> {order.get('color_frame')} / {order.get('color_roof')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🛠 <b>Опции:</b>\n{opt_str}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>ИТОГО: {order.get('price', 0):,} руб.</b>"
    )

# === ХЕНДЛЕРЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        "Я помогу вам рассчитать стоимость навеса и оформить заявку. "
        "Нажмите кнопку <b>«🏗 Открыть конструктор»</b> внизу, чтобы начать.",
        reply_markup=await get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.data == "check_sub":
        if await check_subscription(update, context):
            await update.callback_query.message.delete()
            await start(update, context)
        else: await update.callback_query.answer("Нет подписки!", show_alert=True)

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает данные, показывает клиенту заказ и инструкцию"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        context.user_data['order_data'] = data
        if 'user_comment' not in context.user_data: context.user_data['user_comment'] = 'Нет'
        if 'user_photos' not in context.user_data: context.user_data['user_photos'] = []
        
        user = update.effective_user
        order_details = format_order_message(data, user.first_name, "", "", "", 1, for_admin=False)
        
        await update.message.reply_text(order_details, parse_mode=ParseMode.HTML)
        await update.message.reply_text(
            "✅ <b>Расчет готов!</b>\n\n"
            "Вы можете <b>добавить комментарий или фото</b> через кнопку «✏️ Добавить пожелания».\n\n"
            "👇 <b>Для оформления заявки</b> нажмите кнопку «📞 Отправить телефон» внизу.",
            reply_markup=await get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"WebApp Error: {e}")

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    text = update.message.text.strip()

    if update.effective_user.id in ADMIN_IDS and text in ['1', '2', '3']:
        # ... админ-логика смены статуса ...
        pass

    if text == "📄 Мой заказ":
        # ... код для "Мой заказ" ...
        pass

    elif text == "✏️ Добавить пожелания/фото":
        context.user_data['wait_comment'] = True
        kb = ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True)
        await update.message.reply_text("✍️ Напишите текст и/или отправьте до 10 фото (одним альбомом):", reply_markup=kb)

    elif text == "🔙 Отмена":
        context.user_data['wait_comment'] = False
        await update.message.reply_text("Отмена.", reply_markup=await get_main_keyboard())

    elif context.user_data.get('wait_comment'):
        context.user_data['user_comment'] = text
        context.user_data['wait_comment'] = False
        await update.message.reply_text("✅ Комментарий сохранен! Можете прикрепить фото или оформить заказ.", reply_markup=await get_main_keyboard())

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка одного или нескольких фото"""
    if context.user_data.get('wait_comment'):
        if 'user_photos' not in context.user_data:
            context.user_data['user_photos'] = []
        
        # Добавляем фото в список
        context.user_data['user_photos'].append(update.message.photo[-1].file_id)
        
        if update.message.caption:
            context.user_data['user_comment'] = update.message.caption
        
        # Если это последнее фото в альбоме, сообщаем об успехе
        if not update.message.media_group_id or context.user_data.get('last_media_group_id') != update.message.media_group_id:
            context.user_data['wait_comment'] = False
            await update.message.reply_text(f"✅ Фото ({len(context.user_data['user_photos'])}) сохранены!", reply_markup=await get_main_keyboard())
        
        context.user_data['last_media_group_id'] = update.message.media_group_id
        
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    
    user = update.effective_user
    phone = update.message.contact.phone_number
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    photos = context.user_data.get('user_photos', [])
    
    if not order:
        await update.message.reply_text("⚠️ Сначала соберите навес.")
        return

    # ... код сохранения в базу ...
    if 'orders' not in context.bot_data: context.bot_data['orders'] = {}
    if 'users' not in context.bot_data: context.bot_data['users'] = {}
    
    oid = order.get('id')
    context.bot_data['orders'][oid] = {'data': order, 'user': {'name': user.first_name, 'phone': phone}, 'status': 1}
    context.bot_data['users'][user.id] = f"{user.first_name} ({phone})"

    user_link = f"@{user.username}" if user.username else "Нет"
    report = format_order_message(order, user.first_name, user_link, phone, comment, 1)
    
    try:
        if photos:
            media = [InputMediaPhoto(media=pid) for pid in photos]
            await context.bot.send_media_group(chat_id=ADMIN_CHANNEL_ID, media=media)
            await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=report, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=report, parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(e)

    await update.message.reply_text("✅ <b>Заявка принята!</b>", reply_markup=await get_main_keyboard(), parse_mode=ParseMode.HTML)
    context.user_data.clear()

# ... (Админ-команды остаются без изменений) ...
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return
    text = (
        "👮‍♂️ <b>АДМИН-ПАНЕЛЬ:</b>\n\n"
        "/export - Скачать заказы (CSV)\n"
        "/clean - Удалить сообщения\n"
        "/order - Список последних\n"
        "/order ID - Выбрать заказ"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML)

# ... (Остальные админ-функции) ...
async def cmd_export(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    # ...
async def handle_document(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    # ...
async def cmd_clean(update, context):
    # ...
async def cmd_order_list(update, context):
    # ...
async def cmd_buyers(update, context):
    # ...
async def handle_channel_post(update, context):
    # ...

def main():
    persistence = PicklePersistence(filepath="bot_data.pickle")
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    
    # Admin
    app.add_handler(CommandHandler("admin", cmd_help))
    app.add_handler(CommandHandler("clean", cmd_clean))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("order", cmd_order_list))
    app.add_handler(CommandHandler("buyer", cmd_buyers))
    
    # User
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("🚀 Bot Started (FRIENDLY VERSION)")
    app.run_polling()

if __name__ == '__main__':
    main()
