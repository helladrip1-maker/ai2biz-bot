#!/usr/bin/env python3

"""
AI2BIZ Telegram Bot - VERSION V7.3 FINAL
- ✅ Полная интеграция Google Sheets (напрямую)
- ✅ Без зависимости от oauth2client (использует gspread напрямую)
- ✅ Все ошибки импорта исправлены
- ✅ Готов к production на Render
"""

import os
import re
import telebot
import json
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

# Попытка импортировать gspread (опционально)
try:
    import gspread
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("⚠️ gspread не установлен. Google Sheets будет отключен.")

load_dotenv()

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_ID = os.getenv(
    "GOOGLE_SHEETS_ID",
    "1Rmmb8W-1wD4C5I_zPrH_LFaCOnuQ4ny833iba8sAR_I"
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")

ZOOM_LINK = os.getenv("ZOOM_LINK", "https://zoom.us/YOUR_ZOOM_LINK")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_NAME = "it_ai2biz"
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

FILE_5_MISTAKES = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/5%20mistakes%20of%20managers.pdf"
)
FILE_CHECKLIST = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/Check%20list%2010%20ways.pdf"
)

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# ===== ИНИЦИАЛИЗАЦИЯ GOOGLE SHEETS =====


def init_google_sheets():
    """Инициализирует подключение к Google Sheets."""
    if not GSPREAD_AVAILABLE:
        print("ℹ️ gspread не установлен. Google Sheets функции отключены.")
        return None

    try:
        if GOOGLE_SERVICE_ACCOUNT_JSON in ("{}", "", None):
            print("⚠️ GOOGLE_SERVICE_ACCOUNT_JSON не настроена.")
            return None

        # Парсим JSON с учетными данными сервиса
        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

        # Авторизуемся через service_account
        client = gspread.service_account_from_dict(creds_dict)

        # Открываем таблицу по ID
        sheet = client.open_by_key(GOOGLE_SHEETS_ID)
        print("✅ Google Sheets подключена успешно!")
        return sheet
    except Exception as e:
        print(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None


google_sheets = init_google_sheets()

# Словари для состояния пользователей
user_data = {}
user_state = {}
user_message_history = {}
welcome_message_ids = {}

# ===== ВАЛИДАЦИЯ =====


def is_valid_email(email):
    """Проверяет валидность email."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def is_valid_telegram(telegram):
    """Проверяет валидность Telegram."""
    telegram = telegram.strip()
    if telegram.startswith("@"):
        return (
            len(telegram) > 1
            and telegram.replace("@", "").replace("_", "").isalnum()
        )
    if "t.me/" in telegram:
        return True
    return False


def is_valid_name(name):
    """Проверяет валидность имени."""
    name = name.strip()
    return 2 <= len(name) <= 50


def safe_send_message(chat_id, text, **kwargs):
    """Безопасно отправляет сообщение."""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")
        try:
            return bot.send_message(chat_id, text, **kwargs)
        except Exception:
            return None


# ===== GOOGLE SHEETS ФУНКЦИИ =====


def save_to_google_sheets(sheet_name, row_data):
    """Сохраняет строку в Google Sheets."""
    if not google_sheets:
        print(f"ℹ️ Google Sheets отключена, пропускаю сохранение в '{sheet_name}'.")
        return False

    try:
        try:
            worksheet = google_sheets.worksheet(sheet_name)
        except Exception:
            print(f"❌ Лист '{sheet_name}' не найден в Google Sheets.")
            return False

        worksheet.append_row(row_data)
        print(f"✅ Данные сохранены в '{sheet_name}'.")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False


def log_action(user_id, name, action, details=""):
    """Логирует действие в лист Stats."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {action} | {name} ({user_id})")
    row_data = [timestamp, str(user_id), name, action, details]
    save_to_google_sheets("Stats", row_data)


def _calc_segment(revenue_value):
    """Определяет сегмент клиента по выручке."""
    revenue = (revenue_value or "").lower()
    if "300k" in revenue or "<" in revenue or "small" in revenue:
        return "small"
    if "1m" in revenue or "medium" in revenue:
        return "medium"
    if "5m" in revenue or "large" in revenue or "+" in revenue:
        return "large"
    return "enterprise"


