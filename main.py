#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI2BIZ Telegram Bot - VERSION V8.0 AUTOFUNNEL
- ✅ Автоворонка с дожимами (follow-up messages)
- ✅ Интеграция с Google Sheets для отслеживания пользователей
- ✅ Форма диагностики
- ✅ Автоматические дожимы через scheduler
- ✅ Отслеживание действий пользователей
"""

import os
import re
import telebot
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import pytz
from messages import MESSAGES, FOLLOW_UP_PLAN
from scheduler_manager import FollowUpScheduler

# Попытка импортировать gspread (опционально)
try:
    import gspread
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("⚠️ gspread не установлен. Google Sheets будет отключен.")

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_ID = os.getenv(
    "GOOGLE_SHEETS_ID", "1Rmmb8W-1wD4C5I_zPrH_LFaCOnuQ4ny833iba8sAR_I"
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
ZOOM_LINK = os.getenv("ZOOM_LINK", "https://zoom.us/YOUR_ZOOM_LINK")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_NAME = "it_ai2biz"
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# ===== ЗАГЛУШКИ ДЛЯ ОТСУТСТВУЮЩИХ ПЕРЕМЕННЫХ =====
# Чтобы код не падал, если эти переменные не были определены
MESSAGES_DICT = {}
BUTTONS = {}
FOLLOW_UP_TIMES = {}
FORM_QUESTIONS = {
    "q1": {"text": "Чем занимается ваша компания?", "options": ["B2B услуги", "B2C услуги", "Производство", "Торговля", "Другое"]},
    "q2": {"text": "Сколько у вас сотрудников?", "options": ["1-5", "5-20", "20-50", "50+"]},
    "q3": {"text": "Есть ли у вас CRM?", "options": ["Да, AmoCRM", "Да, Bitrix24", "Другая", "Нет"]},
    "q4": {"text": "Есть ли отдел продаж?", "options": ["Да", "Нет, продаю сам", "Робот"]},
    "q5": {"text": "Какая выручка в месяц?", "options": ["< 100K", "100-300K", "300K - 1M", "1M+"]}
}

FILE_5_MISTAKES = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/5%20mistakes%20of%20managers.pdf?v=20251227"
)
FILE_CHECKLIST = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/Check%20list%2010%20ways.pdf?v=20251227"
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
        
        # Создаем лист Users если его нет
        try:
            sheet.worksheet("Users")
        except Exception:
            worksheet = sheet.add_worksheet("Users", 1000, 10)
            worksheet.append_row([
                "User ID", "Username", "Name", "Started", 
                "Last Action", "State", "Lead Quality", "Answers", "Messages Sent"
            ])
            print("✅ Создан лист Users")
        
        return sheet
    except Exception as e:
        print(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

google_sheets = init_google_sheets()

# Словари для состояния пользователей (СНАЧАЛА определяем их!)
user_data = {}
user_state = {}
user_message_history = {}
welcome_message_ids = {}
form_answers = {}  # Для формы диагностики

# Инициализация scheduler для дожимов (ПОСЛЕ определения user_data)
scheduler = FollowUpScheduler(bot, user_data)
scheduler.start()
logger.info("✅ Scheduler для дожимов запущен")

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

def is_valid_phone(phone):
    """Проверяет валидность номера телефона: +7 и 10 цифр (любые разделители)."""
    phone = phone.strip()
    if not phone.startswith("+7"):
        return False
    digits_only = re.sub(r"\D", "", phone[2:])
    return len(digits_only) == 10 and digits_only.isdigit()

def is_valid_name(name):
    """Проверяет валидность имени."""
    name = name.strip()
    return 2 <= len(name) <= 50

def safe_send_message(chat_id, text, **kwargs):
    """Безопасно отправляет сообщение."""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        try:
            return bot.send_message(chat_id, text, **kwargs)
        except Exception:
            return None

# ===== GOOGLE SHEETS ФУНКЦИИ =====
def save_to_google_sheets(sheet_name, row_data):
    """Сохраняет строку в Google Sheets."""
    if not google_sheets:
        logger.info(f"ℹ️ Google Sheets отключена, пропускаю сохранение в '{sheet_name}'.")
        return False
    try:
        try:
            worksheet = google_sheets.worksheet(sheet_name)
        except Exception:
            logger.warning(f"❌ Лист '{sheet_name}' не найден в Google Sheets.")
            return False
        worksheet.append_row(row_data)
        logger.info(f"✅ Данные сохранены в '{sheet_name}'.")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def create_or_update_user(user_id, username, first_name, action="", state=""):
    """Создает или обновляет запись пользователя в Google Sheets."""
    if not google_sheets:
        return False
    
    try:
        worksheet = google_sheets.worksheet("Users")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Пытаемся найти пользователя
        try:
            cell = worksheet.find(str(user_id))
            row = cell.row
            
            # Обновляем существующую запись
            worksheet.update_cell(row, 2, username or "")  # Username
            worksheet.update_cell(row, 3, first_name or "")  # Name
            if action:
                worksheet.update_cell(row, 5, action)  # Last Action
            if state:
                worksheet.update_cell(row, 6, state)  # State
            logger.info(f"✅ Обновлена запись пользователя {user_id}")
        except Exception:
            # Создаем новую запись
            worksheet.append_row([
                str(user_id),
                username or "",
                first_name or "",
                timestamp,
                action or "",
                state or "initial",
                "",  # Lead Quality
                "",  # Answers
                "0"  # Messages Sent
            ])
            logger.info(f"✅ Создана запись пользователя {user_id}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания/обновления пользователя: {e}")
        return False

def update_user_action(user_id, action):
    """Обновляет последнее действие пользователя."""
    if scheduler:
        scheduler.mark_user_action(user_id, action)
    
    if not google_sheets:
        return False
    
    try:
        worksheet = google_sheets.worksheet("Users")
        cell = worksheet.find(str(user_id))
        if cell:
            row = cell.row
            worksheet.update_cell(row, 5, action)
            logger.info(f"✅ Обновлено действие пользователя {user_id}: {action}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления действия: {e}")
    
    return False

def log_action(user_id, name, action, details=""):
    """Логирует действие в лист Stats."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] {action} | {name} ({user_id})")
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
    contact = lead_data.get("telegram", "") or lead_data.get("phone", "")
    row_data = [
        timestamp,
        str(user_id),
        lead_data.get("name", ""),
        lead_data.get("business_duration", ""),
        contact,
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
    contact = lead_data.get("telegram", "") or lead_data.get("phone", "")
    row_data = [
        timestamp,
        str(user_id),
        lead_data.get("name", ""),
        lead_data.get("business_duration", ""),
        contact,
        lead_data.get("email", ""),
        lead_data.get("business", ""),
        lead_data.get("revenue", ""),
        lead_data.get("participants", ""),
        lead_data.get("zoom_time", ""),
        segment,
    ]
    save_to_google_sheets("Leads Consultation", row_data)

def save_form_answers(user_id, answers):
    """Сохраняет ответы формы диагностики."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Определяем качество лида
    lead_quality = "cold"
    if answers.get("q5") == "300K+":
        lead_quality = "hot"
    elif answers.get("q5") in ["100-300K"]:
        lead_quality = "warm"
    
    row_data = [
        timestamp,
        str(user_id),
        answers.get("q1", ""),
        answers.get("q2", ""),
        answers.get("q3", ""),
        answers.get("q4", ""),
        answers.get("q5", ""),
        lead_quality,
    ]
    save_to_google_sheets("Form Answers", row_data)
    
    # Обновляем качество лида в Users
    if google_sheets:
        try:
            worksheet = google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id))
            if cell:
                row = cell.row
                worksheet.update_cell(row, 7, lead_quality)
        except Exception:
            pass
    
    return lead_quality

def notify_admin_consultation(lead_data):
    """Отправляет уведомление администратору."""
    if ADMIN_CHAT_ID == 0:
        logger.info("ℹ️ ADMIN_CHAT_ID не установлен.")
        return
    segment = _calc_segment(lead_data.get("revenue")).upper()
    contact_info = lead_data.get("telegram", "") or lead_data.get("phone", "")
    notification = (
        "🔔\n\n"
        "*НОВАЯ ГОРЯЧАЯ ЗАЯВКА*\n\n"
        f" *Имя:* {lead_data.get('name')}\n"
        f" *Срок:* {lead_data.get('business_duration')}\n"
        f" *Контакт:* {contact_info}\n"
        f" *Email:* {lead_data.get('email', 'N/A')}\n"
        f" *Бизнес:* {lead_data.get('business')}\n"
        f" *Выручка:* {lead_data.get('revenue')}\n"
        f" *На созвоне:* {lead_data.get('participants')}\n"
        f" *Время:* {lead_data.get('zoom_time')}\n"
        f" *Сегмент:* {segment}\n"
        f" *Дата:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        safe_send_message(ADMIN_CHAT_ID, notification, parse_mode="Markdown")
        logger.info("✅ Уведомление администратору отправлено.")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

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
    for msg_id in messages_to_delete:
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    user_message_history[user_id] = [welcome_msg_id]

def reset_user_state(user_id):
    """Очищает состояние пользователя."""
    user_data.pop(user_id, None)
    user_state.pop(user_id, None)
    form_answers.pop(user_id, None)

def process_cancel_command(message):
    """Обрабатывает команду /cancel."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)
    delete_messages_after_welcome(chat_id, user_id)
    send_old_menu(message)

def process_help_command(message):
    """Обрабатывает команду /help."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)
    help_text = (
        "💬 *Есть вопросы по работе бота или к AI2BIZ?*\n\n"
        "Напиши *@glore4*\n\n"
        "Поможем разобраться и решить проблему оперативно"
    )
    msg = safe_send_message(chat_id, help_text, parse_mode="Markdown")
    if msg:
        save_message_history(user_id, msg.message_id)
    send_old_menu(message)

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

def build_inline_keyboard(buttons_config):
    """Создает InlineKeyboardMarkup из конфигурации кнопок."""
    markup = telebot.types.InlineKeyboardMarkup()
    for row in buttons_config:
        keyboard_row = []
        for button_text, callback_or_url in row:
            if callback_or_url.startswith("http"):
                keyboard_row.append(
                    telebot.types.InlineKeyboardButton(text=button_text, url=callback_or_url)
                )
            else:
                keyboard_row.append(
                    telebot.types.InlineKeyboardButton(text=button_text, callback_data=callback_or_url)
                )
        if keyboard_row:
            markup.add(*keyboard_row)
    return markup

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
        logger.error(f"Ошибка webhook: {e}")
        return "ERROR", 400

# ===== ПРИВЕТСТВИЕ (АВТОВОРОНКА) =====
def send_welcome_internal(message):
    """Отправляет MESSAGE 0 и запускает воронку."""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Партнер"
    username = message.from_user.username or ""
    chat_id = message.chat.id
    
    # Создаем или обновляем пользователя
    create_or_update_user(user_id, username, user_name, "START_FUNNEL", "initial")
    
    # Отправляем Message 0
    # Используем send_message_job, чтобы логика была единой, но message 0 нужно отправить сразу
    # Поэтому вызываем метод отправки scheduler'а напрямую или просто bot.send_message используя данные
    
    msg_data = MESSAGES.get("message_0")
    if msg_data:
        text = msg_data.get("text")
        buttons = msg_data.get("buttons")
        
        markup = None
        if buttons:
            markup = telebot.types.InlineKeyboardMarkup()
            for row in buttons:
                 btns = []
                 for btn in row:
                     if "url" in btn:
                         btns.append(telebot.types.InlineKeyboardButton(text=btn["text"], url=btn["url"]))
                     else:
                         btns.append(telebot.types.InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
                 markup.add(*btns)
        
        try:
            msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            if msg:
                welcome_message_ids[user_id] = msg.message_id
                save_message_history(user_id, msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка отправки welcome: {e}")

    # Запланировать следующий шаг (message_1 через 10 минут)
    if scheduler:
        scheduler.schedule_next_message(user_id, chat_id, "message_0")

def send_old_menu(message):
    """Отправляет старое меню (приветствие)."""
     # Это старая логика, которую просят оставить как меню
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Партнер"
    chat_id = message.chat.id
    
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        "Я бот *AI2BIZ* – помогу получить материалы по автоматизации продаж и запишу тебя на консультацию."
    )
    # Кнопки старого меню (из предыдущего кода, предположительно были простые)
    # Восстанавливаем базовые кнопки
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("📚 Файлы", callback_data="subscribed"), # Предполагаем что это ведет к файлам
        telebot.types.InlineKeyboardButton("📞 Консультация", callback_data="consultation")
    )
    
    msg = safe_send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)

# ===== /START =====
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    logger.info(f"Пользователь {user_id} запустил бота")
    log_action(user_id, user_name, "START", "Запуск бота")
    bot.clear_step_handler_by_chat_id(message.chat.id)
    reset_user_state(user_id)
    send_welcome_internal(message)

# ===== /HELP =====
@bot.message_handler(commands=["help"])
def help_command(message):
    process_help_command(message)

# ===== /CANCEL =====
@bot.message_handler(commands=["cancel", "menu"])
def cancel_command(message):
    process_cancel_command(message)

# ===== /MENU (Old Welcome) =====
# process_cancel_command зовет send_welcome_internal, который теперь запускает воронку Message 0.
# Но /cancel и /menu должны открывать СТАРОЕ меню.
# Поэтому нужно изменить process_cancel_command чтобы он вызывал send_old_menu.

def process_cancel_command(message):
    """Обрабатывает команду /cancel и /menu."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)
    # Вместо send_welcome_internal вызываем send_old_menu
    send_old_menu(message)

# ===== /COMMANDS =====
@bot.message_handler(commands=["commands"])
def commands_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    reset_user_state(user_id)
    delete_messages_after_welcome(chat_id, user_id)
    commands_text = (
        "📋 *Список команд:*\n\n"
        " */start* – главное меню\n"
        " */help* – помощь и контакты\n"
        " */cancel* – вернуться в меню\n"
        " */commands* – этот список\n\n"
        "Или просто напиши:\n"
        " *файлы* – получить бесплатные материалы\n"
        " *консультация* – записаться на консультацию"
    )
    msg = safe_send_message(chat_id, commands_text, parse_mode="Markdown")
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    # send_welcome_internal(message) - убрали, чтобы не спамить START сообщением
    # Лучше показать меню
    send_old_menu(message)

# ===== CALLBACK HANDLERS =====
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка всех callback запросов."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    callback_data = call.data
    
    # Отмечаем действие пользователя
    update_user_action(user_id, callback_data)
    
    try:
        if callback_data == "subscribed":
            bot.answer_callback_query(call.id, "Спасибо за подписку! 🎉")
            reset_user_state(user_id)
            user_state[user_id] = "waiting_file_choice"
            user_data[user_id] = {}
            file_selection_text = (
                "✅ Отлично! Теперь выбери материал, который тебя интересует:\n\n"
                "🔴 *5 ошибок менеджеров*, которые теряют 50% лидов\n"
                "📋 *Чек-лист* 10 способов определить, теряете ли вы заявки"
            )
            markup = telebot.types.ReplyKeyboardMarkup(
                resize_keyboard=True, one_time_keyboard=True
            )
            markup.add("🔴 5 ошибок менеджеров")
            markup.add("📋 Чек-лист")
            msg = safe_send_message(
                chat_id, file_selection_text, reply_markup=markup, parse_mode="Markdown"
            )
            if msg:
                save_message_history(user_id, msg.message_id)
        
        elif callback_data == "consultation":
            bot.answer_callback_query(call.id)
            reset_user_state(user_id)
            user_state[user_id] = "consultation_name"
            user_data[user_id] = {}
            consultation_text = (
                "📞 *Отлично, давай запишемся на консультацию*\n\n"
                "Расскажи немного о себе, и мы подготовимся к нашей встрече.\n\n"
                " *Как тебя зовут?*"
            )
            msg = safe_send_message(
                chat_id,
                consultation_text,
                reply_markup=telebot.types.ReplyKeyboardRemove(),
                parse_mode="Markdown",
            )
            if msg:
                save_message_history(user_id, msg.message_id)
        
        elif callback_data == "examples":
            bot.answer_callback_query(call.id)
            examples_text = (
                "Вот наш самый успешный кейс:\n\n"
                "📊 Deutsch Agent: +4x выручки за 4 месяца\n"
                "📊 Ремонтная компания: окупаемость 6 дней\n"
                "📊 Экспобанк: автоматизировал 80% процессов\n\n"
                "Хотите записаться на консультацию?"
            )
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(
                telebot.types.InlineKeyboardButton("📋 Консультация", callback_data="consultation")
            )
            bot.edit_message_text(
                examples_text,
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        
        elif callback_data == "start_form":
            bot.answer_callback_query(call.id)
            start_diagnostic_form(call.message, user_id)
        
        elif callback_data == "download_guide":
            bot.answer_callback_query(call.id)
            send_pdf_guide(chat_id, user_id)
        
        elif callback_data.startswith("answer_"):
            bot.answer_callback_query(call.id)
            handle_form_answer(call, user_id)
        
        else:
            bot.answer_callback_query(call.id, "Обрабатываю...")
    
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

# ===== ФОРМА ДИАГНОСТИКИ =====
def start_diagnostic_form(message, user_id):
    """Начинает форму диагностики."""
    chat_id = message.chat.id if hasattr(message, 'chat') else message.chat_id
    
    if user_id not in form_answers:
        form_answers[user_id] = {}
    
    user_state[user_id] = "diagnostic_form"
    form_answers[user_id]["current_question"] = "q1"
    
    question_data = FORM_QUESTIONS.get("q1", {})
    question_text = question_data.get("text", "Чем занимается ваша компания?")
    options = question_data.get("options", [])
    
    markup = telebot.types.InlineKeyboardMarkup()
    for option in options:
        callback_data = f"answer_q1_{option.lower().replace(' ', '_').replace('/', '_')}"
        markup.add(telebot.types.InlineKeyboardButton(option, callback_data=callback_data))
    
    if hasattr(message, 'edit_text'):
        msg = bot.edit_message_text(
            question_text,
            chat_id=chat_id,
            message_id=message.message_id,
            reply_markup=markup
        )
    else:
        msg = safe_send_message(chat_id, question_text, reply_markup=markup)
        if msg:
            save_message_history(user_id, msg.message_id)

def handle_form_answer(call, user_id):
    """Обрабатывает ответ на вопрос формы."""
    callback_data = call.data
    chat_id = call.message.chat.id
    
    # Парсим callback_data: answer_q1_b2b_услуги
    parts = callback_data.split("_")
    if len(parts) < 3:
        return
    
    question_num = parts[1]  # q1, q2, etc
    answer = "_".join(parts[2:])  # Ответ
    
    if user_id not in form_answers:
        form_answers[user_id] = {}
    
    form_answers[user_id][question_num] = answer
    
    # Определяем следующий вопрос
    question_nums = ["q1", "q2", "q3", "q4", "q5"]
    current_index = question_nums.index(question_num) if question_num in question_nums else -1
    next_index = current_index + 1
    
    if next_index < len(question_nums):
        next_question = question_nums[next_index]
        question_data = FORM_QUESTIONS.get(next_question, {})
        question_text = question_data.get("text", "")
        options = question_data.get("options", [])
        
        markup = telebot.types.InlineKeyboardMarkup()
        for option in options:
            callback_data = f"answer_{next_question}_{option.lower().replace(' ', '_').replace('/', '_')}"
            markup.add(telebot.types.InlineKeyboardButton(option, callback_data=callback_data))
        
        bot.edit_message_text(
            question_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        form_answers[user_id]["current_question"] = next_question
    else:
        # Форма завершена
        finish_diagnostic_form(chat_id, user_id, call.message.message_id)

def finish_diagnostic_form(chat_id, user_id, message_id):
    """Завершает форму диагностики."""
    answers = form_answers.get(user_id, {})
    
    # Сохраняем ответы
    lead_quality = save_form_answers(user_id, answers)
    update_user_action(user_id, "completed_form")
    
    # Отправляем финальное сообщение
    final_message = MESSAGE_AFTER_FORM or (
        "Спасибо за заполнение! 🎯\n\n"
        "Наш специалист свяжется с вами в течение 30 минут для консультации."
    )
    
    bot.edit_message_text(
        final_message,
        chat_id=chat_id,
        message_id=message_id,
        parse_mode="HTML"
    )
    
    # Предлагаем консультацию
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("📋 Консультация", callback_data="consultation")
    )
    safe_send_message(chat_id, "Хотите записаться на консультацию?", reply_markup=markup)
    
    reset_user_state(user_id)

def send_pdf_guide(chat_id, user_id):
    """Отправляет PDF гайд."""
    try:
        file_url = FILE_5_MISTAKES
        file_description = (
            "📄 *5 ОШИБОК МЕНЕДЖЕРОВ, КОТОРЫЕ ТЕРЯЮТ 50% ЛИДОВ*\n\n"
            "В этом материале разберемся, почему теряется заявки!\n\n"
            "✅ В конце получишь конкретные решения для каждой ошибки.\n\n"
            "💡 За счет исправления этих ошибок клиенты AI2BIZ экономят от 200K в месяц только на потерях."
        )
        
        doc_msg = bot.send_document(
            chat_id, file_url, caption=file_description, parse_mode="Markdown"
        )
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
        
        # Отправляем сообщение после PDF
        after_pdf_text = MESSAGES_DICT.get("after_pdf", 
            "PDF прикреплен! 📎\n\nПрочитай первых 5 страниц."
        )
        msg = safe_send_message(chat_id, after_pdf_text, parse_mode="HTML")
        if msg:
            save_message_history(user_id, msg.message_id)
        
        update_user_action(user_id, "downloaded_pdf")
        log_action(user_id, "", "PDF_DOWNLOADED", "Скачан PDF гайд")
        
    except Exception as e:
        logger.error(f"Ошибка отправки PDF: {e}")
        safe_send_message(chat_id, "Ошибка при отправке. Попробуй позже.")

# ===== ОСНОВНОЙ ХЕНДЛЕР =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").lower().strip()
    save_message_history(user_id, message.message_id)
    
    # Проверяем команды
    if check_for_commands(message):
        return
    
    # ПРОВЕРЯЕМ STATE-MACHINE для обработки многошаговых форм
    current_state = user_state.get(user_id)
    
    if current_state == "waiting_file_choice":
        handle_file_selection(message, user_id)
        return
    elif current_state == "consultation_name":
        ask_consultation_name(message, user_id)
        return
    elif current_state == "consultation_duration":
        ask_consultation_business_duration(message, user_id)
        return
    elif current_state == "consultation_contact":
        ask_consultation_telegram_check(message, user_id)
        return
    elif current_state == "consultation_email":
        ask_consultation_email_check(message, user_id)
        return
    elif current_state == "consultation_business":
        ask_consultation_business(message, user_id)
        return
    elif current_state == "consultation_revenue":
        ask_consultation_revenue(message, user_id)
        return
    elif current_state == "consultation_participants":
        ask_consultation_participants(message, user_id)
        return
    elif current_state == "consultation_time":
        finish_form_consultation(message, user_id)
        return
    # Файловая анкета
    elif current_state == "files_name":
        ask_files_name_check(message, user_id)
        return
    elif current_state == "files_duration":
        ask_files_business_duration(message, user_id)
        return
    elif current_state == "files_contact":
        ask_files_telegram_check(message, user_id)
        return
    elif current_state == "files_business":
        ask_files_business(message, user_id)
        return
    elif current_state == "files_revenue":
        finish_form_files(message, user_id)
        return
    
    # МАТЕРИАЛЫ
    if any(
        word in text
        for word in [
            "материал", "материалы", "файлы", "документ", "pdf",
            "гайд", "файл", "ошиб", "5", "10", "пять", "десять", "лид",
        ]
    ):
        subscription_text = (
            "🔐 *Перед доступом к материалам нужна подписка на канал*\n\n"
            f" *@{CHANNEL_NAME}*\n\n"
            "Там мы публикуем:\n"
            "• кейсы клиентов\n"
            "• реальные примеры роста (x2.5 заявок за месяц)\n"
            "• эксклюзивные материалы для подписчиков и новости\n\n"
            "Подпишись и нажми кнопку ниже ↓"
        )
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton(
                "✅ Я подписался", callback_data="subscribed"
            )
        )
        msg = safe_send_message(
            chat_id, subscription_text, reply_markup=markup, parse_mode="Markdown"
        )
        if msg:
            save_message_history(user_id, msg.message_id)
        return
    
    # КОНСУЛЬТАЦИЯ
    if any(
        word in text
        for word in [
            "консультац", "запись", "созвон", "консульт",
            "zoom", "встреча", "разговор", "зум", "конс",
        ]
    ):
        update_user_action(user_id, "consultation_requested")
        reset_user_state(user_id)
        user_state[user_id] = "consultation"
        user_data[user_id] = {}
        consultation_text = (
            "📞 *Отлично, давай запишемся на консультацию*\n\n"
            "Расскажи немного о себе, и мы подготовимся к нашей встрече.\n\n"
            " *Как тебя зовут?*"
        )
        msg = safe_send_message(
            chat_id,
            consultation_text,
            reply_markup=telebot.types.ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )
        if msg:
            save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return
    
    # Неизвестная команда
    help_text = (
        "Не совсем понял 😕\n\n"
        "Выбери один из вариантов:\n"
        "📚 *файлы* – получить бесплатные гайды\n"
        "📞 *консультация* – записаться на созвон\n\n"
        "Или используй /commands для полного списка"
    )
    msg = safe_send_message(chat_id, help_text, parse_mode="Markdown")
    if msg:
        save_message_history(user_id, msg.message_id)

# ===== ЦЕПОЧКА: МАТЕРИАЛЫ =====
def handle_file_selection(message, user_id):
    if check_for_commands(message):
        return
    text = (message.text or "").lower().strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    if "ошибок" in text or "5" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
    elif "чек" in text or "диагност" in text:
        user_data[user_id]["file_type"] = "checklist"
    else:
        invalid_text = "Выбери один из предложенных вариантов ↓"
        markup = telebot.types.ReplyKeyboardMarkup(
            resize_keyboard=True, one_time_keyboard=True
        )
        markup.add("🔴 5 ошибок менеджеров")
        markup.add("📋 Чек-лист")
        msg = safe_send_message(chat_id, invalid_text, reply_markup=markup)
        if msg:
            save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return
    
    form_text = (
        "Спасибо за выбор 👍\n\n"
        "Перед отправкой файла заполним краткую анкету, чтобы понять чуть глубже ваш бизнес (1 минута).\n\n"
        " *Как тебя зовут?*"
    )
    msg = safe_send_message(
        chat_id,
        form_text,
        reply_markup=telebot.types.ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "files_name"

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
    duration_text = "⏰ Сколько времени функционирует твой бизнес?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "files_duration"

def ask_files_business_duration(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text
    telegram_text = "📱 Твой Telegram (@username) или номер телефона в формате +7-xxx-xxx-xx-xx"
    msg = safe_send_message(
        chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "files_contact"

def ask_files_telegram_check(message, user_id):
    if check_for_commands(message):
        return
    contact = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    
    if contact.startswith("@") or "t.me/" in contact.lower():
        if is_valid_telegram(contact):
            user_data[user_id]["telegram"] = contact
            business_text = (
                "🏢 Расскажи о своем бизнесе: ниша, продукт, главные проблемы в продажах"
            )
            msg = safe_send_message(chat_id, business_text)
            if msg:
                save_message_history(user_id, msg.message_id)
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "files_business"
        else:
            error_text = "Некорректный формат Telegram 📱\n\nИспользуй формат: *@username*"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
            # Остаемся в том же состоянии, если ошибка
            user_state[user_id] = "files_contact"
    elif contact.startswith("+7"):
        if is_valid_phone(contact):
            user_data[user_id]["phone"] = contact
            business_text = (
                "🏢 Расскажи о своем бизнесе: ниша, продукт, главные проблемы в продажах"
            )
            msg = safe_send_message(chat_id, business_text)
            if msg:
                save_message_history(user_id, msg.message_id)
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "files_business"
        else:
            error_text = "Некорректный формат номера ❌\n\nИспользуй +7 и 10 цифр номера"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "files_contact"
    else:
        error_text = "Некорректный ввод ❌\n\nВведи *@username* или номер телефона с +7"
        msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
        if msg:
            save_message_history(user_id, msg.message_id)
        if msg:
            save_message_history(user_id, msg.message_id)
        user_state[user_id] = "files_contact"

def ask_files_business(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = (message.text or "").strip()
    revenue_text = "💰 Выручка в месяц?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "files_revenue"

def finish_form_files(message, user_id):
    if check_for_commands(message):
        return
    user_data[user_id]["revenue"] = message.text
    app_data = user_data[user_id]
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    save_lead_files(user_id, app_data)
    update_user_action(user_id, "requested_files")
    log_action(user_id, app_data.get("name"), "FORM_FILES", "Заявка на материалы")
    
    sending_text = "⏳ Секундочку, отправляю файл..."
    msg = safe_send_message(
        chat_id, sending_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
    
    try:
        if app_data.get("file_type") == "5_mistakes":
            file_url = FILE_5_MISTAKES
            file_description = (
                "📄 *5 ОШИБОК МЕНЕДЖЕРОВ, КОТОРЫЕ ТЕРЯЮТ 50% ЛИДОВ*\n\n"
                "В этом материале разберемся, почему теряется заявки!\n\n"
                "✅ В конце получишь конкретные решения для каждой ошибки.\n\n"
                "💡 За счет исправления этих ошибок клиенты AI2BIZ экономят от 200K в месяц только на потерях."
            )
        else:
            file_url = FILE_CHECKLIST
            file_description = (
                "📋 *ЧЕК-ЛИСТ: 10 СПОСОБОВ ПОНЯТЬ, ТЕРЯЕТЕ ЛИ ВЫ ЛИДЫ*\n\n"
                "Пройди эту диагностику за 10-15 минут и узнай:\n\n"
                "✓ На каком этапе теряется больше всего заявок\n"
                "✓ Сколько денег утекает в месяц из-за утечек\n"
                "✓ Что можно улучшить без инвестиций\n"
                "✓ Четкий план действий на следующую неделю\n\n"
                "💰 *После улучшений,* в среднем, клиенты добавляют +150K в месячной выручке."
            )
        doc_msg = bot.send_document(
            chat_id, file_url, caption=file_description, parse_mode="Markdown"
        )
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
        log_action(user_id, app_data.get("name"), "FILE_SENT", "Файл отправлен")
        
        # Запускаем логику после файла (через 1 час "Что дальше?")
        if scheduler:
            scheduler.schedule_file_followup(user_id, chat_id)

        consultation_offer = (
            "✅ Файл отправлен!\n\n"
            " *Что дальше?*\n\n"
            "Материал показывает *проблемы*, но реальный рост начинается с *конкретного плана действий*.\n\n"
            "На *созвоне* мы разберем:\n"
            "🎯 Твою текущую воронку продаж и точки фокуса\n"
            "📊 Расчет потерь в деньгах\n"
            "💡 Конкретные шаги для увеличения конверсии\n"
            "💰 Как можно улучшить показатели за счет автоматизации\n\n"
            " *Напиши слово «консультация» и запишись на 30-минутный созвон с экспертом AI2BIZ* 👇"
        )
        msg = safe_send_message(chat_id, consultation_offer, parse_mode="Markdown")
        if msg:
            save_message_history(user_id, msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        error_msg = safe_send_message(chat_id, "Ошибка при отправке. Попробуй позже.")
        if error_msg:
            save_message_history(user_id, error_msg.message_id)
    
    # Сбрасываем состояние после завершения
    reset_user_state(user_id)

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
        if msg:
            save_message_history(user_id, msg.message_id)
        # Остаемся в том же состоянии если ошибка
        user_state[user_id] = "consultation_name"
        return
    user_data[user_id]["name"] = name
    duration_text = "⏰ Сколько времени функционирует твой бизнес?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_duration"

def ask_consultation_business_duration(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text
    telegram_text = "📱 Твой Telegram (@username) или номер телефона в формате +7-xxx-xxx-xx-xx"
    msg = safe_send_message(
        chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_contact"

def ask_consultation_telegram_check(message, user_id):
    if check_for_commands(message):
        return
    contact = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    
    if contact.startswith("@") or "t.me/" in contact.lower():
        if is_valid_telegram(contact):
            user_data[user_id]["telegram"] = contact
            email_text = "📧 Твой Email (name@example.com)"
            msg = safe_send_message(chat_id, email_text)
            if msg:
                save_message_history(user_id, msg.message_id)
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "consultation_email"
        else:
            error_text = "Некорректный формат Telegram 📱\n\nИспользуй формат: *@username*"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "consultation_contact"
    elif contact.startswith("+7"):
        if is_valid_phone(contact):
            user_data[user_id]["phone"] = contact
            email_text = "📧 Твой Email (name@example.com)"
            msg = safe_send_message(chat_id, email_text)
            if msg:
                save_message_history(user_id, msg.message_id)
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "consultation_email"
        else:
            error_text = "Некорректный формат номера ❌\n\nИспользуй +7 и 10 цифр номера"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
            user_state[user_id] = "consultation_contact"
    else:
        error_text = "Некорректный ввод ❌\n\nВведи *@username* или номер телефона с +7"
        msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
        if msg:
            save_message_history(user_id, msg.message_id)
        if msg:
            save_message_history(user_id, msg.message_id)
        user_state[user_id] = "consultation_contact"

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
        if msg:
            save_message_history(user_id, msg.message_id)
        user_state[user_id] = "consultation_email"
        return
    user_data[user_id]["email"] = email
    business_text = (
        "🏢 Какая ниша у бизнеса, и в чем на твой взгляд проблема в данный момент?"
    )
    msg = safe_send_message(chat_id, business_text)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_business"

def ask_consultation_business(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = (message.text or "").strip()
    revenue_text = "💰 Какая сейчас выручка в месяц?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_revenue"

def ask_consultation_revenue(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["revenue"] = message.text
    participants_text = "👥 Кто будет на созвоне?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("Я один", "Я с бизнес партнером")
    markup.add("Я не принимаю решений в компании")
    msg = safe_send_message(chat_id, participants_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_participants"

def ask_consultation_participants(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["participants"] = message.text
    time_text = "🕐 Когда удобно выйти в Zoom?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("Завтра 9-12", "Завтра 12-18")
    markup.add("После завтра", "В выходные")
    msg = safe_send_message(chat_id, time_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
    if msg:
        save_message_history(user_id, msg.message_id)
    user_state[user_id] = "consultation_time"

def finish_form_consultation(message, user_id):
    if check_for_commands(message):
        return
    user_data[user_id]["zoom_time"] = message.text
    app_data = user_data[user_id]
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    save_lead_consultation(user_id, app_data)
    update_user_action(user_id, "completed_consultation_form")
    log_action(
        user_id, app_data.get("name"), "FORM_CONSULTATION", "Заявка на консультацию"
    )
    # Останавливаем воронку
    if scheduler:
        scheduler.stop_funnel(user_id)

    notify_admin_consultation(app_data)
    
    confirmation = (
        "✅ *Заявка принята!*\n\n"
        " *Резюме:*\n"
        f"👤 *{app_data.get('name')}*\n"
        f"📧 {app_data.get('email')}\n"
        f"📱 {app_data.get('telegram') or app_data.get('phone')}\n"
        f"🕐 Предпочитаемое время: {app_data.get('zoom_time')}\n\n"
        "⏳ *Менеджер AI2BIZ свяжется с тобой в течение часа* и согласует точное время встречи.\n\n"
        "📍 *На консультации разберем:*\n"
        "• где теряются лиды\n"
        "• конкретный план внедрения автоматизации\n"
        "• сроки внедрения и окупаемость\n\n"
        "🎯 *Спасибо, что выбрал AI2BIZ!*\n"
        "Подпишись на канал *@it_ai2biz*, чтобы не пропустить наши кейсы и новости автоматизации 📣"
    )
    msg = safe_send_message(
        chat_id,
        confirmation,
        reply_markup=telebot.types.ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    if msg:
        save_message_history(user_id, msg.message_id)

    # Сбрасываем состояние
    reset_user_state(user_id)

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route("/")
def index():
    return (
        "\n\nСтатус: Активен (v8.0 Autofunnel)"
        "\n\nФорматирование: HTML/Markdown"
        "\n\nКоманды: /start, /help, /cancel, /commands"
        "\n\nАвтоворонка: Включена"
    )

# ===== ЗАПУСК =====
if __name__ == "__main__":
    print("✅ AI2BIZ Bot v8.0 Autofunnel запущен.")
    if not GSPREAD_AVAILABLE:
        print("⚠️ gspread не установлен. Добавьте в requirements.txt и выполните redeploy.")
    if scheduler:
        print("✅ Scheduler для дожимов активен")
    else:
        print("⚠️ Scheduler не инициализирован")
    app.run(host="0.0.0.0", port=5000, debug=False)
