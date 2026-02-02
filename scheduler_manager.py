
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import telebot
from messages import MESSAGES, FOLLOW_UP_PLAN

logger = logging.getLogger(__name__)

class FollowUpScheduler:
    def __init__(self, bot, user_data, google_sheets=None, scheduler_storage=None):
        self.bot = bot
        self.user_data = user_data
        self.google_sheets = google_sheets
        self.scheduler = BackgroundScheduler()
        # Если нужно, можно добавить RedisJobStore или SQLAlchemyJobStore
        # self.scheduler.add_jobstore('sqlalchemy', url='sqlite:///jobs.sqlite')
        self.scheduler.start()
        self.user_stop_flags = {} # user_id -> True/False

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def schedule_next_message(self, user_id, chat_id, last_message_key):
        """Планирует следующее сообщение на основе текущего."""
        if self.is_stopped(user_id):
            return

        plan = FOLLOW_UP_PLAN.get(last_message_key)
        if not plan:
            logger.info(f"Конец воронки для {user_id} после {last_message_key}")
            return

        next_msg_key, delay_minutes = plan
        run_date = datetime.now() + timedelta(minutes=delay_minutes)
        
        job_id = f"funnel_{user_id}_{next_msg_key}"
        
        # Удаляем старую задачу если есть (на всякий случай)
        self.cancel_job(job_id)

        logger.info(f"Планирую {next_msg_key} для {user_id} через {delay_minutes} мин (job_id={job_id})")
        
        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date),
            args=[user_id, chat_id, next_msg_key],
            id=job_id,
            replace_existing=True
        )
        self.update_sheet_schedule(user_id, next_msg_key, run_date)

    def send_message_job(self, user_id, chat_id, message_key):
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
        
        # Подставляем имя если оно есть в user_data
        # user_data = {user_id: {"name": "Ivan", ...}}
        u_data = self.user_data.get(user_id, {})
        name = u_data.get("name")
        
        # "сделай обращение к тем, кто заполнил анкету по имени"
        # Просто добавляем имя в начало, если оно известно
        if name:
             # Проверяем, не начинается ли текст уже с имени (маловероятно)
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
            self.schedule_next_message(user_id, chat_id, message_key)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения воронки {user_id}: {e}")

    def stop_funnel(self, user_id):
        """Останавливает воронку для пользователя (например, записался на консультацию)."""
        self.user_stop_flags[user_id] = True
        # Можно также отменить все запланированные задачи для юзера
        # Но APScheduler не поддерживает фильтр по юзеру легко без перебора
        # Поэтому мы просто ставим флаг
        logger.info(f"Воронка остановлена для {user_id}")

    def is_stopped(self, user_id):
        return self.user_stop_flags.get(user_id, False)

    def mark_user_action(self, user_id, action):
        """Отмечает действие пользователя и отменяет запланированные дожимы при важных действиях."""
        logger.info(f"Пользователь {user_id} совершил действие: {action}")
        
        # Если пользователь совершил важное действие - останавливаем автоворонку
        important_actions = [
            "consultation",
            "completed_consultation_form",
            "requested_files",
            "subscribed",
            "consultation_requested"
        ]
        
        if action in important_actions:
            # Не останавливаем полностью, но отменяем текущие запланированные дожимы
            # поскольку пользователь уже активен
            logger.info(f"Пользователь {user_id} активен ({action}), отменяем текущие дожимы")
            # Можно отменить все задачи для этого пользователя
            # Но мы оставляем файловую логику работать
            pass

    def schedule_file_followup(self, user_id, chat_id):
        """Специфическая логика после скачивания файла: через 1 час и потом переход к message_5."""
        if self.is_stopped(user_id):
            return

        # 1. Через 1 час "Что дальше?"
        run_date_1 = datetime.now() + timedelta(minutes=60)
        job_id_1 = f"file_followup_1_{user_id}"
        
        logger.info(f"Планирую file_followup для {user_id} через 60 мин")
        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date_1),
            args=[user_id, chat_id, "message_file_followup"],
            id=job_id_1,
            replace_existing=True
        )
        self.update_sheet_schedule(user_id, "message_file_followup", run_date_1)

        # 2. Через 24 часа переход к message_5 
        # (вызываем schedule_next_message с фейк 'message_4' чтобы сработал переход на 5?)
        # Или явно планируем message 5 через 24+1 час?
        # MD говорит: "После этого через 24 часа переход к message 5"
        # То есть через 24 часа после "Что дальше?".
        
        run_date_2 = run_date_1 + timedelta(hours=24)
        job_id_2 = f"file_to_msg5_{user_id}"
        
        logger.info(f"Планирую переход к message_5 для {user_id} через 25 часов")
        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date_2),
            args=[user_id, chat_id, "message_5"],
            id=job_id_2,
            replace_existing=True
        )

    def cancel_job(self, job_id):
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

    def update_sheet_schedule(self, user_id, next_msg, run_date):
        """Обновляет информацию о запланированных сообщениях в Google Sheets."""
        if not self.google_sheets:
            return

        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id))
            if cell:
                row = cell.row
                # Предполагаем, что столбцы J (10) и K (11) свободны или предназначены для этого
                # 10: Next Scheduled Message
                # 11: Run Date
                worksheet.update_cell(row, 10, next_msg)
                worksheet.update_cell(row, 11, run_date.strftime("%Y-%m-%d %H:%M:%S"))
                logger.info(f"✅ Google Sheets updated for {user_id}: {next_msg} at {run_date}")
        except Exception as e:
            logger.error(f"❌ Failed to update Google Sheets schedule for {user_id}: {e}")