def save_lead_files(user_id, lead_data):
    """Сохраняет лид, запросивший файлы."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    segment = _calc_segment(lead_data.get("revenue"))

    row_data = [
        timestamp,
        str(user_id),
        lead_data.get("name", ""),
        lead_data.get("business_duration", ""),
        lead_data.get("telegram", ""),
        lead_data.get("business", ""),
        lead_data.get("revenue", ""),
        lead_data.get("file_type", ""),
        segment,
    ]
    save_to_google_sheets("Leads Files", row_data)


def save_lead_consultation(user_id, lead_data):
    """Сохраняет лид консультации."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    segment = _calc_segment(lead_data.get("revenue"))

    row_data = [
        timestamp,
        str(user_id),
        lead_data.get("name", ""),
        lead_data.get("business_duration", ""),
        lead_data.get("telegram", ""),
        lead_data.get("email", ""),
        lead_data.get("business", ""),
        lead_data.get("revenue", ""),
        lead_data.get("participants", ""),
        lead_data.get("zoom_time", ""),
        segment,
    ]
    save_to_google_sheets("Leads Consultation", row_data)


def notify_admin_consultation(lead_data):
    """Отправляет уведомление администратору."""
    if ADMIN_CHAT_ID == 0:
        print("ℹ️ ADMIN_CHAT_ID не установлен.")
        return

    segment = _calc_segment(lead_data.get("revenue")).upper()
    notification = (
        "🔔 НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ\n\n"
        f"Имя: {lead_data.get('name')}\n"
        f"Срок: {lead_data.get('business_duration')}\n"
        f"Telegram: {lead_data.get('telegram')}\n"
        f"Email: {lead_data.get('email')}\n"
        f"Бизнес: {lead_data.get('business')}\n"
        f"Выручка: {lead_data.get('revenue')}\n"
        f"На созвоне: {lead_data.get('participants')}\n"
        f"Время: {lead_data.get('zoom_time')}\n"
        f"Сегмент: {segment}\n"
        f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    try:
        safe_send_message(ADMIN_CHAT_ID, notification)
        print("✅ Уведомление администратору отправлено.")
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")


def save_message_history(user_id, message_id):
    """Сохраняет ID сообщения."""
    if user_id not in user_message_history:
        user_message_history[user_id] = []
    user_message_history[user_id].append(message_id)


def delete_messages_after_welcome(chat_id, user_id):
    """Удаляет сообщения после приветствия."""
    if user_id not in welcome_message_ids:
        return

    welcome_msg_id = welcome_message_ids[user_id]
    if user_id not in user_message_history:
        return

    messages_to_delete = [
        msg_id
        for msg_id in user_message_history[user_id]
        if msg_id > welcome_msg_id
    ]
    deleted = 0
    for msg_id in messages_to_delete:
        try:
            bot.delete_message(chat_id, msg_id)
            deleted += 1
        except Exception:
            pass

    user_message_history[user_id] = [welcome_msg_id]


def reset_user_state(user_id):
    """Очищает состояние пользователя."""
    user_data.pop(user_id, None)
    user_state.pop(user_id, None)


def process_cancel_command(message):
    """Обрабатывает команду /cancel."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)
    send_welcome_internal(message)


def process_help_command(message):
    """Обрабатывает команду /help."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)

    help_text = (
        "Вопросы или проблемы?\n\n"
        "Напишите: @glore4\n\n"
        "Ответим в течение часа."
    )
    msg = safe_send_message(chat_id, help_text)
    if msg:
        save_message_history(user_id, msg.message_id)
    send_welcome_internal(message)


def check_for_commands(message):
    """Проверяет /cancel или /help."""
    if not message.text:
        return False

    text = message.text.strip()
    if text == "/cancel":
        process_cancel_command(message)
        return True
    if text == "/help":
        process_help_command(message)
        return True
    return False


# ===== WEBHOOK =====


@app.route("/telegram-webhook", methods=["POST"])
def webhook():
    try:
        json_data = request.get_json()
        if json_data:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"Ошибка webhook: {e}")
        return "ERROR", 400


# ===== ПРИВЕТСТВИЕ =====


def send_welcome_internal(message):
    """Отправляет приветствие."""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    chat_id = message.chat.id

    welcome_text = (
        f"Привет, {user_name}!\n\n"
        "Я бот AI2BIZ. Помогу получить материалы и записаться на консультацию.\n\n"
        "Напиши:\n"
        "• файлы - получить материалы\n"
        "• консультация - записаться на созвон\n"
        "• /cancel - главное меню\n"
        "• /help - поддержка"
    )

    msg = safe_send_message(chat_id, welcome_text)
    if msg:
        welcome_message_ids[user_id] = msg.message_id
        save_message_history(user_id, msg.message_id)


# ===== /START =====


@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"

    print(f"Пользователь {user_id} запустил бота")
    log_action(user_id, user_name, "START", "Начало разговора")

    bot.clear_step_handler_by_chat_id(message.chat.id)
    reset_user_state(user_id)
    send_welcome_internal(message)


