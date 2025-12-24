#!/usr/bin/env python3

"""
AI2BIZ Telegram Bot - ADVANCED VERSION V5.3
- Проверка подписки БЕЗ реальной верификации (просто кнопка)
- Правильное удаление /cancel (сохраняет приветствие)
- Две отдельных анкеты (файлы + консультация)
- ДВА ТИПА ФАЙЛОВ: 5 ошибок менеджеров или Чек-лист (выбор пользователя)
- Улучшенный markdown с эмодзи
"""

import os
import re
import telebot
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TOKEN")
ZOOM_LINK = os.getenv("ZOOM_LINK", "https://zoom.us/YOUR_ZOOM_LINK")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_NAME = "it_ai2biz"
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

FILE_5_MISTAKES = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/5%20mistakes%20of%20managers.pdf"
FILE_CHECKLIST = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check%20list%2010%20ways.pdf"

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_data = {}
user_state = {}
user_message_history = {}
welcome_message_ids = {}
user_subscribed = {}

# ===== ВАЛИДАЦИЯ =====
def is_valid_email(email):
    """Проверяет валидность email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_telegram(telegram):
    """Проверяет валидность Telegram"""
    telegram = telegram.strip()
    if telegram.startswith('@'):
        return len(telegram) > 1 and telegram.replace('@', '').replace('_', '').isalnum()
    elif 't.me/' in telegram:
        return True
    else:
        return False

def is_valid_name(name):
    """Проверяет валидность имени"""
    name = name.strip()
    return len(name) >= 2 and len(name) <= 50

def safe_send_message(chat_id, text, parse_mode="HTML", **kwargs):
    """Безопасно отправляет сообщение с автоматическим выбором parse_mode"""
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, **kwargs)
    except telebot.apihelper.ApiException as e:
        if "can't parse entities" in str(e):
            text_clean = text.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            text_clean = text_clean.replace('<u>', '').replace('</u>', '')
            return bot.send_message(chat_id, text_clean, **kwargs)
        else:
            raise

# ===== SUPABASE =====
def save_to_supabase(table, data):
    """Сохраняет в Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"⚠️ Supabase не настроена")
        return False
    try:
        import requests
        headers = {
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        response = requests.post(url, json=data, headers=headers)
        if response.status_code in [200, 201]:
            print(f"✅ Сохранено в {table}")
            return True
        else:
            print(f"❌ Ошибка Supabase ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def log_action(user_id, name, action, details=""):
    """Логирует в таблицу stats"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {action} | {name} ({user_id})")
    save_to_supabase("stats", {
        "user_id": user_id,
        "name": name,
        "action": action,
        "details": details
    })

def save_lead_files(user_id, lead_data):
    """Сохраняет лид файлов в таблицу leads_files"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '300k' in revenue or '1m' in revenue:
        segment = "medium"
    elif 'large' in revenue or '5m' in revenue:
        segment = "large"
    else:
        segment = "enterprise"

    data = {
        "user_id": user_id,
        "name": lead_data.get('name', ''),
        "business_duration": lead_data.get('business_duration', ''),
        "telegram": lead_data.get('telegram', ''),
        "business": lead_data.get('business', ''),
        "revenue": lead_data.get('revenue', ''),
        "file_type": lead_data.get('file_type', ''),
        "segment": segment
    }
    save_to_supabase("leads_files", data)

def save_lead_consultation(user_id, lead_data):
    """Сохраняет лид консультации в таблицу leads_consultation"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '300k' in revenue or '1m' in revenue:
        segment = "medium"
    elif 'large' in revenue or '5m' in revenue:
        segment = "large"
    else:
        segment = "enterprise"

    data = {
        "user_id": user_id,
        "name": lead_data.get('name', ''),
        "business_duration": lead_data.get('business_duration', ''),
        "telegram": lead_data.get('telegram', ''),
        "email": lead_data.get('email', ''),
        "business": lead_data.get('business', ''),
        "revenue": lead_data.get('revenue', ''),
        "participants": lead_data.get('participants', ''),
        "zoom_time": lead_data.get('zoom_time', ''),
        "segment": segment
    }
    save_to_supabase("leads_consultation", data)
    save_to_supabase("segments", {
        "user_id": user_id,
        "segment": segment
    })

def notify_admin_consultation(lead_data):
    """Отправляет уведомление администратору"""
    if ADMIN_CHAT_ID == 0:
        print("⚠️ ADMIN_CHAT_ID не установлен")
        return

    segment = determine_segment(lead_data.get('revenue', ''))
    notification = f"""🔔 <b>НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ!</b>

👤 <b>Имя:</b> {lead_data.get('name')}
⏱️ <b>Время функционирования бизнеса:</b> {lead_data.get('business_duration')}
📱 <b>Telegram:</b> {lead_data.get('telegram')}
📧 <b>Email:</b> {lead_data.get('email')}
🏢 <b>Бизнес:</b> {lead_data.get('business')}
💰 <b>Выручка:</b> {lead_data.get('revenue')}
👥 <b>На созвоне:</b> {lead_data.get('participants')}
🎥 <b>Время Zoom:</b> {lead_data.get('zoom_time')}
📊 <b>Сегмент:</b> {segment.upper()}
⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    try:
        safe_send_message(ADMIN_CHAT_ID, notification, parse_mode="HTML")
        print(f"✅ Уведомление отправлено админу")
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")

def determine_segment(revenue):
    """Определяет сегмент по выручке"""
    revenue = str(revenue).lower()
    if 'small' in revenue or '< 300k' in revenue or '<300k' in revenue:
        return "small"
    elif 'medium' in revenue or '300k-1m' in revenue:
        return "medium"
    elif 'large' in revenue or '1m-5m' in revenue:
        return "large"
    else:
        return "enterprise"

def save_message_history(user_id, message_id):
    """Сохраняет ID сообщения для последующего удаления"""
    if user_id not in user_message_history:
        user_message_history[user_id] = []
    user_message_history[user_id].append(message_id)

def delete_messages_after_welcome(chat_id, user_id):
    """Удаляет сообщения после приветственного сообщения (не включая его)"""
    if user_id not in welcome_message_ids:
        print(f"⚠️ Приветствие для {user_id} не найдено")
        return

    welcome_msg_id = welcome_message_ids[user_id]
    deleted_count = 0
    
    if user_id in user_message_history:
        messages_to_delete = [msg_id for msg_id in user_message_history[user_id] if msg_id > welcome_msg_id]
        
        for msg_id in messages_to_delete:
            try:
                bot.delete_message(chat_id, msg_id)
                deleted_count += 1
            except Exception as e:
                print(f"⚠️ Не удалось удалить сообщение {msg_id}: {e}")
        
        user_message_history[user_id] = [welcome_msg_id]
        print(f"✅ Удалено {deleted_count} сообщений для пользователя {user_id}")

# ===== WEBHOOK =====
@app.route('/telegram-webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        if json_data:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return "ERROR", 400

# ===== /START =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    print(f"🆔 User ID: {user_id}")
    log_action(user_id, user_name, "START_COMMAND", "Пользователь запустил бота")

    welcome_text = f"""👋 <b>Привет, {user_name}!</b>

Я бот <b>AI2BIZ</b> - помогу получить материалы по автоматизации продаж и запишу тебя на консультацию.

<b>Что я могу:</b>
1️⃣ Отправить <b>полезные материалы</b> по автоматизации бизнеса
2️⃣ <b>Записать на консультацию</b> со специалистом команды AI2BIZ

<b>📚 Материалы помогут:</b>
✅ Увеличить конверсию на <b>150-300%</b>
✅ Автоматизировать работу менеджеров
✅ Не терять <b>50% лидов</b>

<b>🎯 Реальные результаты AI2BIZ:</b>
✅ Увеличение конверсии на <b>150-300%</b>
✅ Сокращение времени обработки лидов в <b>5 раз</b>
✅ Окупаемость инвестиций за <b>1 неделю</b>

<b>📝 Выбери что тебе нужно:</b>
• Напиши <b>"файлы"</b> - получить материалы
• Напиши <b>"консультация"</b> - записаться на консвон

💡 <b>/cancel</b> - вернуться в главное меню"""

    msg = safe_send_message(message.chat.id, welcome_text, parse_mode="HTML")
    welcome_message_ids[user_id] = msg.message_id
    save_message_history(user_id, msg.message_id)

# ===== /CANCEL =====
@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    """Отменяет текущий процесс и возвращает в главное меню"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Очищаем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    if user_id in user_state:
        del user_state[user_id]

    # Удаляем сообщения после приветствия (само приветствие сохраняется)
    delete_messages_after_welcome(chat_id, user_id)

    # Отправляем главное меню
    send_welcome(message)

# ===== ОСНОВНАЯ ОБРАБОТКА =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    text = message.text.lower().strip()
    chat_id = message.chat.id

    # Сохраняем сообщение пользователя
    save_message_history(user_id, message.message_id)

    # ФАЙЛЫ
    if any(word in text for word in ["файлы", "материал", "документ", "pdf"]):
        # Показываем требование подписки БЕЗ реальной проверки
        subscription_text = """🔐 <b>Внимание!</b>

Чтобы получить материалы, нужно подписаться на наш канал:
<b>@it_ai2biz</b>

📌 <b>Почему это важно?</b>
Мы делимся там эксклюзивными материалами и кейсами по автоматизации, которые помогают бизнесу увеличить конверсию на <b>150-300%</b>

<b>Без подписки на канал забрать материалы не получится.</b>

После подписки нажми кнопку ниже 👇"""

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ Я подписался", callback_data="subscribed"))

        msg = safe_send_message(chat_id, subscription_text, parse_mode="HTML", reply_markup=markup)
        save_message_history(user_id, msg.message_id)
        return

    # КОНСУЛЬТАЦИЯ
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт", "zoom"]):
        user_state[user_id] = "consultation"
        user_data[user_id] = {}

        consultation_text = """🎯 <b>Запись на консультацию</b>

Отлично! Давайте запишемся на <b>бесплатную консультацию</b> со специалистом AI2BIZ.

Наш эксперт поможет:
✅ Выявить проблемы в вашей воронке продаж
✅ Показать потенциал автоматизации именно для вашего бизнеса
✅ Рассчитать окупаемость внедрения

<b>Начнем! Как тебя зовут?</b>"""

        msg = safe_send_message(chat_id, consultation_text, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)

    # АДМИНИСТРАТОР: РАССЫЛКА
    elif text.startswith('/broadcast_small') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "small", message.text.replace("/broadcast_small ", ""))
    elif text.startswith('/broadcast_medium') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "medium", message.text.replace("/broadcast_medium ", ""))
    elif text.startswith('/broadcast_large') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "large", message.text.replace("/broadcast_large ", ""))
    elif text.startswith('/broadcast_enterprise') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "enterprise", message.text.replace("/broadcast_enterprise ", ""))

    else:
        help_text = """❓ <b>Команда не понята</b>

Используй:
📄 <b>файлы</b> - получить материалы по автоматизации
📞 <b>консультация</b> - записаться на консультацию
🔄 <b>/cancel</b> - вернуться в меню"""

        msg = safe_send_message(chat_id, help_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)

# ===== CALLBACK QUERIES (кнопки) =====
@bot.callback_query_handler(func=lambda call: call.data == "subscribed")
def handle_subscription(call):
    """Обработка нажатия кнопки 'Я подписался' - БЕЗ реальной проверки"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    # Просто активируем процесс получения файлов БЕЗ проверки
    bot.answer_callback_query(call.id, "✅ Спасибо за подписку!", show_alert=False)

    user_state[user_id] = "files"
    user_data[user_id] = {}

    file_selection_text = """✅ <b>Спасибо за подписку!</b>

Теперь выбери, какой материал тебе нужен:"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("📄 5 ошибок менеджеров")
    markup.add("✅ Чек-лист")

    msg = safe_send_message(chat_id, file_selection_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, handle_file_selection, user_id)

# ===== ВЫБОР ФАЙЛА =====
def handle_file_selection(message, user_id):
    """Обрабатывает выбор файла"""
    text = message.text.lower().strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if "ошибок" in text or "менеджеров" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: 5 ошибок менеджеров")
    elif "чек" in text or "лист" in text:
        user_data[user_id]["file_type"] = "checklist"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: Чек-лист")
    else:
        invalid_choice_text = """⚠️ <b>Некорректный выбор</b>

Пожалуйста, выбери один из предложенных вариантов:"""

        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("📄 5 ошибок менеджеров")
        markup.add("✅ Чек-лист")

        msg = safe_send_message(chat_id, invalid_choice_text, parse_mode="HTML", reply_markup=markup)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return

    form_text = """📝 <b>Заполним краткую анкету</b>

Это займет всего <b>1 минуту</b>, но поможет нам лучше понять твой бизнес.

<b>Как тебя зовут?</b>
(Минимум 2 буквы)"""

    msg = safe_send_message(chat_id, form_text, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_name_check, user_id)

# ===== АНКЕТА ФАЙЛОВ =====
def ask_files_name_check(message, user_id):
    """Проверяет имя перед сохранением"""
    name = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = """❌ <b>Некорректное имя</b>

Имя должно быть <b>от 2 до 50 символов</b>. Попробуй ещё раз:"""

        msg = safe_send_message(chat_id, error_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_name_check, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = """📅 <b>Сколько времени функционирует ваш бизнес?</b>"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business_duration, user_id)

def ask_files_business_duration(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = """📱 <b>Твой Telegram?</b>

Напиши в формате:
• <b>@username</b>
• или <b>https://t.me/username</b>"""

    msg = safe_send_message(chat_id, telegram_text, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)

def ask_files_telegram_check(message, user_id):
    """Проверяет Telegram перед сохранением"""
    telegram = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = """❌ <b>Некорректный Telegram</b>

Используй формат:
• <b>@username</b>
• или <b>https://t.me/username</b>"""

        msg = safe_send_message(chat_id, error_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    business_text = """🏢 <b>Расскажи о своём бизнесе</b>

<i>Напиши:</i>
• Ниша/индустрия
• Основной продукт
• Главные проблемы в продажах"""

    msg = safe_send_message(chat_id, business_text, parse_mode="HTML")
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business, user_id)

def ask_files_business(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()

    revenue_text = """💰 <b>Выручка в месяц?</b>"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_files, user_id)

def finish_form_files(message, user_id):
    user_data[user_id]["revenue"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    save_lead_files(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_FILES", f"Заявка на файлы: {app.get('file_type')}")

    sending_text = """⏳ <b>Отправляю твой файл...</b>"""

    msg = safe_send_message(chat_id, sending_text, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)

    try:
        if app.get('file_type') == "5_mistakes":
            file_url = FILE_5_MISTAKES
            file_title = "5 ошибок менеджеров"
            file_description = """📄 <b>5 ошибок менеджеров, из-за которых теряются 50% лидов</b>

<b>Что внутри:</b>
✅ Ошибка 1: Медленный ответ на лид (потеря 30% заявок)
✅ Ошибка 2: Отсутствие системы квалификации (потеря 15% хороших клиентов)
✅ Ошибка 3: Нет автоматизации (100+ часов в месяц на рутину)
✅ Ошибка 4: Отсутствие CRM (потеря истории взаимодействия)
✅ Ошибка 5: Нет контроля и аналитики (слепое управление)

<b>Результат после исправления:</b>
💎 Увеличение конверсии на <b>150-300%</b>
💎 Сокращение времени обработки в <b>5 раз</b>
💎 Окупаемость за <b>1 неделю</b>

<b>Как это работает в реальности?</b>
Мы помогаем компаниям внедрить автоворонки в Telegram и интеграцию с CRM. Кейс: компания увеличила выручку на 400% за 3 месяца.

🎯 <b>Хочешь получить такой же результат?</b>
Запишись на бесплатную консультацию - расскажу, как это работает именно в твоем бизнесе!"""
        else:
            file_url = FILE_CHECKLIST
            file_title = "Чек-лист"
            file_description = """✅ <b>10 способов обнаружить, теряете ли вы лидов</b>

<b>Что это дает:</b>
✅ Быстрая диагностика проблем в продажах (10 минут)
✅ Выявление "дырявых мест" в воронке
✅ Оценка потерь в деньгах
✅ Четкий план действий для исправления

<b>Проверьте свою воронку:</b>
• Скорость ответа на лид
• Система квалификации контактов
• Наличие CRM и аналитики
• Уровень автоматизации процессов
• Мотивация и контроль менеджеров

<b>После диагностики:</b>
💡 Вы поймете, где теряются лиды
💡 Узнаете, сколько денег вы теряете в месяц
💡 Получите четкую дорожную карту улучшений

🎯 <b>Готов получить консультацию?</b>
Запишись на звонок со специалистом - разберем именно вашу ситуацию!"""

        doc_msg = bot.send_document(
            chat_id,
            file_url,
            caption=file_description,
            parse_mode="HTML"
        )
        save_message_history(user_id, doc_msg.message_id)
        log_action(user_id, app.get('name'), "DOWNLOAD_FILES", f"Получил файл: {app.get('file_type')}")

        consultation_offer = """🎉 <b>Файл отправлен!</b>

<b>Что дальше?</b>
Этот материал показывает <b>проблему</b>, но реальные результаты начинаются с <b>внедрения решений</b>.

<b>💎 Наши результаты:</b>
✅ Увеличение конверсии на <b>150-300%</b>
✅ Сокращение времени обработки в <b>5 раз</b>
✅ Окупаемость за <b>1 неделю</b>

<b>🚀 На консультации мы разберем:</b>
• Какие процессы в вашем бизнесе можно автоматизировать
• На сколько % вырастет выручка после внедрения
• Сколько стоит решение именно для вас
• Когда мы сможем запустить (обычно за 2 недели)

<b>Запишись на бесплатную консультацию!</b>
Напиши <b>"консультация"</b> и наш специалист свяжется с тобой в течение часа.

📞 Твой спец ждет! 👨‍💼"""

        msg = safe_send_message(chat_id, consultation_offer, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)

    except Exception as e:
        print(f"Error: {str(e)}")
        error_msg = safe_send_message(chat_id, f"❌ Ошибка при отправке файла: {str(e)}")
        save_message_history(user_id, error_msg.message_id)

# ===== АНКЕТА КОНСУЛЬТАЦИИ =====
def ask_consultation_name(message, user_id):
    """Проверяет имя для консультации"""
    name = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = """❌ <b>Некорректное имя</b>

Имя должно быть <b>от 2 до 50 символов</b>. Попробуй ещё раз:"""

        msg = safe_send_message(chat_id, error_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = """📅 <b>Сколько времени функционирует ваш бизнес?</b>"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business_duration, user_id)

def ask_consultation_business_duration(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = """📱 <b>Твой Telegram?</b>

Напиши в формате:
• <b>@username</b>
• или <b>https://t.me/username</b>"""

    msg = safe_send_message(chat_id, telegram_text, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)

def ask_consultation_telegram_check(message, user_id):
    """Проверяет Telegram для консультации"""
    telegram = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = """❌ <b>Некорректный Telegram</b>

Используй формат:
• <b>@username</b>
• или <b>https://t.me/username</b>"""

        msg = safe_send_message(chat_id, error_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    email_text = """📧 <b>Email адрес?</b>

<i>Пример: name@example.com</i>"""

    msg = safe_send_message(chat_id, email_text, parse_mode="HTML")
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)

def ask_consultation_email_check(message, user_id):
    """Проверяет Email перед сохранением"""
    email = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_email(email):
        error_text = """❌ <b>Некорректный Email</b>

Используй формат: <b>name@example.com</b>"""

        msg = safe_send_message(chat_id, error_text, parse_mode="HTML")
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)
        return

    user_data[user_id]["email"] = email

    business_text = """🏢 <b>Расскажи о своём бизнесе</b>

<i>Напиши:</i>
• Ниша/индустрия
• Основной продукт/услуга
• Выручка в месяц
• Главные проблемы в продажах"""

    msg = safe_send_message(chat_id, business_text, parse_mode="HTML")
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business, user_id)

def ask_consultation_business(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()

    revenue_text = """💰 <b>Выручка в месяц?</b>"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_revenue, user_id)

def ask_consultation_revenue(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["revenue"] = message.text

    participants_text = """👥 <b>Кто будет на созвоне?</b>

(Это влияет на график и содержание консультации)"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Я один", "С бизнес партнером")
    markup.add("Я не принимаю решений в компании")

    msg = safe_send_message(chat_id, participants_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_participants, user_id)

def ask_consultation_participants(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["participants"] = message.text

    time_text = """🎥 <b>Когда будет удобно выйти в Zoom?</b>"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Завтра (9:00 - 12:00)", "Завтра (12:00 - 18:00)")
    markup.add("После завтра", "В выходные")

    msg = safe_send_message(chat_id, time_text, parse_mode="HTML", reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_consultation, user_id)

def finish_form_consultation(message, user_id):
    user_data[user_id]["zoom_time"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    save_lead_consultation(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_CONSULTATION", "Заявка на консультацию")
    notify_admin_consultation(app)

    confirmation = f"""✅ <b>Спасибо! Заявка принята.</b>

<b>Твои данные:</b>
📝 Имя: {app.get('name')}
⏱️ Время функционирования: {app.get('business_duration')}
📱 Telegram: {app.get('telegram')}
📧 Email: {app.get('email')}

<b>Предпочитаемое время созвона:</b>
🕐 {app.get('zoom_time')}

<b>Что дальше?</b>
Наш специалист свяжется с тобой в <b>Telegram</b> в течение <b>часа</b> и согласует точное время встречи на Zoom.

<b>На консультации мы разберем:</b>
✅ Текущую ситуацию в вашем бизнесе
✅ Проблемы в воронке продаж
✅ Потенциал роста после автоматизации
✅ Стоимость и сроки внедрения решения

<b>🙌 Спасибо, что выбрал AI2BIZ!</b>
Подпишись на канал для эксклюзивных материалов: <b>@it_ai2biz</b>"""

    msg = safe_send_message(chat_id, confirmation, parse_mode="HTML", reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)

# ===== РАССЫЛКИ (только для админа) =====
def broadcast_by_segment(admin_id, segment, message_text):
    """Рассылка определённому сегменту"""
    if not message_text:
        safe_send_message(admin_id, "Укажите текст рассылки\n\nПример: /broadcast_small Привет, это рассылка!")
        return

    try:
        import requests
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/segments?segment=eq.{segment}"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            safe_send_message(admin_id, f"Ошибка получения списка: {response.text}")
            return

        users = response.json()
        count = 0
        for user_obj in users:
            try:
                safe_send_message(user_obj['user_id'], message_text, parse_mode="HTML")
                count += 1
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_obj['user_id']}: {e}")

        safe_send_message(admin_id, f"✅ Рассылка отправлена <b>{count}</b> пользователям сегмента <b>{segment.upper()}</b>", parse_mode="HTML")
    except Exception as e:
        safe_send_message(admin_id, f"❌ Ошибка: {str(e)}")

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    return """
    <h1>AI2BIZ Telegram Bot V5.3</h1>
    <p><strong>Статус:</strong> Активен и готов к использованию</p>
    <p><strong>Основной функционал:</strong></p>
    <ul>
        <li>Требование подписки на канал @it_ai2biz (без реальной проверки)</li>
        <li>Отправка двух типов файлов (5 ошибок / Чек-лист)</li>
        <li>Система записи на консультацию</li>
        <li>Интеграция с Supabase для сохранения лидов</li>
        <li>Рассылка по сегментам для администратора</li>
        <li>Правильное удаление сообщений при /cancel</li>
    </ul>
    """

# ===== ЗАПУСК БОТА =====
if __name__ == '__main__':
    print("🤖 Бот AI2BIZ V5.3 запущен!")
    print(f"🔐 Проверка конфигурации:")
    print(f"✓ TOKEN: {'Установлен' if TOKEN else '❌ НЕ УСТАНОВЛЕН'}")
    print(f"✓ SUPABASE_URL: {'Установлен' if SUPABASE_URL else '⚠️ Не установлен (логирование не будет)'}")
    print(f"✓ ADMIN_CHAT_ID: {'Установлен' if ADMIN_CHAT_ID != 0 else '⚠️ Не установлен'}")
    
    # Запуск Flask
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
