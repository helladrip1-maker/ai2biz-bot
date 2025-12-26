#!/usr/bin/env python3

"""
AI2BIZ Telegram Bot - VERSION V6.0 FINAL
- ✅ ПОЛНОСТЬЮ ИСПРАВЛЕНА команда /cancel - теперь работает из любого состояния
- ✅ Команда /help с контактом поддержки
- ✅ Исправлены все ошибки парсинга
- ✅ Оптимизированный код
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
    return False

def is_valid_name(name):
    """Проверяет валидность имени"""
    name = name.strip()
    return 2 <= len(name) <= 50

def safe_send_message(chat_id, text, parse_mode=None, **kwargs):
    """Безопасно отправляет сообщение без parse_mode"""
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return bot.send_message(chat_id, text, **kwargs)

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
    """Сохраняет лид файлов"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '1m' in revenue:
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
    """Сохраняет лид консультации"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '1m' in revenue:
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
    save_to_supabase("segments", {"user_id": user_id, "segment": segment})

def notify_admin_consultation(lead_data):
    """Отправляет уведомление администратору"""
    if ADMIN_CHAT_ID == 0:
        print("⚠️ ADMIN_CHAT_ID не установлен")
        return

    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '1m' in revenue:
        segment = "medium"
    elif 'large' in revenue or '5m' in revenue:
        segment = "large"
    else:
        segment = "enterprise"

    notification = f"""🔔 НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ!

👤 Имя: {lead_data.get('name')}
⏱️ Время: {lead_data.get('business_duration')}
📱 Telegram: {lead_data.get('telegram')}
📧 Email: {lead_data.get('email')}
🏢 Бизнес: {lead_data.get('business')}
💰 Выручка: {lead_data.get('revenue')}
👥 На созвоне: {lead_data.get('participants')}
🎥 Zoom: {lead_data.get('zoom_time')}
📊 Сегмент: {segment.upper()}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    try:
        safe_send_message(ADMIN_CHAT_ID, notification)
        print(f"✅ Уведомление отправлено админу")
    except Exception as e:
        print(f"❌ Ошибка уведомления: {e}")

def save_message_history(user_id, message_id):
    """Сохраняет ID сообщения"""
    if user_id not in user_message_history:
        user_message_history[user_id] = []
    user_message_history[user_id].append(message_id)

def delete_messages_after_welcome(chat_id, user_id):
    """Удаляет сообщения после приветствия"""
    if user_id not in welcome_message_ids:
        return

    welcome_msg_id = welcome_message_ids[user_id]
    deleted_count = 0

    if user_id in user_message_history:
        messages_to_delete = [msg_id for msg_id in user_message_history[user_id] if msg_id > welcome_msg_id]
        for msg_id in messages_to_delete:
            try:
                bot.delete_message(chat_id, msg_id)
                deleted_count += 1
            except:
                pass
        user_message_history[user_id] = [welcome_msg_id]
        print(f"✅ Удалено {deleted_count} сообщений")

def reset_user_state(user_id):
    """Очищает состояние пользователя"""
    if user_id in user_data:
        del user_data[user_id]
    if user_id in user_state:
        del user_state[user_id]

def process_cancel_command(message):
    """ВНУТРЕННЯЯ обработка команды /cancel"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Очищаем все обработчики
    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)

    # Отправляем главное меню
    send_welcome_internal(message)

def process_help_command(message):
    """ВНУТРЕННЯЯ обработка команды /help"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)

    help_text = """❓ ПОМОЩЬ И ПОДДЕРЖКА

Если у вас есть вопрос, который бот решить не способен, или вы обнаружили ошибки в работе бота, пишите:

📞 @glore4

Наша команда поддержки поможет вам в течение часа.

Возвращаемся в главное меню..."""

    msg = safe_send_message(chat_id, help_text)
    save_message_history(user_id, msg.message_id)
    send_welcome_internal(message)

def check_for_commands(message):
    """Проверяет команды и обрабатывает их"""
    if not message.text:
        return False

    text = message.text.strip()

    if text == '/cancel':
        process_cancel_command(message)
        return True
    elif text == '/help':
        process_help_command(message)
        return True

    return False

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

# ===== ВНУТРЕННЯЯ функция отправки приветствия =====

def send_welcome_internal(message):
    """Внутренняя функция для отправки приветствия"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    chat_id = message.chat.id

    welcome_text = f"""👋 Привет, {user_name}!

Я бот AI2BIZ - помогу получить материалы по автоматизации продаж и запишу тебя на консультацию.

Что я могу:
1️⃣ Отправить полезные материалы по автоматизации бизнеса
2️⃣ Записать на консультацию со специалистом команды AI2BIZ

Материалы помогут:
✅ Увеличить конверсию на 150-300%
✅ Автоматизировать работу менеджеров
✅ Не терять 50% лидов

