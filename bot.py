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

# КОНФИГУРАЦИЯ
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931  # Канал для заказов
INFO_CHANNEL_ID = -1003461235309   # Канал для обязательной подписки
INFO_CHANNEL_LINK = "https://t.me/+rRO-uz37RgtkZTY6" # Ссылка на канал (замените на правильную)

# СПИСОК АДМИНОВ (ID пользователей)
ADMIN_IDS = [7746957973] # <--- ВСТАВЬТЕ СЮДА СВОЙ ID (число)

if not BOT_TOKEN:
    exit(1)

# Справочники
ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}

# === ПРОВЕРКА ПОДПИСКИ ===
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает True, если подписан"""
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=user_id)
        if member.status in ['left', 'kicked', 'banned']:
            return False
        return True
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        # Если бот не админ в канале подписки, пропускаем (чтобы не блокировать всех)
        return True

async def ask_subscription(update: Update):
    """Просит подписаться"""
    kb = [[InlineKeyboardButton("📢 Подписаться на канал", url=INFO_CHANNEL_LINK)]]
    # Добавляем кнопку проверки, которая вызывает /start
    kb.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")])
    
    await update.message.reply_text(
        "🚫 <b>Доступ ограничен!</b>\n\n"
        "Для использования бота необходимо подписаться на наш информационный канал.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )

# === ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    # Главное меню
    web_app_url = "https://kovka007.vercel.app"
    
    kb = [
        [KeyboardButton("🏗 Открыть конструктор (Изменить)", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания")],
        [KeyboardButton("🆘 Помощь")]
    ]
    
    await update.message.reply_text(
        "👋 <b>Главное меню</b>\n\n"
        "Здесь вы можете рассчитать стоимость навеса, добавить комментарий к заказу и отправить заявку.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок (проверка подписки)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_sub":
        if await check_subscription(update, context):
            await query.message.delete()
            await start(update, context)
        else:
            await query.message.reply_text("❌ Вы еще не подписались!", ephemeral=True)

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок меню"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Мой заказ
    if text == "📄 Мой заказ":
        order = context.user_data.get('order_data')
        if not order:
            await update.message.reply_text("📭 У вас пока нет активного расчета. Откройте конструктор!")
            return
        
        rtype = ROOF_TYPES.get(order.get('type'), order.get('type'))
        comment = context.user_data.get('user_comment', 'Нет')
        
        msg = (
            f"📋 <b>ВАШ ТЕКУЩИЙ ЗАКАЗ</b>\n"
            f"🆔 <code>{order.get('id')}</code>\n"
            f"🏗 {rtype}\n"
            f"💰 {order.get('price', 0):,} руб.\n"
            f"📝 <b>Пожелания:</b> {comment}\n\n"
            f"<i>Чтобы оформить, нажмите 'Отправить телефон' после сборки в конструкторе.</i>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    # Добавить пожелания
    elif text == "✏️ Добавить пожелания":
        context.user_data['waiting_for_comment'] = True
        await update.message.reply_text(
            "✍️ <b>Напишите ваши пожелания</b> одним сообщением (например: 'Нужен выезд замерщика завтра'):",
            parse_mode=ParseMode.HTML
        )

    # Помощь
    elif text == "🆘 Помощь":
        await update.message.reply_text(
            "🛠 <b>Как пользоваться ботом:</b>\n\n"
            "1. Нажмите <b>'Открыть конструктор'</b>\n"
            "2. Соберите навес и нажмите 'Оформить заявку' на сайте\n"
            "3. Бот покажет расчет. Вы можете добавить пожелания через меню.\n"
            "4. Нажмите кнопку <b>'Отправить телефон'</b> для финализации.",
            parse_mode=ParseMode.HTML
        )
    
    # Обработка ввода текста (комментария)
    elif context.user_data.get('waiting_for_comment'):
        context.user_data['user_comment'] = text
        context.user_data['waiting_for_comment'] = False
        await update.message.reply_text(f"✅ Комментарий сохранен:\n<i>{text}</i>", parse_mode=ParseMode.HTML)

# === ЛОГИКА ЗАКАЗА ===

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data_str = update.effective_message.web_app_data.data
        raw_data = json.loads(data_str)
        
        # Нормализация
        order_data = {
            'id': raw_data.get('id'),
            'type': raw_data.get('type') or raw_data.get('t'),
            'width': raw_data.get('width') or raw_data.get('w'),
            'length': raw_data.get('length') or raw_data.get('l'),
            'height': raw_data.get('height') or raw_data.get('h'),
            'height_peak': raw_data.get('height_peak', 0), # Новое поле
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
        
        rtype = ROOF_TYPES.get(order_data['type'], order_data['type'])
        
        text = (
            f"✅ <b>Расчет обновлен!</b>\n"
            f"🆔 <code>{order_data['id']}</code>\n"
            f"🏗 {rtype}\n"
            f"📏 {order_data['width']}x{order_data['length']} м\n"
            f"💰 <b>{order_data['price']:,} руб.</b>\n\n"
            f"<i>Вы можете добавить комментарий через меню или сразу отправить контакты.</i>"
        )
        
        kb = [[KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]]
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    
    if not order:
        await update.message.reply_text("⚠️ Сначала соберите навес в конструкторе.")
        return

    # Сохраняем заказ в историю бота (в памяти) для админки
    if 'orders_history' not in context.bot_data:
        context.bot_data['orders_history'] = []
    
    # Краткая запись для истории
    history_item = {
        'id': order.get('id'),
        'user': f"@{user.username}" if user.username else user.first_name,
        'price': order.get('price'),
        'phone': contact.phone_number
    }
    context.bot_data['orders_history'].append(history_item)
    # Храним только последние 50
    if len(context.bot_data['orders_history']) > 50:
        context.bot_data['orders_history'].pop(0)

    # Опции
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усиленные фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Боковая зашивка")
    if opts.get('found'): options_list.append("✅ Фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж")
    options_str = "\n".join(options_list) if options_list else "Базовая"

    # ОТЧЕТ АДМИНУ
    admin_report = (
        f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name}\n"
        f"🔗 <b>Username:</b> @{user.username if user.username else 'Нет'}\n"
        f"📞 <b>Телефон:</b> <code>{contact.phone_number}</code>\n"
        f"💬 <b>Пожелания:</b> {comment}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>ID:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {ROOF_TYPES.get(order.get('type'), order.get('type'))}\n"
        f"📐 <b>Габариты:</b> {order.get('width')} x {order.get('length')} м\n"
        f"📏 <b>Ширина:</b> {order.get('width')} м\n"
        f"📏 <b>Длина:</b> {order.get('length')} м\n"
        f"↕️ <b>Высота столбов:</b> {order.get('height')} м\n"
        f"🏔 <b>Общая высота:</b> ~{order.get('height_peak')} м\n"
        f"🧱 <b>Сечение столбов:</b> {order.get('pillar')}\n"
        f"📐 <b>Уклон:</b> {order.get('slope')}°\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔲 <b>Площадь пола:</b> {order.get('area_floor')} м²\n"
        f"🏠 <b>Площадь кровли:</b> {order.get('area_roof')} м²\n"
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
        logger.error(f"Channel error: {e}")

    # Возвращаем главное меню
    await start(update, context)
    await update.message.reply_text("✅ Заказ отправлен! Менеджер свяжется с вами.")
    
    # Очистка
    context.user_data.clear()

# === АДМИН ПАНЕЛЬ ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return # Игнорируем не админов

    history = context.bot_data.get('orders_history', [])
    
    msg = f"👮‍♂️ <b>АДМИН ПАНЕЛЬ</b>\n\n📊 Всего заказов в памяти: {len(history)}\n\n"
    
    # Показать последние 5 заказов
    last_orders = history[-5:]
    for o in last_orders:
        msg += f"🔹 {o['id']} | {o['user']} | {o['price']:,}р\n"
    
    msg += "\n<i>Для рассылки используйте /broadcast текст</i>"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return

    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("⚠️ Введите текст: /broadcast Привет всем")
        return
    
    # В реальном боте нужно хранить user_ids в БД.
    # Здесь мы не можем разослать, так как не храним ID всех пользователей.
    # Это заглушка.
    await update.message.reply_text("ℹ️ Рассылка работает только с базой данных (в этом коде отключена для безопасности).")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    # Данные
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # Меню и кнопки
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))

    logger.info("🚀 Бот запущен (PRO VERSION)")
    application.run_polling()

if __name__ == '__main__':
    main()
