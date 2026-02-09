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
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check-list%20AI2BIZ.pdf?v=20260209"
)

FILE_CASE_DEUTSCHER = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/%20Case%20Deutscher%20Agent%20AI2BIZ.pdf?v=20260209"
)

FILE_AVTOVORONKI = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/Avtovoronki%20AI2BIZ.pdf?v=20260209"
)

FILE_AI = (
    "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/"
    "bot-files/AI%20for%20Business%20AI2BIZ.pdf?v=20260209"
)

FILE_CACHE_PATH = "file_cache.json"
FILE_CACHE = {}

def load_file_cache():
    """Загружает кэш file_id из файла."""
    global FILE_CACHE
    if os.path.exists(FILE_CACHE_PATH):
        try:
            with open(FILE_CACHE_PATH, "r") as f:
                FILE_CACHE = json.load(f)
            print(f"✅ Кэш файлов загружен: {len(FILE_CACHE)} файлов")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
            FILE_CACHE = {}
    else:
        FILE_CACHE = {}

def save_file_cache():
    """Сохраняет кэш file_id в файл."""
    try:
        with open(FILE_CACHE_PATH, "w") as f:
            json.dump(FILE_CACHE, f)
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения кэша: {e}")

def send_cached_document(chat_id, file_url, caption=None, parse_mode=None):
    """
    Отправляет документ, используя кэшированный file_id если есть.
    Если нет - отправляет по URL и сохраняет file_id.
    """
    file_id = FILE_CACHE.get(file_url)
    sent_msg = None
    
    # 1. Пробуем отправить по file_id
    if file_id:
        try:
            logger.info(f"📤 Отправка файла из кэша: {file_url[:30]}...")
            sent_msg = bot.send_document(chat_id, file_id, caption=caption, parse_mode=parse_mode)
            return sent_msg
        except Exception as e:
            logger.warning(f"⚠️ Ошибка отправки по file_id (возможно устарел): {e}")
            # Если ошибка - удаляем из кэша и пробуем по URL
            FILE_CACHE.pop(file_url, None)
            save_file_cache()

    # 2. Отправляем по URL (если нет в кэше или ошибка)
    try:
        logger.info(f"🌐 Скачивание и отправка файла: {file_url[:30]}...")
        sent_msg = bot.send_document(chat_id, file_url, caption=caption, parse_mode=parse_mode)
        
        # 3. Сохраняем file_id в кэш
        if sent_msg and sent_msg.document:
            FILE_CACHE[file_url] = sent_msg.document.file_id
            save_file_cache()
            logger.info("✅ file_id сохранен в кэш")
            
        return sent_msg
    except Exception as e:
        logger.error(f"❌ Ошибка отправки документа по URL: {e}")
        return None

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
            worksheet = sheet.add_worksheet("Users", 1000, 12)
            worksheet.append_row([
                "User ID", "Username", "Name", "Started", 
                "Last Action", "State", "Lead Quality", "Answers", "Messages Sent",
                "Next Scheduled Message", "Run Date", "Chat ID",
                "Last Sent Message", "Last Sent At", "Last Send Status"
            ])
            print("✅ Создан лист Users")
        else:
            # Обновляем заголовок, если отсутствует Chat ID
            try:
                worksheet = sheet.worksheet("Users")
                headers = worksheet.row_values(1)
                if "Chat ID" not in headers:
                    worksheet.update_cell(1, 12, "Chat ID")
                if "Last Sent Message" not in headers:
                    worksheet.update_cell(1, 13, "Last Sent Message")
                if "Last Sent At" not in headers:
                    worksheet.update_cell(1, 14, "Last Sent At")
                if "Last Send Status" not in headers:
                    worksheet.update_cell(1, 15, "Last Send Status")
            except Exception:
                pass
        
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
scheduler = FollowUpScheduler(bot, user_data, google_sheets)
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

def contains_letters(text):
    """Проверяет, содержит ли текст хотя бы одну букву (латиница или кириллица)."""
    return bool(re.search(r'[a-zA-Zа-яА-ЯёЁ]', text))

def is_valid_name(name):
    """Проверяет валидность имени."""
    name = name.strip()
    return 2 <= len(name) <= 50 and contains_letters(name)

def is_valid_business(text):
    """Проверяет валидность поля ниши/проблем (минимум 10 символов + буквы)."""
    text = text.strip()
    return len(text) >= 10 and contains_letters(text)

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