Реальные результаты AI2BIZ:
✅ Увеличение конверсии на 150-300%
✅ Сокращение времени обработки лидов в 5 раз
✅ Окупаемость инвестиций за 1 неделю

Выбери что тебе нужно:
• Напиши "файлы" - получить материалы
• Напиши "консультация" - записаться на консвон
• /cancel - вернуться в главное меню
• /help - связаться с поддержкой"""

    msg = safe_send_message(chat_id, welcome_text)
    welcome_message_ids[user_id] = msg.message_id
    save_message_history(user_id, msg.message_id)

# ===== /START =====

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"

    print(f"🆔 User ID: {user_id}")
    log_action(user_id, user_name, "START_COMMAND", "Запуск бота")

    bot.clear_step_handler_by_chat_id(message.chat.id)
    reset_user_state(user_id)
    send_welcome_internal(message)

# ===== /CANCEL =====

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    """Команда /cancel из обычного режима"""
    process_cancel_command(message)

# ===== /HELP =====

@bot.message_handler(commands=['help'])
def help_command(message):
    """Команда /help из обычного режима"""
    process_help_command(message)

# ===== ОСНОВНАЯ ОБРАБОТКА =====

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text.lower().strip()
    chat_id = message.chat.id

    save_message_history(user_id, message.message_id)

    # ФАЙЛЫ
    if any(word in text for word in ["файлы", "материал", "документ", "pdf"]):
        subscription_text = """🔐 Внимание!

Чтобы получить материалы, нужно подписаться на наш канал:

@it_ai2biz

Почему это важно?
Мы делимся там эксклюзивными материалами и кейсами по автоматизации, которые помогают бизнесу увеличить конверсию на 150-300%

Без подписки на канал забрать материалы не получится.

После подписки нажми кнопку ниже"""

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ Я подписался", callback_data="subscribed"))

        msg = safe_send_message(chat_id, subscription_text, reply_markup=markup)
        save_message_history(user_id, msg.message_id)
        return

    # КОНСУЛЬТАЦИЯ
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт", "zoom"]):
        reset_user_state(user_id)
        user_state[user_id] = "consultation"
        user_data[user_id] = {}

        consultation_text = """🎯 Запись на консультацию

Отлично! Давайте запишемся на бесплатную консультацию со специалистом AI2BIZ.

Наш эксперт поможет:
✅ Выявить проблемы в вашей воронке продаж
✅ Показать потенциал автоматизации именно для вашего бизнеса
✅ Рассчитать окупаемость внедрения

Начнем! Как тебя зовут?"""

        msg = safe_send_message(chat_id, consultation_text, reply_markup=telebot.types.ReplyKeyboardRemove())
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)

    # АДМИН: РАССЫЛКИ
    elif text.startswith('/broadcast_small') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "small", message.text.replace("/broadcast_small ", ""))
    elif text.startswith('/broadcast_medium') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "medium", message.text.replace("/broadcast_medium ", ""))
    elif text.startswith('/broadcast_large') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "large", message.text.replace("/broadcast_large ", ""))
    elif text.startswith('/broadcast_enterprise') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "enterprise", message.text.replace("/broadcast_enterprise ", ""))

    else:
        help_text = """❓ Команда не понята

Используй:
📄 файлы - получить материалы
📞 консультация - записаться на консультацию
🔄 /cancel - вернуться в меню
❓ /help - связаться с поддержкой"""

        msg = safe_send_message(chat_id, help_text)
        save_message_history(user_id, msg.message_id)

# ===== CALLBACK =====

@bot.callback_query_handler(func=lambda call: call.data == "subscribed")
def handle_subscription(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    bot.answer_callback_query(call.id, "✅ Спасибо за подписку!", show_alert=False)

    reset_user_state(user_id)
    user_state[user_id] = "files"
    user_data[user_id] = {}

    file_selection_text = """✅ Спасибо за подписку!

Теперь выбери, какой материал тебе нужен:"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("📄 5 ошибок менеджеров")
    markup.add("✅ Чек-лист")

    msg = safe_send_message(chat_id, file_selection_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, handle_file_selection, user_id)

# ===== ФАЙЛЫ =====

def handle_file_selection(message, user_id):
    if check_for_commands(message):
        return

    text = message.text.lower().strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if "ошибок" in text or "менеджеров" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
        log_action(user_id, "", "FILE_SELECTED", "5 ошибок")
    elif "чек" in text or "лист" in text:
        user_data[user_id]["file_type"] = "checklist"
        log_action(user_id, "", "FILE_SELECTED", "Чек-лист")
    else:
        invalid_text = """⚠️ Некорректный выбор

Пожалуйста, выбери один из вариантов:"""

        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("📄 5 ошибок менеджеров")
        markup.add("✅ Чек-лист")

        msg = safe_send_message(chat_id, invalid_text, reply_markup=markup)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return

    form_text = """📝 Заполним краткую анкету

Это займет всего 1 минуту, но поможет нам лучше понять твой бизнес.

Как тебя зовут?
(Минимум 2 буквы)"""

    msg = safe_send_message(chat_id, form_text, reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_name_check, user_id)

