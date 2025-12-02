import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
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
ADMIN_IDS = [7746957973] 

if not BOT_TOKEN: exit(1)

# === СПРАВОЧНИКИ ===
ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}

STATUS_MAP = {
    1: "🟡 Ожидает подтверждения",
    2: "🔵 В работе",
    3: "🟢 Объект сдан"
}

# === ПРОВЕРКА ПОДПИСКИ ===
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
    await update.message.reply_text("🚫 <b>Доступ ограничен!</b>\nПодпишитесь на канал.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# === КЛАВИАТУРА ===
async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания")],
        [KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
    ], resize_keyboard=True)

# === ФОРМАТИРОВАНИЕ ЗАКАЗА ===
def format_order_message(order, user, phone, comment, status_code=1):
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

    return (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"Статус: {STATUS_MAP.get(status_code, 'Неизвестно')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name}\n"
        f"🔗 <b>Link:</b> @{user.username if user.username else 'Нет'}\n"
        f"📞 <b>Phone:</b> <code>{phone}</code>\n"
        f"💬 <b>Пожелания:</b> {comment}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
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

# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    await update.message.reply_text("👋 Добро пожаловать!", reply_markup=await get_main_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "check_sub":
        await query.answer()
        if await check_subscription(update, context):
            await query.message.delete()
            await start(update, context)
        else: await query.message.reply_text("❌ Подпишитесь на канал!", ephemeral=True)

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        order_data = {
            'id': data.get('id'),
            'type': data.get('type') or data.get('t'),
            'width': data.get('width') or data.get('w'),
            'length': data.get('length') or data.get('l'),
            'height': data.get('height') or data.get('h'),
            'height_peak': data.get('height_peak', 0),
            'slope': data.get('slope') or data.get('s'),
            'price': data.get('price') or data.get('pr') or 0,
            'area_floor': data.get('area_floor', '0'),
            'area_roof': data.get('area_roof', '0'),
            'pillar': data.get('pillar', 'Не указано'),
            'material': data.get('material', 'polycarbonate'),
            'paint': data.get('paint', 'none'),
            'color_frame': data.get('color_frame', 'Стандарт'),
            'color_roof': data.get('color_roof', 'Стандарт'),
            'opts': data.get('opts', {})
        }
        context.user_data['order_data'] = order_data
        if 'user_comment' not in context.user_data: context.user_data['user_comment'] = 'Нет'
        
        await update.message.reply_text(
            f"🔄 <b>Данные получены!</b>\n💰 Сумма: {order_data['price']:,} руб.\n👇 Нажмите «📞 Отправить телефон» внизу.",
            reply_markup=await get_main_keyboard(), parse_mode=ParseMode.HTML
        )
    except: pass

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    text = update.message.text.strip()
    
    # Админ-команды в чате (без /)
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        # Смена статуса цифрой
        if text in ['1', '2', '3']:
            edit_id = context.user_data.get('admin_edit_order')
            if edit_id:
                orders = context.bot_data.get('orders', {})
                if edit_id in orders:
                    orders[edit_id]['status'] = int(text)
                    await update.message.reply_text(f"✅ Статус {edit_id} -> <b>{STATUS_MAP[int(text)]}</b>", parse_mode=ParseMode.HTML)
                    return
            else:
                await update.message.reply_text("⚠️ Сначала выберите заказ: /order ID")
                return

    # Пользовательские кнопки
    if text == "📄 Мой заказ":
        order = context.user_data.get('order_data')
        if not order:
            await update.message.reply_text("📭 Нет активного заказа.")
            return
        msg = format_order_message(order, update.effective_user, "Не указан", context.user_data.get('user_comment', 'Нет'))
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    elif text == "✏️ Добавить пожелания":
        context.user_data['wait_comment'] = True
        await update.message.reply_text("✍️ Напишите пожелания (или фото) одним сообщением:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True))

    elif text == "🔙 Отмена":
        context.user_data['wait_comment'] = False
        await update.message.reply_text("Отменено.", reply_markup=await get_main_keyboard())

    elif context.user_data.get('wait_comment'):
        context.user_data['user_comment'] = text
        context.user_data['wait_comment'] = False
        await update.message.reply_text("✅ Комментарий сохранен!", reply_markup=await get_main_keyboard())

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('wait_comment'):
        context.user_data['user_photo'] = update.message.photo[-1].file_id
        if update.message.caption: context.user_data['user_comment'] = update.message.caption
        context.user_data['wait_comment'] = False
        await update.message.reply_text("✅ Фото сохранено!", reply_markup=await get_main_keyboard())

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): return
    
    user = update.effective_user
    phone = update.message.contact.phone_number
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    photo = context.user_data.get('user_photo')
    
    if not order:
        await update.message.reply_text("⚠️ Соберите навес в конструкторе.")
        return

    if 'orders' not in context.bot_data: context.bot_data['orders'] = {}
    if 'users' not in context.bot_data: context.bot_data['users'] = {}

    order_id = order.get('id')
    full_order_info = {
        'data': order,
        'user': {'id': user.id, 'name': user.first_name, 'username': user.username, 'phone': phone},
        'comment': comment,
        'status': 1,
        'timestamp': update.message.date.isoformat()
    }
    context.bot_data['orders'][order_id] = full_order_info
    context.bot_data['users'][user.id] = f"{user.first_name} (@{user.username}) - {phone}"

    report = format_order_message(order, user, phone, comment, 1)
    
    try:
        if photo:
            await context.bot.send_photo(chat_id=ADMIN_CHANNEL_ID, photo=photo, caption=report, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=report, parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(e)

    await update.message.reply_text("✅ <b>Заявка принята!</b>", reply_markup=await get_main_keyboard(), parse_mode=ParseMode.HTML)
    context.user_data.clear()

# === АДМИН КОМАНДЫ ===

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд админа"""
    if update.effective_user.id not in ADMIN_IDS: return
    
    help_text = (
        "👮‍♂️ <b>КОМАНДЫ АДМИНИСТРАТОРА:</b>\n\n"
        "🔹 <code>/order</code> - Список последних 10 заказов\n"
        "🔹 <code>/order clean</code> - Очистить базу заказов\n"
        "🔹 <code>/order ID</code> - Выбрать заказ для редактирования\n"
        "🔹 <code>/buyer</code> - Список всех клиентов\n"
        "🔹 <code>/clean</code> - Удалить последние 50 сообщений бота\n\n"
        "<i>Чтобы изменить статус заказа, сначала выберите его через /order ID, а затем отправьте цифру:</i>\n"
        "1️⃣ Ожидает\n2️⃣ В работе\n3️⃣ Сдан"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("🗑 Чищу чат...")
    try:
        msg_id = update.message.message_id
        for i in range(50):
            try: await context.bot.delete_message(update.effective_chat.id, msg_id - i)
            except: pass
    except: pass

async def cmd_order_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    args = context.args
    orders = context.bot_data.get('orders', {})

    if args and args[0] == 'clean':
        context.bot_data['orders'] = {}
        await update.message.reply_text("🗑 База заказов очищена.")
        return

    if args:
        oid = args[0]
        if oid in orders:
            context.user_data['admin_edit_order'] = oid
            o = orders[oid]
            status_txt = STATUS_MAP.get(o['status'], 'New')
            msg = (
                f"📦 <b>Заказ {oid}</b>\n"
                f"Статус: {status_txt}\n"
                f"Клиент: {o['user']['name']} ({o['user']['phone']})\n"
                f"Сумма: {o['data']['price']:,} руб.\n\n"
                f"👇 <b>Отправьте цифру для смены статуса:</b>\n"
                f"1 - Ожидает\n2 - В работе\n3 - Сдан"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ Заказ не найден.")
        return

    if not orders:
        await update.message.reply_text("📭 Заказов нет.")
        return
        
    msg = "📂 <b>АКТИВНЫЕ ЗАЯВКИ:</b>\n\n"
    for oid, info in list(orders.items())[-10:]:
        icon = "🟡" if info['status'] == 1 else "🔵" if info['status'] == 2 else "🟢"
        msg += f"{icon} <code>{oid}</code> | {info['user']['name']} | {info['data']['price']:,}\n"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def cmd_buyers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    users = context.bot_data.get('users', {})
    if not users:
        await update.message.reply_text("📭 База пуста.")
        return
    
    msg = "👥 <b>КЛИЕНТЫ:</b>\n\n"
    for uid, info in users.items():
        msg += f"👤 {info}\n"
        
    if len(msg) > 4000: msg = msg[:4000] + "..."
    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", cmd_help)) # /admin вызывает справку
    app.add_handler(CommandHandler("clean", cmd_clean))
    app.add_handler(CommandHandler("order", cmd_order_list))
    app.add_handler(CommandHandler("buyer", cmd_buyers))
    
    # Данные
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    
    logger.info("🚀 Бот запущен (FINAL)")
    app.run_polling()

if __name__ == '__main__':
    main()
