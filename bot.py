import os
import logging
import json
import io
import csv
import asyncio
import signal
import sys
import base64
import time
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
ADMIN_USER_ID = 5216818742
INFO_CHANNEL_ID = -1003461235309
INFO_CHANNEL_LINK = "https://t.me/taranov_public"
ADMIN_IDS = [7746957973, 5216818742] 

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)

logger.info(f"🚀 Запуск бота на порту: {PORT}")

# === ХРАНИЛИЩЕ СКРИНШОТОВ (в памяти, TTL 5 минут) ===
_screenshot_store: dict[str, tuple[str, float]] = {}  # order_id -> (base64_data, timestamp)

def store_screenshot(order_id: str, base64_data: str):
    """Сохранить скриншот для заказа"""
    _screenshot_store[order_id] = (base64_data, time.time())
    # Очистка старых (>5 мин)
    cutoff = time.time() - 300
    expired = [k for k, v in _screenshot_store.items() if v[1] < cutoff]
    for k in expired:
        del _screenshot_store[k]

def get_screenshot(order_id: str) -> str | None:
    """Получить скриншот для заказа"""
    entry = _screenshot_store.pop(order_id, None)
    if entry and (time.time() - entry[1]) < 300:
        return entry[0]
    return None

def decode_screenshot(base64_data: str) -> bytes | None:
    """Декодировать base64 скриншот в bytes"""
    try:
        # Удаляем data:image/jpeg;base64, если есть
        if ',' in base64_data:
            base64_data = base64_data.split(',', 1)[1]
        return base64.b64decode(base64_data)
    except Exception as e:
        logger.error(f"Failed to decode screenshot: {e}")
        return None

async def send_order_with_photo(bot, chat_id: str | int, msg: str, screenshot_b64: str | None):
    """Отправить заказ с фото или без"""
    photo_bytes = decode_screenshot(screenshot_b64) if screenshot_b64 else None
    if photo_bytes:
        try:
            photo_io = io.BytesIO(photo_bytes)
            photo_io.name = 'scene.jpg'
            await bot.send_photo(chat_id=chat_id, photo=photo_io, caption=msg[:1024], parse_mode=ParseMode.HTML)
            # Если сообщение длиннее 1024 символов — дошлём текстом
            if len(msg) > 1024:
                await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
            return True
        except Exception as e:
            logger.error(f"Failed to send photo to {chat_id}: {e}")
    # Fallback: отправляем только текст
    await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
    return False

# === СПРАВОЧНИКИ ===
ROOF_TYPES = {'single': 'Односкатный', 'gable': 'Двускатный', 'arched': 'Арочный', 'triangular': 'Треугольный', 'semiarched': 'Полуарочный'}
MATERIALS = {'polycarbonate': 'Сотовый поликарбонат', 'metaltile': 'Металлочерепица', 'decking': 'Профнастил'}
PAINTS = {'none': 'Грунт-эмаль', 'ral': 'Эмаль RAL', 'polymer': 'Полимерно-порошковая'}
STATUS_MAP = {1: "🟡 Ожидает", 2: "🔵 В работе", 3: "🟢 Сдан"}
GATE_TYPES = {'none': 'Нет', 'sliding': 'Откатные', 'swing': 'Распашные', 'hinged': 'Навесные'}
GATE_FILLINGS = {
    'lattice': 'Решетка',
    'solid': 'Сплошное',
    'forged': 'Ковка',
    'combined': 'Комби',
    'vertical': 'Вертик. планки'
}

# === HTTP СЕРВЕР ДЛЯ HEALTH CHECKS ===
async def handle_health_check(request):
    """Обработчик health check для Render"""
    return web.Response(text="✅ Bot is alive")

