#!/usr/bin/env python3
import os
import sys
import json
import logging
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials
import telebot
from telebot import types

# Добавляем текущую директорию в путь для импорта messages
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from messages import MESSAGES, FOLLOW_UP_PLAN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("check_pending")

# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

def init_google_sheets():
    """Инициализация подключения к Google Sheets."""
    try:
        if not GOOGLE_SERVICE_ACCOUNT_JSON:
            logger.error("❌ GOOGLE_SERVICE_ACCOUNT_JSON не установлен")
            return None
        
        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEETS_ID)
        return sheet
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

def send_message_direct(chat_id, message_key, user_id):
    """Отправка сообщения пользователю."""
    msg_data = MESSAGES.get(message_key)
    if not msg_data:
        logger.error(f"❌ Сообщение {message_key} не найдено в MESSAGES")
        return False
    
    text = msg_data.get("text")
    buttons = msg_data.get("buttons")
    
    # Можно добавить логику получения имени из Sheets если нужно, 
    # но пока используем текст как есть
    
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
        logger.info(f"✅ Отправлено {message_key} пользователю {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
        return False

def check_pending_messages():
    """Проверяет таблицу и отправляет запланированные сообщения."""
    sheet = init_google_sheets()
    if not sheet:
        return
    
    try:
        worksheet = sheet.worksheet("Users")
        all_records = worksheet.get_all_records()
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        processed_count = 0
        
        for idx, record in enumerate(all_records):
            user_id = record.get("User ID")
            if not user_id:
                continue
            
            next_msg = record.get("Next Scheduled Message", "").strip()
            run_date_str = record.get("Run Date", "").strip()
            chat_id = record.get("Chat ID") or user_id
            
            if next_msg and run_date_str:
                try:
                    run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
                    run_date = moscow_tz.localize(run_date)
                    
                    if run_date <= now:
                        logger.info(f"🔔 Наступило время для {next_msg} (план: {run_date_str}) для {user_id}")
                        
                        # 1. Сначала очищаем текущую задачу в таблице, чтобы не было дублей
                        row_num = idx + 2  # +2 так как headers + 0-based index
                        worksheet.update(values=[["", ""]], range_name=f'J{row_num}:K{row_num}')
                        
                        # 2. Отправляем сообщение
                        if send_message_direct(chat_id, next_msg, user_id):
                            processed_count += 1
                            
                            # 3. Планируем следующее сообщение
                            plan = FOLLOW_UP_PLAN.get(next_msg)
                            if plan:
                                next_next_msg, delay_minutes = plan
                                next_run_date = now + timedelta(minutes=delay_minutes)
                                date_str = next_run_date.strftime("%Y-%m-%d %H:%M:%S")
                                
                                worksheet.update(values=[[next_next_msg, date_str]], range_name=f'J{row_num}:K{row_num}')
                                logger.info(f"📅 Запланировано следующее: {next_next_msg} на {date_str} для {user_id}")
                
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке записи {user_id}: {e}")
                    
        logger.info(f"📊 Обработка завершена. Отправлено {processed_count} сообщений.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении таблицы: {e}")

if __name__ == "__main__":
    check_pending_messages()