def ask_files_name_check(message, user_id):
    if check_for_commands(message):
        return

    name = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = """❌ Некорректное имя

Имя должно быть от 2 до 50 символов. Попробуй ещё раз:"""

        msg = safe_send_message(chat_id, error_text)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_name_check, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = """📅 Сколько времени функционирует ваш бизнес?"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business_duration, user_id)

def ask_files_business_duration(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = """📱 Твой Telegram?

Напиши в формате:
• @username
• или https://t.me/username"""

    msg = safe_send_message(chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)

def ask_files_telegram_check(message, user_id):
    if check_for_commands(message):
        return

    telegram = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = """❌ Некорректный Telegram

Используй формат:
• @username
• или https://t.me/username"""

        msg = safe_send_message(chat_id, error_text)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    business_text = """🏢 Расскажи о своём бизнесе

Напиши:
• Ниша/индустрия
• Основной продукт
• Главные проблемы в продажах"""

    msg = safe_send_message(chat_id, business_text)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business, user_id)

def ask_files_business(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()

    revenue_text = """💰 Выручка в месяц?"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_files, user_id)

def finish_form_files(message, user_id):
    if check_for_commands(message):
        return

    user_data[user_id]["revenue"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id

    save_message_history(user_id, message.message_id)
    save_lead_files(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_FILES", f"Файл: {app.get('file_type')}")

    sending_text = """⏳ Отправляю твой файл..."""
    msg = safe_send_message(chat_id, sending_text, reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)

    try:
        if app.get('file_type') == "5_mistakes":
            file_url = FILE_5_MISTAKES
            file_description = """📄 5 ошибок менеджеров, из-за которых теряются 50% лидов

Что внутри:
✅ Ошибка 1: Медленный ответ на лид (потеря 30% заявок)
✅ Ошибка 2: Отсутствие системы квалификации (потеря 15% хороших клиентов)
✅ Ошибка 3: Нет автоматизации (100+ часов в месяц на рутину)
✅ Ошибка 4: Отсутствие CRM (потеря истории взаимодействия)
✅ Ошибка 5: Нет контроля и аналитики (слепое управление)

Результат после исправления:
💎 Увеличение конверсии на 150-300%
💎 Сокращение времени обработки в 5 раз
💎 Окупаемость за 1 неделю

🎯 Хочешь получить такой же результат?
Запишись на бесплатную консультацию!"""
        else:
            file_url = FILE_CHECKLIST
            file_description = """✅ 10 способов обнаружить, теряете ли вы лидов

Что это дает:
✅ Быстрая диагностика проблем (10 минут)
✅ Выявление дырявых мест в воронке
✅ Оценка потерь в деньгах
✅ Четкий план действий

Проверьте свою воронку:
• Скорость ответа на лид
• Система квалификации контактов
• Наличие CRM и аналитики
• Уровень автоматизации процессов
• Мотивация и контроль менеджеров

🎯 Готов получить консультацию?
Запишись на звонок со специалистом!"""

        doc_msg = bot.send_document(chat_id, file_url, caption=file_description)
        save_message_history(user_id, doc_msg.message_id)
        log_action(user_id, app.get('name'), "DOWNLOAD_FILES", f"Получил: {app.get('file_type')}")

        consultation_offer = """🎉 Файл отправлен!

Что дальше?
Этот материал показывает проблему, но реальные результаты начинаются с внедрения решений.

💎 Наши результаты:
✅ Увеличение конверсии на 150-300%
✅ Сокращение времени обработки в 5 раз
✅ Окупаемость за 1 неделю

Запишись на бесплатную консультацию!
Напиши "консультация" и наш специалист свяжется с тобой в течение часа.

📞 Твой спец ждет!"""

        msg = safe_send_message(chat_id, consultation_offer)
        save_message_history(user_id, msg.message_id)

    except Exception as e:
        print(f"Error: {str(e)}")
        error_msg = safe_send_message(chat_id, f"❌ Ошибка: {str(e)}")
        save_message_history(user_id, error_msg.message_id)

# ===== КОНСУЛЬТАЦИЯ =====

def ask_consultation_name(message, user_id):
    if check_for_commands(message):
        return

    name = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = """❌ Некорректное имя

Имя должно быть от 2 до 50 символов. Попробуй ещё раз:"""

        msg = safe_send_message(chat_id, error_text)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = """📅 Сколько времени функционирует ваш бизнес?"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business_duration, user_id)

def ask_consultation_business_duration(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = """📱 Твой Telegram?

Напиши в формате:
• @username
• или https://t.me/username"""

    msg = safe_send_message(chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)

def ask_consultation_telegram_check(message, user_id):
    if check_for_commands(message):
        return

    telegram = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = """❌ Некорректный Telegram

Используй формат:
• @username
• или https://t.me/username"""

        msg = safe_send_message(chat_id, error_text)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    email_text = """📧 Email адрес?

Пример: name@example.com"""

    msg = safe_send_message(chat_id, email_text)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)

def ask_consultation_email_check(message, user_id):
    if check_for_commands(message):
        return

    email = message.text.strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_email(email):
        error_text = """❌ Некорректный Email

Используй формат: name@example.com"""

        msg = safe_send_message(chat_id, error_text)
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)
        return

    user_data[user_id]["email"] = email

    business_text = """🏢 Расскажи о своём бизнесе

Напиши:
• Ниша/индустрия
• Основной продукт/услуга
• Выручка в месяц
• Главные проблемы в продажах"""

    msg = safe_send_message(chat_id, business_text)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business, user_id)

