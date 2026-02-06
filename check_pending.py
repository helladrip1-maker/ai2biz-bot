#!/usr/bin/env python3
"""
🚀 ИСПРАВЛЕННЫЙ CRON ДЛЯ RAILWAY
Устраняет ошибку invalid_scope и обеспечивает стабильную отправку.
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta
import pytz
import telebot
from telebot import types
import gspread

# Настройка путей для корректного импорта в Railway
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from messages import MESSAGES, FOLLOW_UP_PLAN
except ImportError:
    # В Railway корень проекта обычно находится в /app
    sys.path.insert(0, '/app')
    from messages import MESSAGES, FOLLOW_UP_PLAN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("check_pending")

# ПЕРЕМЕННЫЕ ИЗ ОКРУЖЕНИЯ
TOKEN = os.getenv("TOKEN")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")

# Инициализация бота
bot = telebot.TeleBot(TOKEN)
google_sheets_client = None

def init_google_sheets():
    """Инициализация подключения к Google Sheets с защитой от ошибок scope."""
    global google_sheets_client
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.error("❌ GOOGLE_SERVICE_ACCOUNT_JSON не найден в переменных окружения")
        return None
    
    try:
        # Очистка JSON от возможных проблемных символов (Railway иногда оборачивает в кавычки)
        clean_json = GOOGLE_SERVICE_ACCOUNT_JSON.strip()
        if clean_json.startswith("'") and clean_json.endswith("'"):
            clean_json = clean_json[1:-1]
        if clean_json.startswith('"') and clean_json.endswith('"'):
            clean_json = clean_json[1:-1]
            
        creds_dict = json.loads(clean_json)
        
        # Самый надежный метод авторизации: автоматически проставляет нужные Scopes
        client = gspread.service_account_from_dict(creds_dict)
        google_sheets_client = client.open_by_key(GOOGLE_SHEETS_ID)
        logger.info("✅ Google Sheets успешно подключен!")
        return google_sheets_client
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

def send_message_direct(chat_id, message_key, user_id):
    """Отправка сообщения через Telegram API с поддержкой кнопок."""
    msg_data = MESSAGES.get(message_key)
    if not msg_data:
        logger.error(f"❌ Сообщение {message_key} не найдено в messages.py")
        return False
    
    text = msg_data.get("text")
    buttons = msg_data.get("buttons")
    
    markup = None
    if buttons:
        markup = types.InlineKeyboardMarkup()
        for row in buttons:
            btns = []
            for btn in row:
                if "url" in btn:
                    btns.append(types.InlineKeyboardButton(text=btn["text"], url=btn["url"]))
                else:
                    btns.append(types.InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
            markup.add(*btns)
    
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        logger.info(f"✅ ОТПРАВЛЕНО {message_key} для {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
        return False

CUSTOM_FOLLOW_UP = {
    "message_file_followup": ("message_5", 23 * 60 + 50),
    "message_3_1": ("message_4", 10),
}

def get_next_plan(message_key):
    if message_key in FOLLOW_UP_PLAN:
        return FOLLOW_UP_PLAN[message_key]
    return CUSTOM_FOLLOW_UP.get(message_key)

def check_pending_messages():
    """Проверка просроченных сообщений в таблице и их отправка."""
    if not google_sheets_client:
        return
    
    try:
        worksheet = google_sheets_client.worksheet("Users")
        all_records = worksheet.get_all_records()
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        logger.info(f"🔍 Сканирую таблицу... Сейчас (МСК): {now.strftime('%H:%M:%S')}")
        
        processed_count = 0
        
        def record_get(record, *keys):
            for key in keys:
                val = record.get(key)
                if val is not None and str(val).strip() != "":
                    return val
            return ""

        for idx, record in enumerate(all_records):
            user_id_val = record.get("User ID")
            if not user_id_val:
                continue
            
            user_id = str(user_id_val)
            next_msg = str(record_get(record, "Next Scheduled Message", "Next Msg")).strip()
            run_date_str = str(record_get(record, "Run Date", "Time")).strip()
            chat_id = record_get(record, "Chat ID") or user_id
            
            if next_msg and run_date_str:
                try:
                    # Попытка распарсить дату
                    run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
                    run_date = moscow_tz.localize(run_date)
                    
                    if run_date <= now:
                        logger.info(f"🔔 Время пришло! User: {user_id}, Сообщение: {next_msg}")
                        
                        # 1. Очищаем ячейки СРАЗУ (защита от повторной отправки следующим кроном)
                        row_num = idx + 2  # +2 из-за заголовка и 0-индексации
                        worksheet.update(values=[["", ""]], range_name=f'J{row_num}:K{row_num}')
                        
                        # 2. Отправляем сообщение
                        if send_message_direct(chat_id, next_msg, user_id):
                            processed_count += 1
                            worksheet.update(values=[[next_msg, now.strftime("%Y-%m-%d %H:%M:%S"), "OK"]], range_name=f'M{row_num}:O{row_num}')
                            
                            # 3. Планируем следующее сообщение по цепочке из FOLLOW_UP_PLAN
                            plan = get_next_plan(next_msg)
                            if plan:
                                next_key, delay_minutes = plan
                                next_run_time = now + timedelta(minutes=delay_minutes)
                                date_str = next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                                
                                worksheet.update(values=[[next_key, date_str]], range_name=f'J{row_num}:K{row_num}')
                                logger.info(f"📅 Новая задача в цепочке: {next_key} через {delay_minutes} мин")
                        else:
                            worksheet.update(values=[[next_msg, now.strftime("%Y-%m-%d %H:%M:%S"), "ERROR"]], range_name=f'M{row_num}:O{row_num}')
                                
                except Exception as e:
                    logger.error(f"❌ Ошибка в строке {idx+2} (User {user_id}): {e}")
        
        logger.info(f"📊 Обработка завершена. Отправлено за этот запуск: {processed_count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при работе с листом 'Users': {e}")

if __name__ == "__main__":
    if init_google_sheets():
        check_pending_messages()
    logger.info("🏁 Работа Cron-скрипта завершена.")
