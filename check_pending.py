#!/usr/bin/env python3
"""
🚀 ПОЛНЫЙ РАБОЧИЙ CRON с ОТПРАВКОЙ и ПЛАНИРОВАНИЕМ
Исправлена ошибка invalid_scope и логика кнопок.
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

# Настройка путей для Railway
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from messages import MESSAGES, FOLLOW_UP_PLAN
except ImportError:
    # В Railway корень обычно в /app
    sys.path.insert(0, '/app')
    from messages import MESSAGES, FOLLOW_UP_PLAN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("check_pending")

TOKEN = os.getenv("TOKEN")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")

bot = telebot.TeleBot(TOKEN)
google_sheets = None

def init_google_sheets():
    global google_sheets
    
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.error("❌ GOOGLE_SERVICE_ACCOUNT_JSON не установлен")
        return None
    
    try:
        # Парсим JSON
        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        # gspread.service_account_from_dict сам проставляет нужные scopes
        client = gspread.service_account_from_dict(creds_dict)
        sheet = client.open_by_key(GOOGLE_SHEETS_ID)
        google_sheets = sheet
        logger.info("✅ Google Sheets подключен успешно!")
        return sheet
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

def send_message_direct(chat_id, message_key, user_id):
    """Отправка сообщения с кнопками"""
    msg_data = MESSAGES.get(message_key)
    if not msg_data:
        logger.error(f"❌ Сообщение {message_key} не найдено")
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
        logger.info(f"✅ ОТПРАВЛЕНО {message_key} → {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки {user_id}: {e}")
        return False

def check_pending_messages():
    if not google_sheets:
        return
    
    try:
        worksheet = google_sheets.worksheet("Users")
        # Получаем все данные одним запросом
        all_records = worksheet.get_all_records()
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        logger.info(f"🔍 Проверка {len(all_records)} строк | Сейчас: {now.strftime('%H:%M:%S')}")
        
        for idx, record in enumerate(all_records):
            user_id_val = record.get("User ID")
            if not user_id_val:
                continue
                
            try:
                user_id = str(user_id_val)
                chat_id = record.get("Chat ID") or user_id
                next_msg = record.get("Next Scheduled Message", "").strip()
                run_date_str = record.get("Run Date", "").strip()
                
                if not next_msg or not run_date_str:
                    continue
                
                # Парсим дату
                run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
                run_date = moscow_tz.localize(run_date)
                
                if run_date <= now:
                    logger.info(f"🔔 Время пришло для {user_id}: {next_msg}")
                    
                    # 1. Сначала очищаем задачу в таблице (защита от дублей)
                    row_num = idx + 2
                    worksheet.update(values=[["", ""]], range_name=f'J{row_num}:K{row_num}')
                    
                    # 2. Отправляем сообщение
                    if send_message_direct(chat_id, next_msg, user_id):
                        # 3. Планируем следующее по цепочке
                        plan = FOLLOW_UP_PLAN.get(next_msg)
                        if plan:
                            next_next_msg, minutes = plan
                            new_run_date = now + timedelta(minutes=minutes)
                            date_str = new_run_date.strftime("%Y-%m-%d %H:%M:%S")
                            
                            worksheet.update(values=[[next_next_msg, date_str]], range_name=f'J{row_num}:K{row_num}')
                            logger.info(f"📅 Следующее: {next_next_msg} через {minutes} мин")
                            
            except Exception as e:
                logger.error(f"❌ Ошибка обработки строки {idx+2}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка чтения таблицы: {e}")

if __name__ == "__main__":
    if init_google_sheets():
        check_pending_messages()
    logger.info("✅ Завершено")
