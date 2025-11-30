import os
import logging
import json
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from keep_alive import keep_alive

# Запуск сервера для поддержки активности
keep_alive()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931  # Канал для заявок
INFO_CHANNEL_ID = -1003461235309   # Канал для обязательной подписки
INFO_CHANNEL_LINK = "https://t.me/taranov_public"
ADMIN_IDS = [7746957973] # ID админов бота

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# Справочники для перевода
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

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания")],
        [KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
    ], resize_keyboard=True)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на канал"""
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS: return True
    
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=user_id)
        if member.status in ['left', 'kicked', 'restricted']:
            return False
        return True
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        # Если бот не админ или ошибка API - пускаем, чтобы не блокировать бота
        return True

async def ask_subscription(update: Update):
    """Просьба подписаться"""
    kb = [
        [InlineKeyboardButton("📢 Подписаться на канал", url=INFO_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
    ]
    await update.message.reply_text(
        "🚫 <b>Доступ ограничен!</b>\n\n"
        "Для использования конструктора необходимо подписаться на наш канал.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )

# === ОБРАБОТЧИКИ КОМАНД ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        "Рассчитайте стоимость навеса в конструкторе и отправьте заявку в пару кликов.",
        reply_markup=await get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки проверки подписки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_sub":
        if await check_subscription(update, context):
            await query.message.delete()
            await start(update, context)
        else:
            await query.message.reply_text("❌ Вы еще не подписались!", ephemeral=True)

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового меню"""
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    text = update.message.text
    
    # 1. МОЙ ЗАКАЗ
    if text == "📄 Мой заказ":
        order = context.user_data.get('order_data')
        comment = context.user_data.get('user_comment', 'Нет')
        
        if not order:
            await update.message.reply_text("📭 Корзина пуста. Откройте конструктор!")
            return
        
        rtype = ROOF_TYPES.get(order.get('type'), order.get('type'))
        
        msg = (
            f"📋 <b>ВАШ ЗАКАЗ</b>\n"
            f"🆔 <code>{order.get('id')}</code>\n"
            f"🏗 {rtype} ({order.get('width')}x{order.get('length')}м)\n"
            f"💰 <b>{order.get('price', 0):,} руб.</b>\n\n"
            f"📝 <b>Комментарий:</b> {comment}\n\n"
            f"👇 <i>Нажмите 'Отправить телефон', чтобы отправить заявку менеджеру.</i>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    # 2. ПОЖЕЛАНИЯ
    elif text == "✏️ Добавить пожелания":
        context.user_data['waiting_for_comment'] = True
        cancel_kb = ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True)
        await update.message.reply_text("✍️ Напишите ваши пожелания одним сообщением:", reply_markup=cancel_kb)

    # 3. ОТМЕНА
    elif text == "🔙 Отмена":
        context.user_data['waiting_for_comment'] = False
        await update.message.reply_text("Ввод отменен.", reply_markup=await get_main_keyboard())

    # 4. СОХРАНЕНИЕ ТЕКСТА
    elif context.user_data.get('waiting_for_comment'):
        context.user_data['user_comment'] = text
        context.user_data['waiting_for_comment'] = False
        await update.message.reply_text(
            f"✅ Комментарий сохранен!\n\n<i>\"{text}\"</i>",
            reply_markup=await get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )

# === ПОЛУЧЕНИЕ ДАННЫХ ИЗ WEBAPP ===

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data_str = update.effective_message.web_app_data.data
        logger.info(f"📥 Data: {data_str}")
        raw_data = json.loads(data_str)
        
        # Собираем данные в единую структуру
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
        
        # Сохраняем старый коммент, если был
        if 'user_comment' not in context.user_data:
            context.user_data['user_comment'] = 'Нет'

        text = (
            f"🔄 <b>Данные обновлены!</b>\n"
            f"🆔 <code>{order_data['id']}</code>\n"
            f"💰 Сумма: <b>{order_data['price']:,} руб.</b>\n\n"
            f"👇 Нажмите кнопку ниже, чтобы отправить заявку."
        )
        
        await update.message.reply_text(text, reply_markup=await get_main_keyboard(), parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"WebApp Error: {e}")
        await update.message.reply_text("❌ Ошибка получения данных.")

# === ОТПРАВКА ЗАЯВКИ (ФИНАЛ) ===

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    user = update.effective_user
    contact = update.message.contact
    
    # Берем ВСЕ данные из памяти
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    
    if not order:
        await update.message.reply_text("⚠️ Ошибка: Данные заказа не найдены. Соберите навес заново.")
        return

    # Сохраняем в историю
    if 'orders_history' not in context.bot_data:
        context.bot_data['orders_history'] = []
    
    context.bot_data['orders_history'].append({
        'id': order.get('id'),
        'user': f"@{user.username}" if user.username else user.first_name,
        'price': order.get('price'),
        'phone': contact.phone_number
    })

    # Формируем галочки опций
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усил. фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Боковая зашивка")
    if opts.get('found'): options_list.append("✅ Фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж")
    options_str = "\n".join(options_list) if options_list else "Базовая комплектация"

    # ОТЧЕТ ДЛЯ АДМИНА
    admin_report = (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name} {user.last_name or ''}\n"
        f"🔗 <b>Link:</b> @{user.username if user.username else 'Нет'}\n"
        f"📞 <b>Phone:</b> <code>{contact.phone_number}</code>\n"
        f"💬 <b>Пожелания:</b> {comment}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>ID:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {ROOF_TYPES.get(order.get('type'))}\n"
        f"📏 <b>Габариты:</b> {order.get('width')} x {order.get('length')} м\n"
        f"↕️ <b>Высота (столб):</b> {order.get('height')} м\n"
        f"🏔 <b>Высота (общая):</b> ~{order.get('height_peak')} м\n"
        f"📐 <b>Уклон:</b> {order.get('slope')}°\n"
        f"🧱 <b>Сечение:</b> {order.get('pillar')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔲 <b>S пола:</b> {order.get('area_floor')} м²\n"
        f"🏠 <b>S кровли:</b> {order.get('area_roof')} м²\n"
        f"🏠 <b>Материал:</b> {MATERIALS.get(order.get('material'))}\n"
        f"🎨 <b>Покраска:</b> {PAINTS.get(order.get('paint'))}\n"
        f"🖌 <b>Цвет (К/К):</b> {order.get('color_frame')} / {order.get('color_roof')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🛠 <b>Опции:</b>\n{options_str}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>ИТОГО: {order.get('price', 0):,} руб.</b>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=admin_report, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Send channel error: {e}")
        await update.message.reply_text("⚠️ Ошибка отправки заявки.")
        return

    await update.message.reply_text(
        "✅ <b>Заявка отправлена!</b>\nМенеджер свяжется с вами в ближайшее время.",
        reply_markup=await get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    # Очистка
    context.user_data.clear()

# === АДМИН ПАНЕЛЬ ===

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    history = context.bot_data.get('orders_history', [])
    msg = f"📊 <b>Всего заказов:</b> {len(history)}\n\n"
    for o in history[-5:]:
        msg += f"🔹 {o['id']} | {o['price']:,}р | {o['user']}\n"
        
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка (работает только если есть база ID, здесь заглушка)"""
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("ℹ️ Рассылка требует подключения базы данных.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))

    logger.info("🚀 Бот запущен (FULL FINAL)")
    application.run_polling()

if __name__ == '__main__':
    main()