# ===== /CANCEL =====


@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    process_cancel_command(message)


# ===== /HELP =====


@bot.message_handler(commands=["help"])
def help_command(message):
    process_help_command(message)


# ===== ОСНОВНОЙ ХЕНДЛЕР =====


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").lower().strip()

    save_message_history(user_id, message.message_id)

    # ФАЙЛЫ
    if any(word in text for word in ["файлы", "материал", "документ", "pdf"]):
        subscription_text = (
            f"Подпишись на канал @{CHANNEL_NAME}\n\n"
            "Там публикуем кейсы и материалы по автоматизации продаж.\n\n"
            "После подписки нажми кнопку ниже."
        )
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton(
                "Я подписался", callback_data="subscribed"
            )
        )
        msg = safe_send_message(chat_id, subscription_text, reply_markup=markup)
        if msg:
            save_message_history(user_id, msg.message_id)
        return

    # КОНСУЛЬТАЦИЯ
    if any(
        word in text
        for word in ["консультац", "запись", "созвон", "консульт", "zoom"]
    ):
        reset_user_state(user_id)
        user_state[user_id] = "consultation"
        user_data[user_id] = {}

        consultation_text = "Записываем на консультацию!\n\nКак тебя зовут?"
        msg = safe_send_message(
            chat_id, consultation_text, reply_markup=telebot.types.ReplyKeyboardRemove()
        )
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return

    # Неизвестная команда
    help_text = (
        "Не понял команду.\n\n"
        "Напиши:\n"
        "• файлы\n"
        "• консультация\n"
        "• /cancel или /help"
    )
    msg = safe_send_message(chat_id, help_text)
    if msg:
        save_message_history(user_id, msg.message_id)


# ===== CALLBACK =====


@bot.callback_query_handler(func=lambda call: call.data == "subscribed")
def handle_subscription(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    bot.answer_callback_query(call.id, "Спасибо!")

    reset_user_state(user_id)
    user_state[user_id] = "files"
    user_data[user_id] = {}

    file_selection_text = "Выбери материал:\n• 5 ошибок менеджеров\n• Чек-лист"

    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("5 ошибок менеджеров")
    markup.add("Чек-лист")

    msg = safe_send_message(chat_id, file_selection_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)


# ===== ЦЕПОЧКА: ФАЙЛЫ =====


def handle_file_selection(message, user_id):
    if check_for_commands(message):
        return

    text = (message.text or "").lower().strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if "ошибок" in text or "менеджеров" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
    elif "чек" in text or "лист" in text:
        user_data[user_id]["file_type"] = "checklist"
    else:
        invalid_text = "Выбери из предложенных вариантов"
        markup = telebot.types.ReplyKeyboardMarkup(
            resize_keyboard=True, one_time_keyboard=True
        )
        markup.add("5 ошибок менеджеров")
        markup.add("Чек-лист")

        msg = safe_send_message(chat_id, invalid_text, reply_markup=markup)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return

    form_text = "Как тебя зовут?"
    msg = safe_send_message(
        chat_id, form_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_name_check, user_id)


def ask_files_name_check(message, user_id):
    if check_for_commands(message):
        return

    name = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = "Имя должно быть от 2 до 50 символов"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_files_name_check, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = "Сколько работает бизнес?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_business_duration, user_id)


def ask_files_business_duration(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = "Твой Telegram (@username или t.me/username):"

    msg = safe_send_message(
        chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)


def ask_files_telegram_check(message, user_id):
    if check_for_commands(message):
        return

    telegram = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = "Некорректный формат. Используй @username или t.me/username"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    business_text = "Расскажи о бизнесе (ниша, продукт, проблемы):"
    msg = safe_send_message(chat_id, business_text)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_business, user_id)


def ask_files_business(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = (message.text or "").strip()

    revenue_text = "Выручка в месяц?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, finish_form_files, user_id)


def finish_form_files(message, user_id):
    if check_for_commands(message):
        return

    user_data[user_id]["revenue"] = message.text
    app_data = user_data[user_id]
    chat_id = message.chat.id

    save_message_history(user_id, message.message_id)
    save_lead_files(user_id, app_data)
    log_action(user_id, app_data.get("name"), "FORM_FILES", "Заявка на файлы")

    sending_text = "Отправляю файл..."
    msg = safe_send_message(
        chat_id, sending_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)

    try:
        if app_data.get("file_type") == "5_mistakes":
            file_url = FILE_5_MISTAKES
            file_description = (
                "5 ошибок менеджеров, которые теряют 50% лидов.\n\n"
                "Изучи материал и запишись на консультацию для разбора твоей ситуации."
            )
        else:
            file_url = FILE_CHECKLIST
            file_description = (
                "Чек-лист для быстрой диагностики потерь лидов.\n\n"
                "Пройди опрос и поймешь, где именно теряется твоя выручка."
            )

        doc_msg = bot.send_document(chat_id, file_url, caption=file_description)
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)

        log_action(user_id, app_data.get("name"), "FILE_SENT", "Файл отправлен")

        consultation_offer = (
            "Файл отправлен!\n\n"
            "Хочешь получить конкретный план роста для твого бизнеса?\n\n"
            "Напиши слово 'консультация' и запишись на бесплатный созвон."
        )
        msg = safe_send_message(chat_id, consultation_offer)
        if msg:
            save_message_history(user_id, msg.message_id)

    except Exception as e:
        print(f"Ошибка отправки файла: {e}")
        error_msg = safe_send_message(chat_id, "Ошибка. Попробуй чуть позже.")
        if error_msg:
            save_message_history(user_id, error_msg.message_id)


# ===== ЦЕПОЧКА: КОНСУЛЬТАЦИЯ =====


def ask_consultation_name(message, user_id):
    if check_for_commands(message):
        return

    name = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_name(name):
        error_text = "Имя должно быть от 2 до 50 символов"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return

    user_data[user_id]["name"] = name

    duration_text = "Сколько работает бизнес?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")

    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_business_duration, user_id)