async def start_http_server(port, application=None):
    """Запуск HTTP сервера на указанном порту для Render.
    Если передан объект telegram Application, добавляется endpoint для приёма заказов из браузера.
    """
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    app.router.add_get('/ping', handle_health_check)

    def cors_headers(origin):
        """Возвращает CORS заголовки для разрешённого origin"""
        return {
            'Access-Control-Allow-Origin': origin or '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-CSRF-Token',
        }

    # Общий список разрешённых origins
    def get_allowed_origins():
        return os.getenv('ALLOWED_ORIGINS', 'https://kovka007.vercel.app,http://localhost:5173,http://localhost:3000,http://localhost:4173')

    async def handle_options(request):
        """Обработчик preflight OPTIONS запросов"""
        origin = request.headers.get('origin', '')
        allowed_list = [o.strip() for o in get_allowed_origins().split(',') if o.strip()]
        if not origin or origin in allowed_list:
            return web.Response(status=200, headers=cors_headers(origin))
        logger.warning(f"CORS preflight rejected for origin: {origin}")
        return web.Response(status=403, text='Forbidden')

    app.router.add_options('/submit_order', handle_options)
    app.router.add_options('/upload_screenshot', handle_options)

    async def handle_submit_order(request):
        try:
            origin = request.headers.get('origin', '')
            allowed_list = [o.strip() for o in get_allowed_origins().split(',') if o.strip()]
            headers = cors_headers(origin) if (not origin or origin in allowed_list) else {}
            
            if origin and origin not in allowed_list:
                logger.warning(f"Rejected order from origin: {origin}")
                return web.Response(status=403, text='Forbidden', headers=headers)

            data = await request.json()
            logger.info(f"📨 Received browser order via HTTP endpoint: id={data.get('id')}")

            # Извлекаем скриншот из payload (если есть)
            screenshot_b64 = data.pop('screenshot', None)
            # Также проверяем хранилище скриншотов (для Telegram WebApp заказов)
            if not screenshot_b64 and data.get('id'):
                screenshot_b64 = get_screenshot(data['id'])

            # Extract contact fields if provided
            customer_name = data.get('name') or data.get('customer') or 'Браузерный пользователь'
            customer_phone = data.get('phone') or 'Не указан'
            comment = data.get('comment') or data.get('user_comment') or ''

            # Format message using existing helper
            try:
                order_payload = data
                msg = format_order_message(order_payload, customer_name, '', customer_phone, comment, 1, for_admin=True)
                # Добавляем пометку что заявка из браузера
                msg = "🌐 <b>ЗАЯВКА ИЗ БРАУЗЕРА</b>\n\n" + msg
            except Exception as e:
                logger.error(f"Error formatting order message: {e}")
                msg = f"🌐 <b>ЗАЯВКА ИЗ БРАУЗЕРА</b>\n\nНовая заявка (не удалось распарсить):\n{json.dumps(data, ensure_ascii=False)[:400]}"

            # Send to admin channel AND admin user (с фото если есть)
            if application and application.bot:
                try:
                    await send_order_with_photo(application.bot, ADMIN_CHANNEL_ID, msg, screenshot_b64)
                    logger.info(f"✅ Sent browser order to admin channel {ADMIN_CHANNEL_ID}")
                except Exception as e:
                    logger.error(f"Failed to send order to admin channel: {e}")
                    try:
                        await send_order_with_photo(application.bot, ADMIN_USER_ID, msg, screenshot_b64)
                        logger.info(f"✅ Sent browser order to admin user {ADMIN_USER_ID} (fallback)")
                    except Exception as e2:
                        logger.error(f"Failed to send order to admin user: {e2}")
            else:
                logger.warning("No telegram application available to forward order")

            return web.json_response({'ok': True}, headers=headers)
        except Exception as e:
            logger.error(f"Exception in submit_order handler: {e}", exc_info=True)
            return web.json_response({'ok': False, 'error': str(e)}, status=500, headers=cors_headers(request.headers.get('origin', '')))

    app.router.add_post('/submit_order', handle_submit_order)

    async def handle_upload_screenshot(request):
        """Принимает скриншот 3D сцены для прикрепления к заказу (из Telegram WebApp)"""
        try:
            origin = request.headers.get('origin', '')
            allowed_list = [o.strip() for o in get_allowed_origins().split(',') if o.strip()]
            headers = cors_headers(origin) if (not origin or origin in allowed_list) else {}
            
            if origin and origin not in allowed_list:
                return web.Response(status=403, text='Forbidden', headers=headers)

            data = await request.json()
            order_id = data.get('order_id')
            screenshot = data.get('screenshot')
            
            if order_id and screenshot:
                store_screenshot(order_id, screenshot)
                logger.info(f"📸 Screenshot stored for order {order_id} ({len(screenshot)} chars)")
                return web.json_response({'ok': True}, headers=headers)
            else:
                return web.json_response({'ok': False, 'error': 'Missing order_id or screenshot'}, status=400, headers=headers)
        except Exception as e:
            logger.error(f"Exception in upload_screenshot: {e}", exc_info=True)
            return web.json_response({'ok': False, 'error': str(e)}, status=500, headers=cors_headers(request.headers.get('origin', '')))

    app.router.add_post('/upload_screenshot', handle_upload_screenshot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 HTTP сервер запущен на порту {port}")
    return runner

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

class WebAppDataFilter(filters.MessageFilter):
    def filter(self, message) -> bool:
        has_web_app = bool(getattr(message, "web_app_data", None))
        if has_web_app:
            logger.info(f"✅ WebApp data detected from user {message.from_user.id}")
        return has_web_app

async def get_main_keyboard():
    web_app_url = "https://kovka007.vercel.app"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏗 Открыть конструктор", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("📄 Мой заказ"), KeyboardButton("✏️ Добавить пожелания/фото")],
        [KeyboardButton("📚 Как пользоваться"), KeyboardButton("🔒 Политика и соглашение")],
        [KeyboardButton("📞 Отправить телефон и оформить", request_contact=True)]
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

    # Нагрузки (если есть)
    loads = order.get('loads', {})
    loads_str = ""
    if loads:
        loads_str = (
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"❄️ <b>Снеговая:</b> {loads.get('snow', 0)} кг/м²\n"
            f"💨 <b>Ветровая:</b> {loads.get('wind', 0)} Па\n"
            f"⚖️ <b>Общая:</b> {loads.get('total', 0)} кг/м²\n"
            f"📍 <b>Регион:</b> {order.get('region', 'Не указан')}\n"
        )

    # Ворота (если есть)
    gate = order.get('gate', {})
    gate_str = ""
    if gate and gate.get('type') and gate.get('type') != 'none':
        gate_type = GATE_TYPES.get(gate.get('type'), gate.get('type'))
        gate_filling = GATE_FILLINGS.get(gate.get('filling'), gate.get('filling'))
        gate_frame_color = gate.get('frameColor') or gate.get('frame_color') or 'Не указан'
        gate_panel_color = gate.get('panelColor') or gate.get('panel_color') or 'Не указан'
        gate_str = (
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🚗 <b>ВОРОТА:</b>\n"
            f"📐 <b>Тип:</b> {gate_type}\n"
            f"📏 <b>Размер:</b> {gate.get('width', 4)}×{gate.get('height', 2)} м\n"
            f"🔲 <b>Заполнение:</b> {gate_filling}\n"
            f"🎨 <b>Цвет рамы:</b> {gate_frame_color}\n"
            f"🎨 <b>Цвет полотна:</b> {gate_panel_color}\n"
            f"{'🚶 Калитка: Да' if gate.get('wicket') else '🚶 Калитка: Нет'}\n"
            f"{'🤖 Автоматика: Да' if gate.get('automation') else '🤖 Автоматика: Нет'}\n"
        )

    # Цены
    price_navyes = order.get('price', 0)
    price_gate = order.get('price_gate', 0)
    price_total = order.get('price_total', price_navyes + price_gate)
    only_gates = order.get('only_gates', False)
    
    if only_gates:
        price_str = f"🚫 <b>БЕЗ НАВЕСА (только ворота)</b>\n🚗 <b>ВОРОТА: {price_gate:,} руб.</b>\n💵 <b>ИТОГО: {price_gate:,} руб.</b>"
    else:
        price_str = f"💰 <b>НАВЕС: {price_navyes:,} руб.</b>"
        if price_gate > 0:
            price_str += f"\n🚗 <b>ВОРОТА: {price_gate:,} руб.</b>"
            price_str += f"\n💵 <b>ИТОГО: {price_total:,} руб.</b>"

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
        f"{loads_str}"
        f"{gate_str}"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"{price_str}"
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

# === ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ И ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ ===

async def show_privacy_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    policy_text = (
        "🔒 <b>Политика конфиденциальности</b>\n"
        "Мы собираем только данные, необходимые для расчета и оформления заявки: "
        "параметры проекта, контактный телефон, имя, комментарии и прикрепленные файлы.\n"
        "Данные используются для связи с вами, подготовки коммерческого предложения "
        "и улучшения сервиса. Мы не продаем данные третьим лицам. "
        "Передача возможна только подрядчикам, участвующим в выполнении заявки.\n"
        "Вы можете запросить удаление или корректировку данных, написав в поддержку.\n\n"
        "📝 <b>Пользовательское соглашение</b>\n"
        "Сервис предоставляет расчет ориентировочной стоимости и возможность отправки заявки. "
        "Итоговые условия и цена согласуются менеджером после уточнения деталей.\n"
        "Пользователь подтверждает корректность введенных данных и согласие на связь. "
        "Материалы (тексты, изображения) сервиса защищены авторским правом.\n\n"
        "📩 <b>Контакты</b>: +7 (927) 799-11-55, https://kovka007.ru"
    )
    await update.message.reply_text(policy_text, parse_mode=ParseMode.HTML)

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
        "🔹 <code>/export</code> - Экспорт базы\n"
        "🔹 <code>/clean</code> - Очистить чат\n"
        "🔹 <code>/import_db</code> - Загрузить базу заказов"
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
    if not update.callback_query:
        return

    data = update.callback_query.data
    await update.callback_query.answer()

    if data == "check_sub":
        if await check_subscription(update, context):
            try:
                if update.callback_query.message:
                    await update.callback_query.message.delete()
            except Exception as e:
                logger.error(f"Ошибка удаления сообщения: {e}")
            await start(update, context)
        else:
            await update.callback_query.answer("Нет подписки!", show_alert=True)

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

    elif text == "🔒 Политика и соглашение":
        await show_privacy_terms(update, context)

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
        if not update.effective_message or not update.effective_message.web_app_data:
            logger.warning("⚠️ No WebApp data in message")
            return
        
        data_raw = update.effective_message.web_app_data.data
        logger.info(f"📨 Received WebApp data ({len(data_raw)} bytes) from {update.effective_user.id}")
        
        data = json.loads(data_raw)
        context.user_data['order_data'] = data

        if 'user_comment' not in context.user_data: 
            context.user_data['user_comment'] = 'Нет пожеланий'

        # Проверяем наличие скриншота в хранилище (загружен заранее через /upload_screenshot)
        screenshot_b64 = get_screenshot(data.get('id', '')) if data.get('id') else None
        if screenshot_b64:
            context.user_data['order_screenshot'] = screenshot_b64
            logger.info(f"📸 Screenshot found for order {data.get('id')}")

        # Отправляем пользователю заказ с фото (если есть скриншот)
        order_msg = format_order_message(data, update.effective_user.first_name, "", "", "", 1, for_admin=False)
        if screenshot_b64:
            await send_order_with_photo(context.bot, update.effective_chat.id, order_msg, screenshot_b64)
        else:
            await update.message.reply_text(order_msg, parse_mode=ParseMode.HTML)

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
        logger.info(f"✅ Order processed for user {update.effective_user.id}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parse error: {e}")
        await update.message.reply_text("❌ Ошибка парсинга данных конструктора.")
    except Exception as e:
        logger.error(f"❌ WebApp handler error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка обработки: {str(e)[:100]}")

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

    # Скриншот 3D сцены (если был загружен ранее через WebApp)
    order_screenshot = context.user_data.get('order_screenshot')

    try:
        if photos:
            # Отправляем фото отдельным постом
            media = [InputMediaPhoto(media=pid) for pid in photos]
            await context.bot.send_media_group(chat_id=ADMIN_CHANNEL_ID, media=media)

        # Отправляем заявку со скриншотом 3D сцены (или только текстом)
        await send_order_with_photo(context.bot, ADMIN_CHANNEL_ID, report, order_screenshot)
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
    application.add_handler(MessageHandler(WebAppDataFilter(), handle_webapp_data))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))

    # Запускаем HTTP сервер для health checks и endpoint'ов на порту от Render
    http_runner = await start_http_server(PORT, application)

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