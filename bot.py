import os
import logging
import json
import io
import csv
import asyncio
import signal
import sys
from datetime import datetime
from aiohttp import web

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PicklePersistence

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),  # Для Render логов
        logging.FileHandler('bot.log', encoding='utf-8')  # Для локальной отладки
    ]
)
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv('PORT', 8080))  # Render автоматически устанавливает PORT
ADMIN_CHANNEL_ID = -1003250531931
INFO_CHANNEL_ID = -1003461235309
INFO_CHANNEL_LINK = "https://t.me/taranov_public"
ADMIN_IDS = [7746957973, 5216818742] 

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)

logger.info(f"🚀 Запуск бота на порту: {PORT}")

# === СПРАВОЧНИКИ ===
ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}
STATUS_MAP = {1: "🟡 Ожидает", 2: "🔵 В работе", 3: "🟢 Сдан"}

# === HTTP СЕРВЕР ДЛЯ HEALTH CHECKS ===
async def handle_health_check(request):
    """Обработчик health check для Render"""
    return web.Response(text="✅ Bot is alive")

async def start_http_server(port):
    """Запуск HTTP сервера на указанном порту для Render"""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    app.router.add_get('/ping', handle_health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 HTTP сервер запущен на порту {port}")
    return runner

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания/фото")],
        [KeyboardButton("📚 Как пользоваться"), KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
    ], resize_keyboard=True)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return True
    if update.effective_user.id in ADMIN_IDS: return True
    try:
        member = await context.bot.get_chat_member(chat_id=INFO_CHANNEL_ID, user_id=update.effective_user.id)
        if member.status in ['left', 'kicked', 'restricted']: return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True

