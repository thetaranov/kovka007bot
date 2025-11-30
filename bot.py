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

# КОНФИГУРАЦИЯ
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHANNEL_ID = -1003250531931  # Куда летят заявки
INFO_CHANNEL_ID = -1003461235309   # Обязательный канал (бот должен быть админом!)
INFO_CHANNEL_LINK = "https://t.me/taranov_public" # Публичная ссылка

ADMIN_IDS = [7746957973] 

if not BOT_TOKEN:
    exit(1)

ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}

# === ПРОВЕРКА ПОДПИСКИ ===
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=user_id)
        
        # Логируем статус для отладки
        logger.info(f"Статус подписки user {user_id}: {member.status}")
        
        # Разрешенные статусы: creator (владелец), administrator (админ), member (подписчик)
        if member.status in ['left', 'kicked', 'restricted']:
            return False
        return True
        
    except Exception as e:
        logger.error(f"⚠️ Ошибка проверки подписки: {e}")
        logger.error("Убедитесь, что бот является АДМИНИСТРАТОРОМ в канале " + str(INFO_CHANNEL_ID))
        # В случае ошибки API лучше пустить пользователя, чем заблокировать навсегда
        return True

async def ask_subscription(update: Update):
    """Показывает плашку подписки"""
    kb = [
        [InlineKeyboardButton("📢 Подписаться на канал", url=INFO_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
    ]
    
    msg_text = (
        "🚫 <b>Доступ ограничен!</b>\n\n"
        "Чтобы пользоваться конструктором и ботом, пожалуйста, подпишитесь на наш канал.\n"
        "Там много полезного про навесы и стройку!"
    )
    
    # Отправляем сообщение или редактируем старое (если это callback)
    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# === ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка при старте
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    web_app_url = "https://kovka007.vercel.app"
    
    kb = [
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания")],
        [KeyboardButton("🆘 Помощь")]
    ]
    
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        "Добро пожаловать в бота <b>Kovka007</b>.\n"
        "Здесь вы можете рассчитать стоимость навеса за 1 минуту.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Я подписался'"""
    query = update.callback_query
    
    if query.data == "check_sub":
        if await check_subscription(update, context):
            await query.answer("✅ Спасибо за подписку!")
            await query.message.delete() # Удаляем просьбу о подписке
            await start(update, context) # Запускаем меню
        else:
            await query.answer("❌ Вы еще не подписались!", show_alert=True)

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню бота"""
    # Сначала проверяем подписку на каждое действие
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    text = update.message.text
    
    if text == "📄 Мой заказ":
        order = context.user_data.get('order_data')
        if not order:
            await update.message.reply_text("📭 Корзина пуста. Откройте конструктор, чтобы создать заказ.")
            return
        
        rtype = ROOF_TYPES.get(order.get('type'), order.get('type'))
        comment = context.user_data.get('user_comment', 'Нет')
        
        msg = (
            f"📋 <b>ВАШ ЗАКАЗ</b>\n\n"
            f"🆔 <code>{order.get('id')}</code>\n"
            f"🏗 {rtype}\n"
            f"📏 {order.get('width')}x{order.get('length')} м\n"
            f"💰 {order.get('price', 0):,} руб.\n\n"
            f"📝 <b>Комментарий:</b> {comment}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    elif text == "✏️ Добавить пожелания":
        context.user_data['waiting_for_comment'] = True
        await update.message.reply_text("✍️ Напишите ваши пожелания к заказу одним сообщением:")

    elif text == "🆘 Помощь":
        await update.message.reply_text("По всем вопросам пишите: @thetaranov")
    
    elif context.user_data.get('waiting_for_comment'):
        context.user_data['user_comment'] = text
        context.user_data['waiting_for_comment'] = False
        await update.message.reply_text("✅ Комментарий сохранен!")

# === ОБРАБОТКА ДАННЫХ И КОНТАКТА ===

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Данные принимаем даже без подписки, но оформить не дадим без нее
    try:
        data_str = update.effective_message.web_app_data.data
        raw_data = json.loads(data_str)
        
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
        
        rtype = ROOF_TYPES.get(order_data['type'], order_data['type'])
        
        text = (
            f"✅ <b>Расчет готов!</b>\n"
            f"🆔 <code>{order_data['id']}</code>\n"
            f"🏗 {rtype} ({order_data['width']}x{order_data['length']}м)\n"
            f"💰 <b>{order_data['price']:,} руб.</b>\n\n"
            f"👇 Нажмите кнопку ниже, чтобы отправить заявку."
        )
        
        kb = [[KeyboardButton("📞 Отправить телефон", request_contact=True)]]
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем подписку перед отправкой админу
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    user = update.effective_user
    contact = update.message.contact
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет')
    
    if not order:
        await update.message.reply_text("⚠️ Ошибка: нет данных заказа.")
        return

    # Сохранение в историю
    if 'orders_history' not in context.bot_data:
        context.bot_data['orders_history'] = []
    
    context.bot_data['orders_history'].append({
        'id': order.get('id'),
        'user': f"@{user.username}" if user.username else user.first_name,
        'price': order.get('price'),
        'phone': contact.phone_number
    })

    # Формирование отчета
    opts = order.get('opts', {})
    options_list = []
    if opts.get('trusses'): options_list.append("✅ Усил. фермы")
    if opts.get('gutters'): options_list.append("✅ Водостоки")
    if opts.get('walls'): options_list.append("✅ Боковая зашивка")
    if opts.get('found'): options_list.append("✅ Фундамент")
    if opts.get('install'): options_list.append("✅ Монтаж")
    options_str = "\n".join(options_list) if options_list else "Базовая"

    admin_report = (
        f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>Клиент:</b> {user.first_name}\n"
        f"🔗 <b>Link:</b> @{user.username if user.username else 'Нет'}\n"
        f"📞 <b>Tel:</b> <code>{contact.phone_number}</code>\n"
        f"💬 <b>Пожелания:</b> {comment}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>ID:</b> <code>{order.get('id')}</code>\n"
        f"🏗 <b>Тип:</b> {ROOF_TYPES.get(order.get('type'))}\n"
        f"📏 <b>Ширина:</b> {order.get('width')} м\n"
        f"📏 <b>Длина:</b> {order.get('length')} м\n"
        f"↕️ <b>Высота (проезд):</b> {order.get('height')} м\n"
        f"🏔 <b>Высота (общая):</b> ~{order.get('height_peak')} м\n"
        f"🧱 <b>Столбы:</b> {order.get('pillar')}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔲 <b>S пола:</b> {order.get('area_floor')} м²\n"
        f"🏠 <b>S кровли:</b> {order.get('area_roof')} м²\n"
        f"🏠 <b>Кровля:</b> {MATERIALS.get(order.get('material'))}\n"
        f"🖌 <b>Цвет:</b> {order.get('color_frame')} / {order.get('color_roof')}\n"
        f"🎨 <b>Покраска:</b> {PAINTS.get(order.get('paint'))}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🛠 <b>Опции:</b>\n{options_str}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>{order.get('price', 0):,} руб.</b>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHANNEL_ID, text=admin_report, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Channel error: {e}")

    await start(update, context) # Возврат в меню
    await update.message.reply_text("✅ Заказ отправлен менеджеру!")
    context.user_data.clear()

# === АДМИНКА ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    history = context.bot_data.get('orders_history', [])
    msg = f"📊 <b>Заказов всего:</b> {len(history)}\n\n"
    for o in history[-5:]:
        msg += f"🔹 {o['id']} | {o['price']}р | {o['user']}\n"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))

    logger.info("🚀 Бот запущен (SUB CHECK)")
    application.run_polling()

if __name__ == '__main__':
    main()