def ask_consultation_business(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()

    revenue_text = """💰 Выручка в месяц?"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_revenue, user_id)

def ask_consultation_revenue(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["revenue"] = message.text

    participants_text = """👥 Кто будет на созвоне?

(Это влияет на график и содержание консультации)"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Я один", "С бизнес партнером")
    markup.add("Я не принимаю решений в компании")

    msg = safe_send_message(chat_id, participants_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_participants, user_id)

def ask_consultation_participants(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["participants"] = message.text

    time_text = """🎥 Когда будет удобно выйти в Zoom?"""

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Завтра (9:00 - 12:00)", "Завтра (12:00 - 18:00)")
    markup.add("После завтра", "В выходные")

    msg = safe_send_message(chat_id, time_text, reply_markup=markup)
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_consultation, user_id)

def finish_form_consultation(message, user_id):
    if check_for_commands(message):
        return

    user_data[user_id]["zoom_time"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id

    save_message_history(user_id, message.message_id)
    save_lead_consultation(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_CONSULTATION", "Консультация")
    notify_admin_consultation(app)

    confirmation = f"""✅ Спасибо! Заявка принята.

Твои данные:
📝 Имя: {app.get('name')}
⏱️ Время функционирования: {app.get('business_duration')}
📱 Telegram: {app.get('telegram')}
📧 Email: {app.get('email')}

Предпочитаемое время созвона:
🕐 {app.get('zoom_time')}

Что дальше?
Наш специалист свяжется с тобой в Telegram в течение часа и согласует точное время встречи на Zoom.

На консультации мы разберем:
✅ Текущую ситуацию в вашем бизнесе
✅ Проблемы в воронке продаж
✅ Потенциал роста после автоматизации
✅ Стоимость и сроки внедрения решения

🙌 Спасибо, что выбрал AI2BIZ!
Подпишись на канал для эксклюзивных материалов: @it_ai2biz"""

    msg = safe_send_message(chat_id, confirmation, reply_markup=telebot.types.ReplyKeyboardRemove())
    save_message_history(user_id, msg.message_id)

# ===== РАССЫЛКИ =====

def broadcast_by_segment(admin_id, segment, message_text):
    if not message_text:
        safe_send_message(admin_id, "Укажите текст рассылки")
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
            safe_send_message(admin_id, f"Ошибка: {response.text}")
            return

        users = response.json()
        count = 0

        for user_obj in users:
            try:
                safe_send_message(user_obj['user_id'], message_text)
                count += 1
            except:
                pass

        safe_send_message(admin_id, f"✅ Отправлено {count} пользователям ({segment.upper()})")

    except Exception as e:
        safe_send_message(admin_id, f"❌ Ошибка: {str(e)}")

# ===== ГЛАВНАЯ СТРАНИЦА =====

@app.route('/')
def index():
    return """
    <h1>AI2BIZ Telegram Bot</h1>
    <p><strong>Статус:</strong> Активен</p>
    <p><strong>Версия:</strong> 6.0 FINAL</p>
    <p><strong>Функции:</strong></p>
    <ul>
        <li>✅ Команда /cancel работает КОРРЕКТНО</li>
        <li>✅ Команда /help работает</li>
        <li>✅ Отправка материалов</li>
        <li>✅ Запись на консультацию</li>
        <li>✅ Рассылки по сегментам</li>
    </ul>
    """

# ===== ЗАПУСК =====

if __name__ == '__main__':
    print("✅ AI2BIZ Bot v6.0 запущен!")
    app.run(host='0.0.0.0', port=5000, debug=False)