async def ask_subscription(update: Update):
    kb = [[InlineKeyboardButton("📢 Подписаться", url=INFO_CHANNEL_LINK)], [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]]
    await update.message.reply_text("🚫 <b>Доступ ограничен!</b>\nПодпишитесь на канал.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

def format_order_message(order, user_name, user_link, phone, comment, status_code=1, for_admin=True):
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

# === КОРОТКОЕ ПРИВЕТСТВИЕ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    welcome_text = """
🏗 *Конструктор навесов KOVKA007*

Создайте проект навеса под ключ и получите расчет стоимости за минуту!

*Основные функции:*
• 🏗 Конструктор — создайте проект с нужными параметрами
• 📄 Мой заказ — посмотрите детали вашего проекта
• ✏️ Добавить пожелания — прикрепите фото и комментарии
• 📞 Отправить телефон — оформление заявки
• 📚 Как пользоваться — подробное руководство

*Контакты:*
Телефон: +7 (927) 799-11-55
Сайт: https://kovka007.ru

👇 *Выберите действие:*
"""

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_main_keyboard()
    )

# === ПОДРОБНАЯ ИНСТРУКЦИЯ ===

async def show_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instruction_text = """
📚 *ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ КОНСТРУКТОРА*

*1. Откройте конструктор*
Нажмите кнопку «🏗 Открыть конструктор». Откроется приложение, в котором вы сможете выбрать параметры навеса.

*2. Выберите тип навеса*
- Односкатный
- Двускатный
- Арочный
- Треугольный
- Полуарочный

*3. Укажите размеры*
- Длина (от 3 до 20 м)
- Ширина (от 2 до 10 м)
- Высота (от 2 до 5 м)

*4. Выберите материал кровли*
- Сотовый поликарбонат
- Металлочерепица
- Профнастил

*5. Выберите цвет*
- Цвет каркаса
- Цвет кровли

*6. Добавьте опции (по желанию)*
- Усиленные фермы
- Водостоки
- Зашивка стен
- Фундамент
- Монтаж

*7. Рассчитайте стоимость*
Нажмите кнопку «Рассчитать». Система покажет итоговую стоимость.

*8. Сохраните заказ*
После расчета вы можете сохранить заказ и отправить его нам.

*9. Добавьте фото и комментарии*
Вернитесь в бот и нажмите «✏️ Добавить пожелания/фото». Вы можете отправить фото места установки и комментарии.

*10. Оформите заявку*
Нажмите «📞 Отправить телефон и оформить». Мы свяжемся с вами в течение 15 минут.

*📞 Контакты для связи:*
Телефон: +7 (927) 799-11-55
Сайт: https://kovka007.ru
"""

    await update.message.reply_text(
        instruction_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_main_keyboard()
    )

# === АДМИН-ПАНЕЛЬ ===

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return

    text = (
        "👮‍♂️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА:</b>\n\n"
        "🛠 <b>Управление:</b>\n"
        "🔹 <code>/order</code> - Список последних заявок\n"
        "🔹 <code>/order clean</code> - Очистить базу заказов\n"
        "🔹 <code>/order ID</code> - Перейти к заказу\n"
        "🔹 <code>/buyer</code> - Список клиентов\n"
        "🔹 <code>/clean</code> - Удалить последние 50 сообщений\n\n"
        "📂 <b>База данных (Экспорт):</b>\n"
        "🔹 <code>/export</code> - Скачать базу заказов (CSV)\n\n"
        "📥 <b>Импорт:</b>\n"
        "Отправьте .json файл с подписью:\n"
        "<code>/import_db</code> - Загрузить базу заказов"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    orders = context.bot_data.get('orders', {})
    if not orders:
        await update.message.reply_text("📭 База пуста.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Дата', 'Статус', 'Имя', 'Телефон', 'Тип', 'Ширина', 'Длина', 'Цена', 'Комментарий'])

    for oid, info in orders.items():
        data = info.get('data', {})
        user = info.get('user', {})
        writer.writerow([
            oid, info.get('timestamp', '')[:10], STATUS_MAP.get(info.get('status', 1)),
            user.get('name', ''), user.get('phone', ''),
            ROOF_TYPES.get(data.get('type')), data.get('width'), data.get('length'),
            data.get('price'), info.get('comment', '')
        ])

    output.seek(0)
    file_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    file_bytes.name = f"orders_{datetime.now().strftime('%d-%m')}.csv"
    await update.message.reply_document(document=file_bytes, caption=f"📊 Заказов: {len(orders)}")

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return

    if update.message.caption == "/import_db":
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        try:
            data = json.loads(content.decode())
            context.bot_data['orders'] = data
            await update.message.reply_text(f"✅ База восстановлена! Записей: {len(data)}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return
    await msg.reply_text("🗑 Чищу...")
    try:
        mid = msg.message_id
        for i in range(50):
            try: await context.bot.delete_message(msg.chat.id, mid - i)
            except: pass
    except: pass

async def cmd_order_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return

    args = context.args
    orders = context.bot_data.get('orders', {})

    if args and args[0] == 'clean':
        context.bot_data['orders'] = {}
        await msg.reply_text("🗑 База очищена.")
        return

    if args:
        oid = args[0]
        if oid in orders:
            if update.effective_user: context.user_data['admin_edit_order'] = oid
            o = orders[oid]
            status_txt = STATUS_MAP.get(o['status'], 'New')
            text = (
                f"📦 <b>{oid}</b>\nСтатус: {status_txt}\nКлиент: {o['user']['name']} ({o['user']['phone']})\n"
                f"💰 {o['data']['price']:,} руб.\n\n"
                f"👇 Отправьте цифру для смены статуса (в личке):\n1 - Ожидает, 2 - В работе, 3 - Сдан"
            )
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("❌ Не найдено.")
        return

    text = "📂 <b>ЗАКАЗЫ:</b>\n"
    for oid, info in list(orders.items())[-10:]:
        icon = "🟡" if info['status']==1 else "🟢"
        text += f"{icon} <code>{oid}</code> | {info['data']['price']:,}\n"
    await msg.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_buyers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return
    users = context.bot_data.get('users', {})
    if not users:
        await msg.reply_text("📭 Пусто.")
        return
    text = "👥 <b>КЛИЕНТЫ:</b>\n" + "\n".join([v for k, v in users.items()])
    await msg.reply_text(text[:4000])

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or not msg.text: return

    text = msg.text.split()
    cmd = text[0]
    update.message = update.channel_post
    context.args = text[1:]

    if cmd == "/admin": await cmd_help(update, context)
    elif cmd == "/clean": await cmd_clean(update, context)
    elif cmd == "/order": await cmd_order_list(update, context)
    elif cmd == "/buyer": await cmd_buyers(update, context)

# === ПОЛЬЗОВАТЕЛЬСКИЕ ХЕНДЛЕРЫ ===

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.data == "check_sub":
        if await check_subscription(update, context):
            await update.callback_query.message.delete()
            await start(update, context)
        else: await update.callback_query.answer("Нет подписки!", show_alert=True)

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context): 
        await ask_subscription(update)
        return

    text = update.message.text.strip()

    # Обработка смены статуса для админа
    if update.effective_user.id in ADMIN_IDS and text in ['1', '2', '3']:
        edit_id = context.user_data.get('admin_edit_order')
        if edit_id and edit_id in context.bot_data.get('orders', {}):
            context.bot_data['orders'][edit_id]['status'] = int(text)
            await update.message.reply_text(f"✅ Статус обновлен: {STATUS_MAP[int(text)]}")
            return

    # Обработка JSON данных из конструктора
    if text.startswith('{') and text.endswith('}'):
        try:
            data = json.loads(text)
            if 'type' in data:  # Проверяем, что это данные конструктора
                context.user_data['order_data'] = data
                await update.message.reply_text(
                    "✅ Данные конструктора получены! Теперь вы можете:\n"
                    "1. Посмотреть заказ (📄 Мой заказ)\n"
                    "2. Добавить комментарии (✏️ Добавить пожелания/фото)\n"
                    "3. Отправить заявку (📞 Отправить телефон)"
                )
        except Exception as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            pass

    elif text == "📄 Мой заказ":
        order = context.user_data.get('order_data')
        if order:
            user_comment = context.user_data.get('user_comment', 'Не указаны')
            await update.message.reply_text(
                f"🆔 <b>ID заказа:</b> <code>{order.get('id')}</code>\n"
                f"💰 <b>Стоимость:</b> {order.get('price'):,} руб.\n"
                f"💬 <b>Пожелания:</b> {user_comment}\n\n"
                f"Чтобы отправить заявку, нажмите кнопку «📞 Отправить телефон и оформить»",
                parse_mode=ParseMode.HTML
            )
        else: 
            await update.message.reply_text(
                "📭 У вас пока нет созданного заказа.\n"
                "Сначала откройте конструктор и создайте проект навеса.",
                reply_markup=await get_main_keyboard()
            )

    elif text == "✏️ Добавить пожелания/фото":
        context.user_data['wait_comment'] = True
        await update.message.reply_text(
            "✍️ Напишите ваши пожелания или отправьте фотографии:\n\n"
            "• Фото места установки\n"
            "• Особые требования к монтажу\n"
            "• Пожелания по материалам\n"
            "• Дополнительные комментарии\n\n"
            "Или просто отправьте текст.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True)
        )

    elif text == "📚 Как пользоваться":
        await show_instruction(update, context)

    elif text == "🔙 Отмена":
        context.user_data['wait_comment'] = False
        await update.message.reply_text("Действие отменено.", reply_markup=await get_main_keyboard())

    elif context.user_data.get('wait_comment'):
        context.user_data['user_comment'] = text
        context.user_data['wait_comment'] = False
        await update.message.reply_text(
            "✅ Пожелания сохранены!\n\n"
            "Теперь вы можете отправить заявку, нажав «📞 Отправить телефон и оформить».",
            reply_markup=await get_main_keyboard()
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('wait_comment'):
        if 'user_photos' not in context.user_data: 
            context.user_data['user_photos'] = []

        context.user_data['user_photos'].append(update.message.photo[-1].file_id)

        if update.message.caption: 
            context.user_data['user_comment'] = update.message.caption

        # Если это не медиагруппа или первое фото группы
        if not update.message.media_group_id or context.user_data.get('last_media_group_id') != update.message.media_group_id:
            context.user_data['wait_comment'] = False
            await update.message.reply_text(
                f"✅ Фотографии ({len(context.user_data['user_photos'])}) сохранены!\n\n"
                "Теперь вы можете отправить заявку, нажав «📞 Отправить телефон и оформить».",
                reply_markup=await get_main_keyboard()
            )

        context.user_data['last_media_group_id'] = update.message.media_group_id

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        context.user_data['order_data'] = data

        if 'user_comment' not in context.user_data: 
            context.user_data['user_comment'] = 'Нет пожеланий'

        await update.message.reply_text(
            format_order_message(data, update.effective_user.first_name, "", "", "", 1, for_admin=False),
            parse_mode=ParseMode.HTML
        )

        await update.message.reply_text(
            "✅ <b>Проект создан успешно!</b>\n\n"
            "Теперь вы можете:\n"
            "1. Посмотреть детали заказа (📄 Мой заказ)\n"
            "2. Добавить фото и комментарии (✏️ Добавить пожелания/фото)\n"
            "3. Отправить заявку менеджеру (📞 Отправить телефон)\n\n"
            "👇 <b>Для оформления заявки</b> нажмите кнопку «📞 Отправить телефон и оформить» внизу.",
            reply_markup=await get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка обработки webapp данных: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке данных конструктора. Пожалуйста, попробуйте еще раз.",
            reply_markup=await get_main_keyboard()
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await ask_subscription(update)
        return

    user = update.effective_user
    phone = update.message.contact.phone_number
    order = context.user_data.get('order_data')
    comment = context.user_data.get('user_comment', 'Нет пожеланий')
    photos = context.user_data.get('user_photos', [])

    if not order:
        await update.message.reply_text(
            "⚠️ <b>Сначала создайте проект!</b>\n\n"
            "Откройте конструктор и создайте проект навеса, прежде чем отправлять заявку.",
            reply_markup=await get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    if 'orders' not in context.bot_data: 
        context.bot_data['orders'] = {}
    if 'users' not in context.bot_data: 
        context.bot_data['users'] = {}

    oid = order.get('id')
    context.bot_data['orders'][oid] = {
        'data': order,
        'user': {
            'name': user.first_name, 
            'phone': phone, 
            'username': user.username,
            'user_id': user.id
        },
        'status': 1,
        'comment': comment,
        'timestamp': datetime.now().isoformat(),
        'photos_count': len(photos)
    }

    context.bot_data['users'][user.id] = f"{user.first_name} (@{user.username}) - {phone}"

    user_link = f"@{user.username}" if user.username else "Нет"
    report = format_order_message(order, user.first_name, user_link, phone, comment, 1, for_admin=True)

    try:
        if photos:
            # Отправляем фото отдельным постом
            media = [InputMediaPhoto(media=pid) for pid in photos]
            await context.bot.send_media_group(chat_id=ADMIN_CHANNEL_ID, media=media)
            # Отправляем текст заявки
            await context.bot.send_message(
                chat_id=ADMIN_CHANNEL_ID, 
                text=report,
                parse_mode=ParseMode.HTML
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_CHANNEL_ID, 
                text=report,
                parse_mode=ParseMode.HTML
            )
    except Exception as e: 
        logger.error(f"Ошибка отправки в канал: {e}")

    # Ответ пользователю
    await update.message.reply_text(
        "🎉 <b>Заявка успешно отправлена!</b>\n\n"
        f"🆔 <b>Номер вашей заявки:</b> <code>{oid}</code>\n"
        "📞 <b>Наш менеджер свяжется с вами в течение 15 минут</b>\n"
        "⏰ <b>Время работы:</b> Пн-Пт 9:00-20:00, Сб-Вс 10:00-18:00\n\n"
        "📞 <b>Контакты для связи:</b>\n"
        "• Телефон: +7 (927) 799-11-55\n"
        "• Сайт: https://kovka007.ru\n\n"
        "Спасибо за выбор KOVKA007!",
        reply_markup=await get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )

    # Очищаем данные пользователя
    context.user_data.clear()

# === ГЛАВНАЯ ФУНКЦИЯ ===

async def main():
    """Основная функция запуска бота"""
    logger.info(f"🚀 Запуск бота на порту {PORT}...")

    # Настраиваем обработку сигналов
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, завершение работы...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Инициализируем бота
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("admin", cmd_help))
    application.add_handler(CommandHandler("clean", cmd_clean))
    application.add_handler(CommandHandler("order", cmd_order_list))
    application.add_handler(CommandHandler("buyer", cmd_buyers))
    application.add_handler(CommandHandler("export", cmd_export))
    application.add_handler(CommandHandler("start", start))

    # Обработчики канала
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))

    # Пользовательские обработчики
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))

    # Запускаем HTTP сервер для health checks на порту от Render
    http_runner = await start_http_server(PORT)

    try:
        # Запускаем бота
        await application.initialize()
        await application.start()

        logger.info("🤖 Бот запущен и работает в режиме polling...")
        logger.info(f"📊 Health check доступен по адресу: http://0.0.0.0:{PORT}/health")

        # Запускаем polling
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

        # Держим бота активным
        while True:
            await asyncio.sleep(3600)  # Спим по часу

    except asyncio.CancelledError:
        logger.info("Получен запрос на остановку...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Корректное завершение
        logger.info("Завершение работы бота...")
        if application.updater:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await http_runner.cleanup()

# === ТОЧКА ВХОДА ===
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)