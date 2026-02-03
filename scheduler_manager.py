import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import datetime, timedelta
import telebot
import pytz
from messages import MESSAGES, FOLLOW_UP_PLAN

logger = logging.getLogger(__name__)

class FollowUpScheduler:
    def __init__(self, bot, user_data, google_sheets=None, scheduler_storage=None):
        self.bot = bot
        self.user_data = user_data
        self.google_sheets = google_sheets
        
        jobstores = {
            'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            job_defaults={'coalesce': True, 'misfire_grace_time': 300},
            timezone=pytz.timezone('Europe/Moscow')
        )
        self.scheduler.start()
        logger.info(f"✅ Scheduler запущен, задач в очереди: {len(self.scheduler.get_jobs())}")
        self.user_stop_flags = {} # user_id -> True/False

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def schedule_next_message(self, user_id, chat_id, last_message_key):
        """Планирует следующее сообщение ТОЛЬКО в Google Sheets для обработки кроном."""
        if self.is_stopped(user_id):
            return

        plan = FOLLOW_UP_PLAN.get(last_message_key)
        if not plan:
            logger.info(f"Конец воронки для {user_id} после {last_message_key}")
            # Очищаем план в таблице
            self.update_sheet_schedule(user_id, "", None)
            return

        next_msg_key, delay_minutes = plan
        moscow_tz = pytz.timezone('Europe/Moscow')
        run_date = datetime.now(moscow_tz) + timedelta(minutes=delay_minutes)
        
        logger.info(f"✅ Запланировано {next_msg_key} для {user_id} через {delay_minutes} мин (только Google Sheets)")
        self.update_sheet_schedule(user_id, next_msg_key, run_date)

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
        """Задача отправки сообщения."""
        if self.is_stopped(user_id):
            logger.info(f"Воронка остановлена для {user_id}, пропускаю {message_key}")
            return

        logger.info(f"Отправка воронки {message_key} для {user_id}")
        msg_data = MESSAGES.get(message_key)
        if not msg_data:
            return

        text = msg_data.get("text")
        buttons = msg_data.get("buttons")
        
        u_data = self.user_data.get(user_id, {})
        name = u_data.get("name")
        
        if name:
             text = f"{name}, {text}"

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
            self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            # После отправки, планируем следующее
            if schedule_next:
                self.schedule_next_message(user_id, chat_id, message_key)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения воронки {user_id}: {e}")

    def stop_funnel(self, user_id):
        """Останавливает воронку для пользователя (например, записался на консультацию)."""
        self.user_stop_flags[user_id] = True
        self.cancel_all_user_jobs(user_id)
        logger.info(f"Воронка остановлена для {user_id}")

    def is_stopped(self, user_id):
        return self.user_stop_flags.get(user_id, False)

    def mark_user_action(self, user_id, action):
        """Отмечает, что пользователь совершил действие."""
        logger.info(f"Пользователь {user_id} совершил действие: {action}")
        pass

    def schedule_message_4_followup(self, user_id, chat_id):
        """Логика после скачивания Checklist (Message 4)."""
        if self.is_stopped(user_id):
            return

        # Планируем message_file_followup через 60 мин
        moscow_tz = pytz.timezone('Europe/Moscow')
        run_date_1 = datetime.now(moscow_tz) + timedelta(minutes=60)
        
        logger.info(f"Планирую message_file_followup для {user_id} через 60 мин (через Таблицу)")
        self.update_sheet_schedule(user_id, "message_file_followup", run_date_1)

    def schedule_message_5_followup(self, user_id, chat_id):
        """Логика после скачивания Case Study (Message 5)."""
        if self.is_stopped(user_id):
            return

        # Планируем message_5_1 через 24 часа
        moscow_tz = pytz.timezone('Europe/Moscow')
        run_date_1 = datetime.now(moscow_tz) + timedelta(hours=24)
        
        logger.info(f"Планирую message_5_1 для {user_id} через 24 часа (через Таблицу)")
        self.update_sheet_schedule(user_id, "message_5_1", run_date_1)

    def cancel_job(self, job_id):
        """Не используется в Variant B, но сохраняем для совместимости."""
        pass

    def update_sheet_schedule(self, user_id, next_msg, run_date):
        """Обновляет информацию о запланированных сообщениях в Google Sheets. Использует локальный поиск и пакетное обновление."""
        if not self.google_sheets:
            return

        max_retries = 3
        for attempt in range(max_retries):
            try:
                worksheet = self.google_sheets.worksheet("Users")
                all_values = worksheet.get_all_values()
                
                user_row = None
                for idx, row in enumerate(all_values):
                    if row and row[0] == str(user_id):
                        user_row = idx + 1
                        break
                
                if user_row:
                    msg_val = next_msg if next_msg else ""
                    date_val = run_date.strftime("%Y-%m-%d %H:%M:%S") if run_date else ""
                    
                    # Обновляем столбцы J (10) и K (11) пакетно
                    worksheet.update(values=[[msg_val, date_val]], range_name=f'J{user_row}:K{user_row}')
                    logger.info(f"✅ Google Sheets updated for {user_id}: {msg_val} at {date_val}")
                    return
                else:
                    logger.warning(f"⚠️ User {user_id} not found in Google Sheets to update schedule")
                    return
            except Exception as e:
                logger.error(f"❌ Attempt {attempt+1} to update sheets failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    logger.error(f"❌ Failed to update Google Sheets for {user_id} after {max_retries} attempts")