def ask_consultation_business_duration(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text

    telegram_text = "Твой Telegram:"
    msg = safe_send_message(
        chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)


def ask_consultation_telegram_check(message, user_id):
    if check_for_commands(message):
        return

    telegram = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_telegram(telegram):
        error_text = "Некорректный формат"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)
        return

    user_data[user_id]["telegram"] = telegram

    email_text = "Твой Email (name@example.com):"
    msg = safe_send_message(chat_id, email_text)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)


def ask_consultation_email_check(message, user_id):
    if check_for_commands(message):
        return

    email = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if not is_valid_email(email):
        error_text = "Некорректный Email"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)
        return

    user_data[user_id]["email"] = email

    business_text = "Расскажи о бизнесе, выручке, проблемах в продажах:"
    msg = safe_send_message(chat_id, business_text)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_business, user_id)


def ask_consultation_business(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = (message.text or "").strip()

    revenue_text = "Выручка в месяц?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")

    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_revenue, user_id)


def ask_consultation_revenue(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["revenue"] = message.text

    participants_text = "Кто будет на созвоне?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("Я один", "С партнером")
    markup.add("Не принимаю решений")

    msg = safe_send_message(chat_id, participants_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_participants, user_id)


def ask_consultation_participants(message, user_id):
    if check_for_commands(message):
        return

    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["participants"] = message.text

    time_text = "Когда удобно выйти в Zoom?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("Завтра 9-12", "Завтра 12-18")
    markup.add("После завтра", "В выходные")

    msg = safe_send_message(chat_id, time_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, finish_form_consultation, user_id)


def finish_form_consultation(message, user_id):
    if check_for_commands(message):
        return

    user_data[user_id]["zoom_time"] = message.text
    app_data = user_data[user_id]
    chat_id = message.chat.id

    save_message_history(user_id, message.message_id)
    save_lead_consultation(user_id, app_data)
    log_action(user_id, app_data.get("name"), "FORM_CONSULTATION", "Заявка на консультацию")
    notify_admin_consultation(app_data)

    confirmation = (
        "Спасибо, заявка принята!\n\n"
        f"Имя: {app_data.get('name')}\n"
        f"Email: {app_data.get('email')}\n"
        f"Telegram: {app_data.get('telegram')}\n\n"
        "Менеджер свяжется с тобой в течение часа и согласует время созвона.\n\n"
        "Спасибо, что выбрал AI2BIZ!"
    )

    msg = safe_send_message(
        chat_id, confirmation, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)


# ===== ГЛАВНАЯ СТРАНИЦА =====


@app.route("/")
def index():
    return (
        "<h1>AI2BIZ Bot v7.3</h1>"
        "<p>Статус: Активен</p>"
    )


# ===== ЗАПУСК =====


if __name__ == "__main__":
    print("✅ AI2BIZ Bot v7.3 запущен.")
    if not GSPREAD_AVAILABLE:
        print(
            "⚠️ gspread не установлен. Добавьте в requirements.txt "
            "и выполните redeploy."
        )
    app.run(host="0.0.0.0", port=5000, debug=False)