def create_or_update_user(user_id, username, first_name, action="", state="", chat_id=None):
    """Создает или обновляет запись пользователя в Google Sheets."""
    if not google_sheets:
        return False
    
    try:
        worksheet = google_sheets.worksheet("Users")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Пытаемся найти пользователя
        # Используем поиск по первому столбцу для надежности
        try:
            cell = worksheet.find(str(user_id), in_column=1)
            row = cell.row
            
            # Обновляем существующую запись
            worksheet.update_cell(row, 2, username or "")  # Username
            worksheet.update_cell(row, 3, first_name or "")  # Name
            if action:
                worksheet.update_cell(row, 5, action)  # Last Action
            if state:
                worksheet.update_cell(row, 6, state)  # State
            if chat_id is not None:
                worksheet.update_cell(row, 12, str(chat_id))  # Chat ID
            logger.info(f"✅ Обновлена запись пользователя {user_id}")
        except Exception:
            # Создаем новую запись со всеми полями (включая пустые для планировщика)
            worksheet.append_row([
                str(user_id),
                username or "",
                first_name or "",
                timestamp,
                action or "",
                state or "initial",
                "",  # Lead Quality
                "",  # Answers
                "0", # Messages Sent
                "",  # Next Scheduled Message (col 10)
                "",  # Run Date (col 11)
                str(chat_id) if chat_id is not None else "",  # Chat ID (col 12)
                "",  # Last Sent Message (col 13)
                "",  # Last Sent At (col 14)
                ""   # Last Send Status (col 15)
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
        cell = worksheet.find(str(user_id), in_column=1)
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

def get_all_registered_users():
    """Возвращает список всех зарегистрированных пользователей из таблицы."""
    if not google_sheets:
        return []
    try:
        worksheet = google_sheets.worksheet("Users")
        all_records = worksheet.get_all_records()
        user_ids = []
        for record in all_records:
            user_id = record.get("User ID")
            if user_id:
                try:
                    user_ids.append(int(user_id))
                except ValueError:
                    user_ids.append(str(user_id))
        return list(set(user_ids)) # Убираем дубликаты на всякий случай
    except Exception as e:
        logger.error(f"❌ Ошибка получения списка пользователей: {e}")
        return []

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

def reset_user_state(user_id, resume=True):
    """Очищает состояние пользователя."""
    user_data.pop(user_id, None)
    user_state.pop(user_id, None)
    form_answers.pop(user_id, None)
    if scheduler:
        scheduler.cancel_consultation_followups(user_id)
        if resume:
            scheduler.resume_funnel(user_id)

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

# ===== /REFRESH_FILES =====
@bot.message_handler(commands=["refresh_files"])
def process_refresh_files_command(message):
    """Обрабатывает команду /refresh_files (только админ)."""
    user_id = message.from_user.id
    logger.info(f"🔄 Команда /refresh_files от {user_id}. ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
    
    if user_id != ADMIN_CHAT_ID:
        bot.reply_to(message, f"⛔ Доступ запрещен. Ваш ID: {user_id}. Требуется: {ADMIN_CHAT_ID}")
        return
    
    global FILE_CACHE
    FILE_CACHE = {}
    save_file_cache()
    bot.reply_to(message, "♻️ Кэш файлов очищен. Следующая отправка заново скачает файлы с сервера.")


def check_for_commands(message):
    """Проверяет /cancel или /help."""
    if not message.text:
        return False
    text = message.text.strip()
    logger.info(f"DEBUG_CHECK_COMMANDS: '{text}' (len={len(text)})")
    if text == "/cancel":
        process_cancel_command(message)
        return True
    if text == "/help":
        process_help_command(message)
        return True
    if text == "/refresh_files":
        logger.info(f"MATCHED REFRESH_FILES COMMAND: {text}")
        process_refresh_files_command(message)
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
    
    # Всегда сбрасываем состояние при старте/перезапуске
    reset_user_state(user_id)
    create_or_update_user(user_id, username, user_name, "START_FUNNEL", "initial", chat_id=chat_id)
    
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
            image = msg_data.get("image")
            if image:
                msg = bot.send_photo(chat_id, image, caption=text, reply_markup=markup, parse_mode="HTML")
            else:
                msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            
            if msg:
                welcome_message_ids[user_id] = msg.message_id
                save_message_history(user_id, msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка отправки welcome: {e}")

    # Запланировать следующий шаг (message_1 через 10 минут)
    if scheduler:
        scheduler.schedule_next_message(user_id, chat_id, "message_0")

def recovery_handler(user_id, chat_id):
    """Обработчик восстановления воронки для диплинк-лидов."""
    logger.info(f"Запуск восстановления воронки для {user_id}")
    
    # Создаем фиктивное сообщение для совместимости с send_welcome_internal
    class MockMessage:
        def __init__(self, uid, cid):
            self.from_user = type('User', (), {'id': uid, 'first_name': 'Партнер', 'username': ''})
            self.chat = type('Chat', (), {'id': cid})
    
    msg = MockMessage(user_id, chat_id)
    send_welcome_internal(msg)

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
        telebot.types.InlineKeyboardButton("📚 Файлы", callback_data="show_file_menu"),
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
    
    # Проверка на deep link
    text_parts = message.text.split()
    if len(text_parts) > 1 and text_parts[1] == "consult":
        start_consultation_direct(message)
        return

    send_welcome_internal(message)

def safe_delete_message(chat_id, message_id):
    """Безопасно удаляет сообщение, игнорируя ошибки."""
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def start_consultation_direct(message):
    """Немедленный запуск процесса записи (deep link)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя /start consult
    safe_delete_message(chat_id, message.message_id)
    
    # Симуляция удаления: шлем сервисное сообщение и удаляем его
    temp_msg = bot.send_message(chat_id, "⏳ Подключаю специалиста...")
    safe_delete_message(chat_id, temp_msg.message_id)
    
    update_user_action(user_id, "consultation_requested_deeplink")
    reset_user_state(user_id)
    
    # Ставим метку ПОСЛЕ reset_user_state
    user_data[user_id] = {"entry_source": "deeplink_consult"}
    user_state[user_id] = "consultation"
    
    consultation_text = (
        "📞 *Отлично, давай запишемся на консультацию*\n\n"
        "Расскажите немного о себе, и мы подготовимся к нашей встрече.\n\n"
        " *Как вас зовут?*"
    )
    msg = safe_send_message(
        chat_id,
        consultation_text,
        reply_markup=telebot.types.ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    if msg:
        save_message_history(user_id, msg.message_id)
        # Планируем напоминание через 5 минут
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_name")
    
    bot.register_next_step_handler(msg, ask_consultation_name, user_id)

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
        " */commands* – этот список\n"
        
        "Или просто напиши:\n"
        " *файлы* – получить бесплатные материалы\n"
        " *консультация* – записаться на консультацию"
    )
    msg = safe_send_message(chat_id, commands_text, parse_mode="Markdown")
    if msg:
        save_message_history(user_id, msg.message_id)
    # send_welcome_internal(message) - убрали, чтобы не спамить START сообщением
    # Лучше показать меню
    send_old_menu(message)

# ===== /BROADCAST_ALL (Admin Only) =====
@bot.message_handler(commands=["broadcast_all"])
def broadcast_all_command(message):
    user_id = message.from_user.id
    if user_id != ADMIN_CHAT_ID:
        logger.warning(f"🚫 Попытка доступа к рассылке от пользователя {user_id}")
        return

    # Получаем сообщение после команды
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) > 1:
        broadcast_message = text_parts[1]
        confirm_broadcast(message, broadcast_message)
    else:
        msg = bot.send_message(message.chat.id, "📝 Отправьте текст для рассылки всем пользователям:")
        bot.register_next_step_handler(msg, process_broadcast_input)

def process_broadcast_input(message):
    if not message.text or message.text.startswith("/"):
        bot.send_message(message.chat.id, "❌ Рассылка отменена или некорректный текст.")
        return
    confirm_broadcast(message, message.text)

def confirm_broadcast(message, text):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("✅ Отправить всем", callback_data="confirm_broadcast"),
        telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")
    )
    # Сохраняем временные данные
    if message.from_user.id not in user_data:
        user_data[message.from_user.id] = {}
    user_data[message.from_user.id]["broadcast_text"] = text
    
    bot.send_message(
        message.chat.id,
        f"⚠️ *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\nТекст:\n---\n{text}\n---\n\n*Вы уверены?*",
        parse_mode="Markdown",
        reply_markup=markup
    )

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
            # Сразу запускаем воронку Message 4 (Чек-лист)
            if scheduler:
                scheduler.send_message_direct(user_id, chat_id, "message_4")
        
        elif callback_data == "show_file_menu":
            bot.answer_callback_query(call.id)
            if scheduler:
                scheduler.send_message_direct(user_id, chat_id, "message_file_menu", schedule_next=False)
        
        elif callback_data == "consultation":
            bot.answer_callback_query(call.id)
            reset_user_state(user_id)
            user_state[user_id] = "consultation_name"
            user_data[user_id] = {}
            consultation_text = (
                "📞 *Отлично, давайте запишемся на консультацию*\n\n"
                "Расскажите немного о себе, и мы подготовимся к нашей встрече.\n\n"
                " *Как вас зовут?*"
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
            if scheduler:
                # Используем send_message_job(..., schedule_next=False), чтобы не прерывать воронку
                scheduler.send_message_job(user_id, chat_id, "message_3", schedule_next=False)
        
        elif callback_data == "start_form":
            bot.answer_callback_query(call.id)
            start_diagnostic_form(call.message, user_id)
        
        elif callback_data == "download_checklist":
            bot.answer_callback_query(call.id)
            send_checklist_file(user_id, chat_id)
            
        elif callback_data == "get_case_file":
            bot.answer_callback_query(call.id)
            send_case_file(user_id, chat_id)
        
        elif callback_data == "get_avto_file":
            bot.answer_callback_query(call.id)
            send_avtovoronki_file(user_id, chat_id)

        elif callback_data == "get_ai_file":
            bot.answer_callback_query(call.id)
            send_ai_file(user_id, chat_id)
        
        elif callback_data.startswith("answer_"):
            bot.answer_callback_query(call.id)
            handle_form_answer(call, user_id)
        
        elif callback_data == "confirm_broadcast":
            bot.answer_callback_query(call.id, "🚀 Запуск...")
            broadcast_text = user_data.get(user_id, {}).get("broadcast_text")
            if not broadcast_text:
                bot.send_message(chat_id, "❌ Ошибка: текст рассылки не найден.")
                return
            
            # Начинаем рассылку
            users = get_all_registered_users()
            bot.edit_message_text(f"⏳ Рассылка запущена для {len(users)} пользователей...", chat_id=chat_id, message_id=call.message.message_id)
            
            success_count = 0
            fail_count = 0
            for uid in users:
                try:
                    bot.send_message(uid, broadcast_text, parse_mode="HTML")
                    success_count += 1
                except Exception as e:
                    logger.warning(f"❌ Ошибка отправки пользователю {uid}: {e}")
                    fail_count += 1
            
            bot.send_message(chat_id, f"🏁 *Рассылка завершена!*\n\n✅ Успешно: {success_count}\n❌ Ошибок: {fail_count}", parse_mode="Markdown")
            # Очищаем временные данные
            if user_id in user_data:
                user_data[user_id].pop("broadcast_text", None)

        elif callback_data == "cancel_broadcast":
            bot.answer_callback_query(call.id, "Отменено")
            bot.edit_message_text("❌ Рассылка отменена администратором.", chat_id=chat_id, message_id=call.message.message_id)
            if user_id in user_data:
                user_data[user_id].pop("broadcast_text", None)
        
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
    
    # Сбрасываем состояние, НО НЕ ВОЗОБНОВЛЯЕМ ВОРОНКУ (т.к. анкету заполнили)
    reset_user_state(user_id, resume=False)

def send_checklist_file(user_id, chat_id):
    """Отправляет PDF чек-лист и планирует следующие сообщения."""
    update_user_action(user_id, "downloaded_checklist")
    u_data = user_data.get(user_id, {})
    name = u_data.get("name", "User")
    log_action(user_id, name, "CHECKLIST_REQUESTED", "Запросил чек-лист")

    sending_text = "⏳ Секундочку, отправляю чек-лист..."
    msg = safe_send_message(chat_id, sending_text, reply_markup=telebot.types.ReplyKeyboardRemove())
    if msg:
        save_message_history(user_id, msg.message_id)

    try:
        # Текст из message_file_checklist (Message 4.1)
        caption = MESSAGES.get("message_file_checklist", {}).get("text", "Ваш чеклист 📂")
        
        doc_msg = send_cached_document(
            chat_id, FILE_CHECKLIST, caption=caption, parse_mode="HTML"
        )
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
            
        log_action(user_id, name, "CHECKLIST_SENT", "Чек-лист отправлен")

        # Запускаем логику после файла (через 1 час "Что дальше?" и далее)
        if scheduler:
            scheduler.schedule_message_4_followup(user_id, chat_id)

    except Exception as e:
        logger.error(f"Ошибка отправки чек-листа: {e}")
        safe_send_message(chat_id, "Ошибка при отправке чек-листа. Попробуй позже.")

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

    
    # КЕЙСЫ
    if any(word in text for word in ["кейс", "deu", "agent", "разбор", "case"]):
        if scheduler:
            # Используем send_message_job(..., schedule_next=False), чтобы не прерывать воронку
            scheduler.send_message_job(user_id, chat_id, "message_3", schedule_next=False)
        else:
            send_case_file(user_id, chat_id)
        return

    # МАТЕРИАЛЫ И ЧЕК-ЛИСТ (Message 4)
    # Только по конкретным ключам: чек, чек-лист, чеклист, 10, десять, ошиб
    if any(word in text for word in ["чек", "10", "десять", "ошиб"]):
        if scheduler:
            # Не прерываем воронку
            scheduler.send_message_job(user_id, chat_id, "message_4", schedule_next=False)
        return

    # МЕНЮ ВЫБОРА ГАЙДОВ (Дополнительные материалы)
    # По словам: гайд, файл, кп, воронка, ИИ, автоматизация, ai
    if any(word in text for word in ["гайд", "файл", "кп", "воронк", "ии", "автоматизация", "ai"]):
        if scheduler:
            # Не прерываем воронку
            scheduler.send_message_job(user_id, chat_id, "message_file_menu", schedule_next=False)
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
            "📞 *Отлично, давайте запишемся на консультацию*\n\n"
            "Расскажите немного о себе, и мы подготовимся к нашей встрече.\n\n"
            " *Как вас зовут?*"
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

# ЦЕПОЧКА: МАТЕРИАЛЫ - УДАЛЕНО (теперь напрямую через message_4)

    
def send_case_file(user_id, chat_id):
    """Отправляет PDF с кейсом Deutscher Agent и планирует следующие сообщения."""
    # Логируем
    update_user_action(user_id, "requested_case")
    # Получаем имя (если известно)
    u_data = user_data.get(user_id, {})
    name = u_data.get("name", "User")
    log_action(user_id, name, "CASE_REQUESTED", "Запросил кейс")

    sending_text = "⏳ Секундочку, отправляю кейс..."
    msg = safe_send_message(
        chat_id, sending_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)

    try:
        # Текст из message_case_presentation
        caption = MESSAGES.get("message_case_presentation", {}).get("text", "Ваш кейс 📂")
        
        doc_msg = send_cached_document(
            chat_id, FILE_CASE_DEUTSCHER, caption=caption, parse_mode="HTML"
        )
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
            
        log_action(user_id, name, "CASE_SENT", "Кейс отправлен")

        # Планируем СЛЕДУЮЩИЕ сообщения (message 3.1 и message 4)
        if scheduler:
            scheduler.schedule_message_3_followup(user_id, chat_id)

    except Exception as e:
        logger.error(f"Ошибка отправки кейса: {e}")
        safe_send_message(chat_id, "Ошибка при отправке кейса. Попробуй позже.")

def send_avtovoronki_file(user_id, chat_id):
    """Отправляет PDF по автоворонкам."""
    u_data = user_data.get(user_id, {})
    name = u_data.get("name", "User")
    log_action(user_id, name, "AVTOVORONKI_REQUESTED", "Запросил гайд по автоворонкам")

    try:
        caption = MESSAGES.get("message_file_avtovoronki", {}).get("text", "Ваш гайд по автоворонкам 📂")
        doc_msg = send_cached_document(chat_id, FILE_AVTOVORONKI, caption=caption, parse_mode="HTML")
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
        log_action(user_id, name, "AVTOVORONKI_SENT", "Гайд по автоворонкам отправлен")
    except Exception as e:
        logger.error(f"Ошибка отправки файла автоворонок: {e}")
        safe_send_message(chat_id, "Ошибка при отправке файла. Попробуй позже.")

def send_ai_file(user_id, chat_id):
    """Отправляет PDF по ИИ."""
    u_data = user_data.get(user_id, {})
    name = u_data.get("name", "User")
    log_action(user_id, name, "AI_GUIDE_REQUESTED", "Запросил гайд по ИИ")

    try:
        caption = MESSAGES.get("message_file_ai", {}).get("text", "Ваш гайд по ИИ 🤖")
        doc_msg = send_cached_document(chat_id, FILE_AI, caption=caption, parse_mode="HTML")
        if doc_msg:
            save_message_history(user_id, doc_msg.message_id)
        log_action(user_id, name, "AI_GUIDE_SENT", "Гайд по ИИ отправлен")
    except Exception as e:
        logger.error(f"Ошибка отправки файла ИИ: {e}")
        safe_send_message(chat_id, "Ошибка при отправке файла. Попробуй позже.")

# ===== ЦЕПОЧКА: КОНСУЛЬТАЦИЯ =====
def ask_consultation_name(message, user_id):

    if check_for_commands(message):
        return
    name = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    # Пришел ответ - отменяем дожимы
    if scheduler:
        scheduler.cancel_consultation_followups(user_id)

    if not is_valid_name(name):
        if len(name) < 2:
            error_text = "Имя должно быть не короче 2 символов"
        elif not contains_letters(name):
            error_text = "Имя должно содержать буквы, а не только цифры или символы 👤"
        else:
            error_text = "Имя слишком длинное (макс. 50 символов)"
            
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            if scheduler:
                scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_name")
        bot.register_next_step_handler(message, ask_consultation_name, user_id)
        return
    user_data[user_id]["name"] = name
    duration_text = "⏰ Сколько времени функционирует ваш бизнес?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    msg = safe_send_message(chat_id, duration_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        # Планируем дожим для следующего шага
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_business_duration")
    user_state[user_id] = "consultation_duration"

def ask_consultation_business_duration(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)

    user_data[user_id]["business_duration"] = message.text
    telegram_text = "📱 Ваш Telegram (@username) или номер телефона начиная с +7"
    msg = safe_send_message(
        chat_id, telegram_text, reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    if msg:
        save_message_history(user_id, msg.message_id)
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_contact")
    user_state[user_id] = "consultation_contact"

def ask_consultation_telegram_check(message, user_id):
    if check_for_commands(message):
        return
    contact = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)
    
    if contact.startswith("@") or "t.me/" in contact.lower():
        if is_valid_telegram(contact):
            user_data[user_id]["telegram"] = contact
            email_text = "📧 Твой Email (name@example.com)"
            msg = safe_send_message(chat_id, email_text)
            if msg:
                save_message_history(user_id, msg.message_id)
                if scheduler:
                    scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_email")
            user_state[user_id] = "consultation_email"
        else:
            error_text = "Некорректный формат Telegram 📱\n\nИспользуй формат: *@username*"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
                if scheduler:
                    scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_contact")
            user_state[user_id] = "consultation_contact"
    elif contact.startswith("+7"):
        if is_valid_phone(contact):
            user_data[user_id]["phone"] = contact
            email_text = "📧 Твой Email (name@example.com)"
            msg = safe_send_message(chat_id, email_text)
            if msg:
                save_message_history(user_id, msg.message_id)
                if scheduler:
                    scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_email")
            user_state[user_id] = "consultation_email"
        else:
            error_text = "Некорректный формат номера ❌\n\nИспользуй +7 и 10 цифр номера"
            msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
            if msg:
                save_message_history(user_id, msg.message_id)
                if scheduler:
                    scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_contact")
            user_state[user_id] = "consultation_contact"
    else:
        error_text = "Некорректный ввод ❌\n\nВведите *@username* или номер телефона с +7"
        msg = safe_send_message(chat_id, error_text, parse_mode="Markdown")
        if msg:
            save_message_history(user_id, msg.message_id)
            if scheduler:
                scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_contact")
        user_state[user_id] = "consultation_contact"

def ask_consultation_email_check(message, user_id):
    if check_for_commands(message):
        return
    email = (message.text or "").strip()
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)

    if not is_valid_email(email):
        error_text = "Некорректный Email"
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            if scheduler:
                scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_email")
        user_state[user_id] = "consultation_email"
        return
    user_data[user_id]["email"] = email
    business_text = (
        "🏢 Какая ниша у бизнеса, и в чем на ваш взгляд проблема в данный момент?"
    )
    msg = safe_send_message(chat_id, business_text)
    if msg:
        save_message_history(user_id, msg.message_id)
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_business")
    user_state[user_id] = "consultation_business"

def ask_consultation_business(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    business_desc = (message.text or "").strip()
    if not is_valid_business(business_desc):
        if len(business_desc) < 10:
            error_text = "Пожалуйста, опишите нишу и проблему чуть подробнее (минимум 10 символов) ✍️"
        else:
            error_text = "Ваш ответ должен содержать текст (буквы), а не только символы или эмодзи."
            
        msg = safe_send_message(chat_id, error_text)
        if msg:
            save_message_history(user_id, msg.message_id)
            if scheduler:
                scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_business")
        bot.register_next_step_handler(message, ask_consultation_business, user_id)
        return

    user_data[user_id]["business"] = business_desc
    revenue_text = "💰 Какая сейчас выручка в месяц?"
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    msg = safe_send_message(chat_id, revenue_text, reply_markup=markup)
    if msg:
        save_message_history(user_id, msg.message_id)
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_revenue")
    user_state[user_id] = "consultation_revenue"

def ask_consultation_revenue(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)

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
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_participants")
    user_state[user_id] = "consultation_participants"

def ask_consultation_participants(message, user_id):
    if check_for_commands(message):
        return
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)

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
        if scheduler:
            scheduler.schedule_consultation_followup(user_id, chat_id, "consult_followup_time")
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

    if scheduler:
        scheduler.cancel_consultation_followups(user_id)
        scheduler.stop_funnel(user_id)

    notify_admin_consultation(app_data)
    
    confirmation = (
        "✅ *Заявка принята!*\n\n"
        " *Резюме:*\n"
        f"👤 *{app_data.get('name')}*\n"
        f"📧 {app_data.get('email')}\n"
        f"📱 {app_data.get('telegram') or app_data.get('phone')}\n"
        f"🕐 Предпочитаемое время: {app_data.get('zoom_time')}\n\n"
        "⏳ *Менеджер AI2BIZ свяжется с вами в течение часа* и согласует точное время встречи.\n\n"
        "📍 *На консультации разберем:*\n"
        "• где теряются лиды\n"
        "• конкретный план внедрения автоматизации\n"
        "• сроки внедрения и окупаемость\n\n"
        "🎯 *Спасибо, что выбрали AI2BIZ!*\n"
        "Подпишитесь на канал *@it_ai2biz*, чтобы не пропустить наши кейсы и новости автоматизации 📣"
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
    # Сбрасываем состояние, НО НЕ ВОЗОБНОВЛЯЕМ ВОРОНКУ (т.к. анкету заполнили)
    reset_user_state(user_id, resume=False)

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route("/")
def index():
    return (
        "\n\nСтатус: Активен (v8.0 Autofunnel)"
        "\n\nФорматирование: HTML/Markdown"
        "\n\nКоманды: /start, /help, /cancel, /commands"
        "\n\nАвтоворонка: Включена"
    )


# ===== ИНИЦИАЛИЗАЦИЯ (Работает и при импорте в Gunicorn) =====
print("✅ STARTUP: AI2BIZ Bot v8.1 (Gunicorn Fix) Инициализация...")
load_file_cache()

# ===== WEBHOOK SETUP =====
# Force webhook registration to ensure this instance receives updates
WEBHOOK_URL_FULL = WEBHOOK_URL + TOKEN
try:
    logger.info(f"Setting webhook to: {WEBHOOK_URL_FULL}")
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL_FULL)
    logger.info("✅ Webhook set successfully")
except Exception as e:
    logger.error(f"❌ Failed to set webhook: {e}")

# ===== ЗАПУСК (Только локально) =====
if __name__ == "__main__":
    print("✅ LOCAL: AI2BIZ Bot v8.1 запушен локально.")
    if not GSPREAD_AVAILABLE:
        print("⚠️ gspread не установлен. Добавьте в requirements.txt и выполните redeploy.")
    if scheduler:
        print("✅ Scheduler для дожимов активен")
        scheduler.recovery_callback = recovery_handler
    else:
        print("⚠️ Scheduler не инициализирован")
    app.run(host="0.0.0.0", port=5000, debug=False)
