# scheduler_manager.py (НОВЫЙ - упрощенный)
import logging
from datetime import datetime, timedelta
import pytz
import time

logger = logging.getLogger(__name__)

class FollowUpScheduler:
    def __init__(self, bot, user_data, google_sheets=None):
        self.bot = bot
        self.user_data = user_data
        self.google_sheets = google_sheets
        self.user_stop_flags = {}

    def schedule_next_message(self, user_id, chat_id, last_message_key):
        """ПЛАНИРУЕТ ТОЛЬКО в Google Sheets (без APScheduler)"""
        if self.is_stopped(user_id):
            return
        
        from messages import FOLLOW_UP_PLAN
        plan = FOLLOW_UP_PLAN.get(last_message_key)
        if not plan:
            logger.info(f"Конец воронки для {user_id} после {last_message_key}")
            # Очищаем план в таблице
            self.update_sheet_schedule(user_id, "", None)
            return
        
        next_msg_key, delay_minutes = plan
        moscow_tz = pytz.timezone('Europe/Moscow')
        run_date = datetime.now(moscow_tz) + timedelta(minutes=delay_minutes)
        
        # ✅ ТОЛЬКО записываем в Google Sheets
        self.update_sheet_schedule(user_id, next_msg_key, run_date)
        logger.info(f"✅ Запланировано {next_msg_key} для {user_id} на {run_date} (Google Sheets)")
    
    def cancel_all_user_jobs(self, user_id):
        """Очищает запланированные задачи пользователя в Google Sheets."""
        logger.info(f"Отменяем задачи в Google Sheets для {user_id}")
        self.update_sheet_schedule(user_id, "", None)

    def send_message_direct(self, user_id, chat_id, message_key, schedule_next=True):
        """Отправляет сообщение немедленно и планирует следующие шаги."""
        if self.is_stopped(user_id):
            return
        
        # Отменяем текущую очередь в таблице
        self.cancel_all_user_jobs(user_id)
        
        self.send_message_job(user_id, chat_id, message_key, schedule_next=schedule_next)

    def send_message_job(self, user_id, chat_id, message_key, schedule_next=True):
        """Отправляет сообщение и планирует следующее"""
        if self.is_stopped(user_id):
            logger.info(f"Воронка остановлена для {user_id}")
            return
        
        from messages import MESSAGES
        msg_data = MESSAGES.get(message_key)
        if not msg_data:
            return
        
        text = msg_data.get("text")
        buttons = msg_data.get("buttons")
        
        # Имя пользователя
        u_data = self.user_data.get(user_id, {})
        name = u_data.get("name")
        if name:
            text = f"{name}, {text}"
        
        # Клавиатура
        markup = None
        if buttons:
            markup = self.build_markup(buttons)
        
        try:
            self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            logger.info(f"✅ Отправлено {message_key} для {user_id}")
            
            # Планируем следующее
            if schedule_next:
                self.schedule_next_message(user_id, chat_id, message_key)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {message_key} для {user_id}: {e}")
    
    def build_markup(self, buttons):
        """Создает InlineKeyboardMarkup"""
        from telebot import types
        markup = types.InlineKeyboardMarkup()
        for row in buttons:
            btns = []
            for btn in row:
                if "url" in btn:
                    btns.append(types.InlineKeyboardButton(text=btn["text"], url=btn["url"]))
                else:
                    btns.append(types.InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
            markup.add(*btns)
        return markup
    
    def update_sheet_schedule(self, user_id, next_msg, run_date):
        """🔥 НАДЕЖНОЕ обновление Google Sheets"""
        if not self.google_sheets:
            return
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                worksheet = self.google_sheets.worksheet("Users")
                all_values = worksheet.get_all_values()
                
                # 🔥 Ищем строку локально (НАДЕЖНЕЕ worksheet.find())
                user_row = None
                for idx, row in enumerate(all_values):
                    if row and len(row) > 0 and row[0] == str(user_id):
                        user_row = idx + 1
                        break
                
                if user_row:
                    msg_val = next_msg if next_msg else ""
                    date_val = run_date.strftime("%Y-%m-%d %H:%M:%S") if run_date else ""
                    # Batch update (быстрее)
                    worksheet.update(values=[[msg_val, date_val]], range_name=f'J{user_row}:K{user_row}')
                    logger.info(f"✅ Sheets updated: {user_id} → {msg_val}")
                    return
                else:
                    logger.warning(f"⚠️ User {user_id} not found in Sheets")
                    return
                    
            except Exception as e:
                logger.error(f"❌ Sheets update attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
    
    def is_stopped(self, user_id):
        return self.user_stop_flags.get(user_id, False)
    
    def stop_funnel(self, user_id):
        self.user_stop_flags[user_id] = True
        self.cancel_all_user_jobs(user_id)
        logger.info(f"🛑 Воронка остановлена для {user_id}")

    def mark_user_action(self, user_id, action):
        """Отмечает, что пользователь совершил действие."""
        logger.info(f"Пользователь {user_id} совершил действие: {action}")
        pass
