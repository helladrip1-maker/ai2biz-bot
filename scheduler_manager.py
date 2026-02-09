
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
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
        self.scheduler = BackgroundScheduler()
        # Если нужно, можно добавить RedisJobStore или SQLAlchemyJobStore
        # self.scheduler.add_jobstore('sqlalchemy', url='sqlite:///jobs.sqlite')
        self.scheduler.start()
        self.user_stop_flags = {} # user_id -> True/False
        self.tz = pytz.timezone("Europe/Moscow")
        self.use_sheet_queue = bool(self.google_sheets)
        self.recovery_callback = None # Коллбэк для восстановления воронки
        self.custom_follow_up = {
            "message_file_followup": ("message_5", 23 * 60 + 50),
            "message_3_1": ("message_4", 23 * 60 + 50),
        }
        
        # Конфигурация столбцов для двух планировщиков
        self.main_scheduler_cols = {"next_msg": 10, "run_date": 11}  # J, K
        self.consult_scheduler_cols = {"next_msg": 16, "run_date": 17}  # P, Q
        self.last_activity_col = 18  # R
        self.consult_state_col = 19  # S
        self.form_completed_col = 20  # T
        
        # Порог неактивности для сброса (4 дня в секундах)
        self.inactivity_threshold = 4 * 24 * 60 * 60  # 4 days

        if self.use_sheet_queue:
            # Периодический диспетчер: проверяет таблицу и отправляет просроченные сообщения
            self.scheduler.add_job(
                self.dispatch_due_messages_from_sheet,
                trigger="interval",
                seconds=60,
                id="sheet_dispatch",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def schedule_next_message(self, user_id, chat_id, last_message_key):
        """Планирует следующее сообщение на основе текущего."""
        if self.is_stopped(user_id):
            return

        plan = self.get_next_plan(last_message_key)
        if not plan:
            logger.info(f"Конец воронки для {user_id} после {last_message_key}")
            return

        next_msg_key, delay_minutes = plan
        run_date = datetime.now(self.tz) + timedelta(minutes=delay_minutes)
        
        job_id = f"funnel_{user_id}_{next_msg_key}"
        
        # Удаляем старую задачу если есть (на всякий случай)
        self.cancel_job(job_id)

        logger.info(f"Планирую {next_msg_key} для {user_id} через {delay_minutes} мин (job_id={job_id})")

        if self.use_sheet_queue:
            self.update_sheet_schedule(user_id, next_msg_key, run_date, chat_id=chat_id)
            return

        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date),
            args=[user_id, chat_id, next_msg_key],
            id=job_id,
            replace_existing=True
        )
        self.update_sheet_schedule(user_id, next_msg_key, run_date, chat_id=chat_id)

    def cancel_all_user_jobs(self, user_id):
        """Отменяет все запланированные задачи для конкретного пользователя."""
        for job in list(self.scheduler.get_jobs()):
            if str(user_id) in job.id:
                try:
                    self.scheduler.remove_job(job.id)
                    logger.info(f"Удалена задача {job.id}")
                except Exception:
                    pass
        if self.use_sheet_queue:
            self.clear_sheet_schedule(user_id)

    def send_message_direct(self, user_id, chat_id, message_key, schedule_next=True):
        """Отправляет сообщение немедленно и планирует следующие шаги."""
        if self.is_stopped(user_id):
            return
        
        # Отменяем текущую очередь только если мы планируем НОВУЮ цепочку (schedule_next=True)
        # Если мы просто шлем доп. сообщение (например меню файлов), старая очередь должна жить
        if schedule_next:
            self.cancel_all_user_jobs(user_id)
        
        self.send_message_job(user_id, chat_id, message_key, schedule_next=schedule_next)

    def send_message_job(self, user_id, chat_id, message_key, schedule_next=True):
        """Задача отправки сообщения."""
        try:
            logger.info(f"Отправка воронки {message_key} для {user_id}")
            msg_data = MESSAGES.get(message_key)
            if not msg_data:
                return False

            text = msg_data.get("text")
            buttons = msg_data.get("buttons")
            
            # Подставляем имя если оно есть в user_data
            u_data = self.user_data.get(user_id, {})
            name = u_data.get("name")
            
            if name and "message_" in message_key and message_key != "message_0":
                 if not text.startswith(name):
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

            # Если есть изображения
            image = msg_data.get("image")
            images = msg_data.get("images")

            # Проверяем длину текста для caption (лимит Telegram 1024)
            caption = text
            if len(text) > 1024:
                caption = None

            if images:
                media = []
                for i, img_url in enumerate(images):
                    if i == 0:
                        media.append(telebot.types.InputMediaPhoto(img_url, caption=caption, parse_mode="HTML"))
                    else:
                        media.append(telebot.types.InputMediaPhoto(img_url))
                self.bot.send_media_group(chat_id, media)
                
                if len(text) > 1024:
                    self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
                elif markup:
                    footer = msg_data.get("footer", "Выберите действие:")
                    self.bot.send_message(chat_id, footer, reply_markup=markup, parse_mode="HTML")
            
            elif image:
                if len(text) > 1024:
                    self.bot.send_photo(chat_id, image)
                    self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
                else:
                    self.bot.send_photo(chat_id, image, caption=text, reply_markup=markup, parse_mode="HTML")
            
            else:
                self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

            self.update_send_log(user_id, message_key, "OK")
            # После отправки, планируем следующее
            if schedule_next:
                self.schedule_next_message(user_id, chat_id, message_key)

            # Если это было напоминание по консультации ДЛЯ ДИПЛИНК-ЛИДА,
            # планируем восстановление основной воронки через 10 минут (Message 0)
            if message_key.startswith("consult_followup_"):
                 u_data = self.user_data.get(user_id, {})
                 
                 is_deeplink = u_data.get("entry_source") == "deeplink_consult"
                 
                 # Фолбек: проверяем Google Sheets, если в памяти нет флага (после рестарта)
                 if not is_deeplink and self.use_sheet_queue:
                     try:
                         worksheet = self.google_sheets.worksheet("Users")
                         cell = worksheet.find(str(user_id), in_column=1)
                         if cell:
                             # Колонка 7 (G) - Lead Source
                             lead_source_val = worksheet.cell(cell.row, 7).value
                             if lead_source_val == "deeplink":
                                 is_deeplink = True
                                 # Восстанавливаем в память
                                 if user_id not in self.user_data:
                                     self.user_data[user_id] = {}
                                 self.user_data[user_id]["entry_source"] = "deeplink_consult"
                                 logger.info(f"Restored deeplink status for {user_id} from Sheets")
                     except Exception as e:
                         logger.error(f"Error checking deep link status in sheet for {user_id}: {e}")

                 if is_deeplink:
                     self.schedule_funnel_recovery(user_id, chat_id)

            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения воронки {user_id}: {e}")
            self.update_send_log(user_id, message_key, "ERROR")
            return False

    def stop_funnel(self, user_id):
        """Останавливает воронку для пользователя (например, записался на консультацию)."""
        self.user_stop_flags[user_id] = True
        # Можно также отменить все запланированные задачи для юзера
        # Но APScheduler не поддерживает фильтр по юзеру легко без перебора
        # Поэтому мы просто ставим флаг
        self.cancel_all_user_jobs(user_id)
        logger.info(f"Воронка остановлена для {user_id}")

    def is_stopped(self, user_id):
        return self.user_stop_flags.get(user_id, False)

    def resume_funnel(self, user_id):
        """Снимает флаг остановки воронки для пользователя."""
        if user_id in self.user_stop_flags:
            self.user_stop_flags[user_id] = False
            logger.info(f"Воронка возобновлена для {user_id}")

    def mark_user_action(self, user_id, action):
        """Отмечает действие пользователя. Отменяет воронку только при полном заполнении анкет/заявок."""
        logger.info(f"Пользователь {user_id} совершил действие: {action}")
        
        # Обновляем Last Activity в Google Sheets
        self.update_last_activity(user_id)
        
        # Список действий, КУДА МЫ УХОДИМ ИЗ ВОРОНКИ НАВСЕГДА (или до ручного перезапуска)
        # Теперь это только завершенные формы
        stop_actions = [
            "completed_consultation_form",
            "completed_form"
        ]
        
        if action in stop_actions:
            logger.info(f"Пользователь {user_id} завершил квалификацию ({action}), останавливаем дожимы")
            self.stop_funnel(user_id)
            # Записываем время завершения формы
            if action == "completed_consultation_form":
                self.mark_form_completed(user_id)
        else:
            # Для всех остальных действий (скачивание файлов, кнопки меню, начало анкеты)
            # мы НЕ отменяем воронку, чтобы дожимы продолжали приходить если пользователь не закончил.
            logger.info(f"Пользователь {user_id} активен ({action}), воронка продолжается")

    def check_user_inactivity(self, user_id):
        """Проверяет, неактивен ли пользователь более 4 дней."""
        if not self.google_sheets:
            return False
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if not cell:
                return False
            
            row = cell.row
            last_activity_str = worksheet.cell(row, self.last_activity_col).value
            
            if not last_activity_str:
                return False
            
            last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")
            last_activity = self.tz.localize(last_activity)
            now = datetime.now(self.tz)
            
            inactive_seconds = (now - last_activity).total_seconds()
            return inactive_seconds >= self.inactivity_threshold
            
        except Exception as e:
            logger.error(f"Ошибка проверки неактивности для {user_id}: {e}")
            return False

    def reset_inactive_user(self, user_id):
        """Сбрасывает состояние неактивного пользователя (форма + воронка)."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if not cell:
                return
            
            row = cell.row
            # Очищаем оба планировщика
            worksheet.update(values=[["", ""]], range_name=f'J{row}:K{row}')  # Main funnel
            worksheet.update(values=[["", ""]], range_name=f'P{row}:Q{row}')  # Consultation
            # Очищаем состояние формы и время завершения
            worksheet.update_cell(row, self.consult_state_col, "")
            worksheet.update_cell(row, self.form_completed_col, "")
            
            # Снимаем флаг остановки воронки
            if user_id in self.user_stop_flags:
                self.user_stop_flags[user_id] = False
            
            logger.info(f"✅ Сброшено состояние неактивного пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сброса пользователя {user_id}: {e}")

    def update_last_activity(self, user_id):
        """Обновляет timestamp последней активности пользователя."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                timestamp = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")
                worksheet.update_cell(row, self.last_activity_col, timestamp)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления Last Activity для {user_id}: {e}")

    def mark_form_completed(self, user_id):
        """Отмечает время завершения формы консультации."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                timestamp = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")
                worksheet.update_cell(row, self.form_completed_col, timestamp)
        except Exception as e:
            logger.error(f"❌ Ошибка записи времени завершения формы для {user_id}: {e}")

    def schedule_consultation_message(self, user_id, chat_id, message_key, delay_minutes=5):
        """Планирует сообщение дожима консультации (отдельно от основной воронки)."""
        if self.is_stopped(user_id):
            return
        
        run_date = datetime.now(self.tz) + timedelta(minutes=delay_minutes)
        job_id = f"consult_{user_id}_{message_key}"
        
        # Удаляем старую задачу если есть
        self.cancel_job(job_id)
        
        logger.info(f"Планирую консультацию {message_key} для {user_id} через {delay_minutes} мин")
        
        if self.use_sheet_queue:
            self.update_consultation_schedule(user_id, message_key, run_date, chat_id=chat_id)
            return
        
        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date),
            args=[user_id, chat_id, message_key, False],  # schedule_next=False для дожимов
            id=job_id,
            replace_existing=True
        )
        self.update_consultation_schedule(user_id, message_key, run_date, chat_id=chat_id)

    def update_consultation_schedule(self, user_id, next_msg, run_date, chat_id=None):
        """Обновляет расписание консультации в столбцах P, Q."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                worksheet.update_cell(row, self.consult_scheduler_cols["next_msg"], next_msg)
                worksheet.update_cell(row, self.consult_scheduler_cols["run_date"], run_date.strftime("%Y-%m-%d %H:%M:%S"))
                if chat_id is not None:
                    worksheet.update_cell(row, 12, str(chat_id))
                logger.info(f"✅ Consultation schedule updated for {user_id}: {next_msg} at {run_date}")
        except Exception as e:
            logger.error(f"❌ Failed to update consultation schedule for {user_id}: {e}")

    def clear_consultation_schedule(self, user_id):
        """Очищает расписание консультации (столбцы P, Q)."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                worksheet.update(values=[["", ""]], range_name=f'P{row}:Q{row}')
                logger.info(f"✅ Cleared consultation schedule for {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to clear consultation schedule for {user_id}: {e}")

    def schedule_message_4_followup(self, user_id, chat_id):
        """Логика после скачивания Checklist (Message 4)."""
        if self.is_stopped(user_id):
            return

        # Отменяем стандартный переход к message_5 который был запланирован при отправке message_4
        self.cancel_job(f"funnel_{user_id}_message_5")

        # 1. Через 10 минут "Что дальше?" (message_file_followup)
        run_date_1 = datetime.now(self.tz) + timedelta(minutes=10)
        job_id_1 = f"file_followup_1_{user_id}"
        
        logger.info(f"Планирую message_file_followup для {user_id} через 10 мин")
        if self.use_sheet_queue:
            self.update_sheet_schedule(user_id, "message_file_followup", run_date_1, chat_id=chat_id)
            return

        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date_1),
            args=[user_id, chat_id, "message_file_followup", True], # Используем автоматику
            id=job_id_1,
            replace_existing=True
        )
        self.update_sheet_schedule(user_id, "message_file_followup", run_date_1, chat_id=chat_id)

    def schedule_message_3_followup(self, user_id, chat_id):
        """Логика после скачивания Case Study (Message 3)."""
        if self.is_stopped(user_id):
            return

        # Отменяем стандартный переход запланированный при отправке message_3 (к message_4 через час)
        self.cancel_job(f"funnel_{user_id}_message_4")

        # 1. Через 10 минут "Что дальше?" (message_3_1)
        run_date_1 = datetime.now(self.tz) + timedelta(minutes=10)
        job_id_1 = f"case_followup_1_{user_id}"
        
        logger.info(f"Планирую message_3_1 для {user_id} через 10 минут")
        if self.use_sheet_queue:
            self.update_sheet_schedule(user_id, "message_3_1", run_date_1, chat_id=chat_id)
            return

        self.scheduler.add_job(
            self.send_message_job,
            trigger=DateTrigger(run_date=run_date_1),
            args=[user_id, chat_id, "message_3_1", True], # Пусть планирует следующее через get_next_plan
            id=job_id_1,
            replace_existing=True
        )
        self.update_sheet_schedule(user_id, "message_3_1", run_date_1, chat_id=chat_id)

        # Мы не планируем здесь message_4 вручную для локального шедулера,
        # так как send_message_job("message_3_1", schedule_next=True) теперь будет
        # использовать get_next_plan и запланирует его автоматически.

    def schedule_consultation_followup(self, user_id, chat_id, step_key):
        """Планирует напоминание для анкеты консультации через 5 минут."""
        # Используем новый отдельный планировщик консультаций
        self.schedule_consultation_message(user_id, chat_id, step_key, delay_minutes=5)

    def cancel_consultation_followups(self, user_id):
        """Отменяет все текущие задачи-напоминания для анкеты консультации."""
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(f"consult_followup_{user_id}") or job.id.startswith(f"consult_{user_id}"):
                try:
                    self.scheduler.remove_job(job.id)
                    logger.info(f"Удалено напоминание {job.id}")
                except Exception:
                    pass
        # При любой отмене напоминаний - отменяем и восстановление воронки (если юзер ответил)
        self.cancel_funnel_recovery(user_id)
        
        # Очищаем таблицу консультации для этого пользователя
        if self.use_sheet_queue:
            self.clear_consultation_schedule(user_id)

    def schedule_funnel_recovery(self, user_id, chat_id):
        """Планирует отправку Message 0 через 10 минут для лидов из диплинка."""
        run_date = datetime.now(self.tz) + timedelta(minutes=10)
        job_id = f"funnel_recovery_{user_id}"
        
        self.cancel_funnel_recovery(user_id)
        
        logger.info(f"Планирую восстановление воронки для {user_id} через 10 мин")
        
        if self.recovery_callback:
            # Если есть коллбэк (из main.py), планируем вызов коллбэка
            self.scheduler.add_job(
                self.recovery_callback,
                trigger=DateTrigger(run_date=run_date),
                args=[user_id, chat_id],
                id=job_id,
                replace_existing=True
            )
        else:
            # Иначе просто отправляем сообщение (старый способ)
            self.scheduler.add_job(
                self.send_message_job,
                trigger=DateTrigger(run_date=run_date),
                args=[user_id, chat_id, "message_0", True], 
                id=job_id,
                replace_existing=True
            )

    def cancel_funnel_recovery(self, user_id):
        """Отменяет задачу восстановления воронки."""
        job_id = f"funnel_recovery_{user_id}"
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Удалено восстановление воронки для {user_id}")
        except Exception:
            pass

    def cancel_job(self, job_id):
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

    def update_sheet_schedule(self, user_id, next_msg, run_date, chat_id=None):
        """Обновляет информацию о запланированных сообщениях в Google Sheets."""
        if not self.google_sheets:
            return

        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                # Предполагаем, что столбцы J (10) и K (11) свободны или предназначены для этого
                # 10: Next Scheduled Message
                # 11: Run Date
                worksheet.update_cell(row, 10, next_msg)
                worksheet.update_cell(row, 11, run_date.strftime("%Y-%m-%d %H:%M:%S"))
                if chat_id is not None:
                    worksheet.update_cell(row, 12, str(chat_id))
                logger.info(f"✅ Google Sheets updated for {user_id}: {next_msg} at {run_date}")
        except Exception as e:
            logger.error(f"❌ Failed to update Google Sheets schedule for {user_id}: {e}")

    def clear_sheet_schedule(self, user_id):
        if not self.google_sheets:
            return
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                worksheet.update(values=[["", ""]], range_name=f'J{row}:K{row}')
        except Exception as e:
            logger.error(f"❌ Failed to clear sheet schedule for {user_id}: {e}")

    def update_send_log(self, user_id, message_key, status):
        if not self.google_sheets:
            return
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                worksheet.update_cell(row, 13, message_key)
                worksheet.update_cell(row, 14, datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S"))
                worksheet.update_cell(row, 15, status)
        except Exception as e:
            logger.error(f"❌ Failed to update send log for {user_id}: {e}")

    def get_next_plan(self, message_key):
        if message_key in FOLLOW_UP_PLAN:
            return FOLLOW_UP_PLAN[message_key]
        return self.custom_follow_up.get(message_key)

    def dispatch_due_messages_from_sheet(self):
        """Проверяет таблицу и отправляет просроченные сообщения (надежный диспетчер)."""
        if not self.google_sheets:
            return

        try:
            worksheet = self.google_sheets.worksheet("Users")
            all_records = worksheet.get_all_records()
            now = datetime.now(self.tz)

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

                # Получаем данные из обоих планировщиков
                main_msg = str(record_get(record, "Next Scheduled Message", "Next Msg")).strip()
                main_date_str = str(record_get(record, "Run Date", "Time")).strip()
                
                consult_msg = str(record_get(record, "Consult Next Message")).strip()
                consult_date_str = str(record_get(record, "Consult Run Date")).strip()
                
                chat_id_val = record_get(record, "Chat ID") or user_id_val

                try:
                    user_id = int(user_id_val)
                except Exception:
                    user_id = user_id_val

                try:
                    chat_id = int(chat_id_val)
                except Exception:
                    chat_id = chat_id_val

                if self.is_stopped(user_id):
                    continue

                # Парсим даты
                main_date = None
                consult_date = None
                
                if main_msg and main_date_str:
                    try:
                        main_date = datetime.strptime(main_date_str, "%Y-%m-%d %H:%M:%S")
                        main_date = self.tz.localize(main_date)
                    except Exception:
                        logger.error(f"Некорректная дата main в строке {idx + 2}: {main_date_str}")
                
                if consult_msg and consult_date_str:
                    try:
                        consult_date = datetime.strptime(consult_date_str, "%Y-%m-%d %H:%M:%S")
                        consult_date = self.tz.localize(consult_date)
                    except Exception:
                        logger.error(f"Некорректная дата consult в строке {idx + 2}: {consult_date_str}")

                row_num = idx + 2
                
                # Проверяем, какие сообщения просрочены
                main_due = main_date and main_date <= now
                consult_due = consult_date and consult_date <= now

                # КОНФЛИКТ: оба сообщения просрочены
                if main_due and consult_due:
                    logger.info(f"⚠️ Конфликт для {user_id}: оба планировщика имеют просроченные сообщения")
                    
                    # Приоритет: консультация
                    # 1. Отправляем консультацию
                    worksheet.update(values=[["", ""]], range_name=f'P{row_num}:Q{row_num}')
                    sent = self.send_message_job(user_id, chat_id, consult_msg, schedule_next=False)
                    
                    if sent:
                        # 2. Откладываем main на 10 минут
                        new_main_date = now + timedelta(minutes=10)
                        worksheet.update_cell(row_num, self.main_scheduler_cols["run_date"], 
                                            new_main_date.strftime("%Y-%m-%d %H:%M:%S"))
                        logger.info(f"✅ Main message {main_msg} отложено на 10 минут для {user_id}")
                        
                        # 3. Если main сообщение - это message_X (основная воронка), закрываем форму
                        if main_msg.startswith("message_"):
                            self.close_consultation_form(user_id)
                    
                    continue

                # Только консультация просрочена
                if consult_due:
                    worksheet.update(values=[["", ""]], range_name=f'P{row_num}:Q{row_num}')
                    sent = self.send_message_job(user_id, chat_id, consult_msg, schedule_next=False)
                    
                    if sent and consult_msg.startswith("consult_followup_"):
                        # После последнего дожима консультации без ответа, планируем message_0 через 10 минут
                        # Но только если пользователь пришел через диплинк
                        u_data = self.user_data.get(user_id, {})
                        is_deeplink = u_data.get("entry_source") == "deeplink_consult"
                        
                        if is_deeplink and not main_msg:
                            # Планируем восстановление воронки
                            self.schedule_funnel_recovery(user_id, chat_id)
                    
                    continue

                # Только main просрочен
                if main_due:
                    worksheet.update(values=[["", ""]], range_name=f'J{row_num}:K{row_num}')
                    sent = self.send_message_job(user_id, chat_id, main_msg, schedule_next=False)
                    
                    if sent:
                        # Планируем следующее сообщение основной воронки
                        plan = self.get_next_plan(main_msg)
                        if plan:
                            next_key, delay_minutes = plan
                            next_run = now + timedelta(minutes=delay_minutes)
                            self.update_sheet_schedule(user_id, next_key, next_run, chat_id=chat_id)
                        
                        # Если отправили сообщение основной воронки, закрываем форму консультации
                        if main_msg.startswith("message_"):
                            self.close_consultation_form(user_id)
                    
                    continue

        except Exception as e:
            logger.error(f"Ошибка диспетчера таблицы: {e}")

    def close_consultation_form(self, user_id):
        """Закрывает форму консультации и сбрасывает ответы."""
        if not self.google_sheets:
            return
        
        try:
            worksheet = self.google_sheets.worksheet("Users")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row = cell.row
                
                # Проверяем, была ли форма вообще активна
                consult_state = worksheet.cell(row, self.consult_state_col).value
                form_was_active = consult_state and consult_state.strip() != ""
                
                # Очищаем состояние формы
                worksheet.update_cell(row, self.consult_state_col, "")
                logger.info(f"✅ Форма консультации закрыта для {user_id} (была активна: {form_was_active})")
                # Reply-клавиатура автоматически исчезнет при следующем сообщении без клавиатуры
                
                # Очищаем данные формы в памяти
                if user_id in self.user_data:
                    # Сохраняем entry_source если есть
                    entry_source = self.user_data[user_id].get("entry_source")
                    self.user_data[user_id] = {}
                    if entry_source:
                        self.user_data[user_id]["entry_source"] = entry_source
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия формы для {user_id}: {e}")
