#!/usr/bin/env python3
"""
AI2BIZ Telegram Bot - ADVANCED VERSION V2 (ИСПРАВЛЕННАЯ)
- Две отдельных анкеты (файлы + консультация)
- ДВА ТИПА ФАЙЛОВ: 5 ошибок менеджеров или Чек-лист (выбор пользователя)
- Обязательная подписка на канал it_ai2biz перед анкетой
- Кнопки-варианты ответов для выручки и времени функционирования
- Уведомления администратору только на консультацию
"""

import os
import telebot
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TOKEN")
ZOOM_LINK = os.getenv("ZOOM_LINK", "https://zoom.us/YOUR_ZOOM_LINK")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_ID = "@it_ai2biz"  # ← КАНАЛ ДЛЯ ПОДПИСКИ

FILE_5_MISTAKES = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/5%20mistakes%20of%20managers.pdf"
FILE_CHECKLIST = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check%20list%2010%20ways.pdf"

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_data = {}
user_state = {}  # "files" или "consultation"

# ===== SUPABASE =====
def save_to_supabase(table, data):
    """Сохраняет в Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"⚠️ Supabase не настроена")
        return False
    try:
        import requests
        headers = {
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        response = requests.post(url, json=data, headers=headers)
        if response.status_code in [200, 201]:
            print(f"✅ Сохранено в {table}")
            return True
        else:
            print(f"❌ Ошибка Supabase ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def log_action(user_id, name, action, details=""):
    """Логирует в таблицу stats"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {action} | {name} ({user_id})")
    save_to_supabase("stats", {
        "user_id": user_id,
        "name": name,
        "action": action,
        "details": details
    })

def save_lead_files(user_id, lead_data):
    """Сохраняет лид файлов в таблицу leads_files"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '300k' in revenue or '1m' in revenue:
        segment = "medium"
    elif 'large' in revenue or '5m' in revenue:
        segment = "large"
    else:
        segment = "enterprise"
    
    data = {
        "user_id": user_id,
        "name": lead_data.get('name', ''),
        "business_duration": lead_data.get('business_duration', ''),
        "telegram": lead_data.get('telegram', ''),
        "business": lead_data.get('business', ''),
        "revenue": lead_data.get('revenue', ''),
        "file_type": lead_data.get('file_type', ''),  # ← НОВОЕ: какой файл выбрал
        "segment": segment
    }
    save_to_supabase("leads_files", data)

def save_lead_consultation(user_id, lead_data):
    """Сохраняет лид консультации в таблицу leads_consultation"""
    revenue = lead_data.get('revenue', '').lower()
    if 'small' in revenue or '300k' in revenue or '<' in revenue:
        segment = "small"
    elif 'medium' in revenue or '300k' in revenue or '1m' in revenue:
        segment = "medium"
    elif 'large' in revenue or '5m' in revenue:
        segment = "large"
    else:
        segment = "enterprise"
    
    data = {
        "user_id": user_id,
        "name": lead_data.get('name', ''),
        "business_duration": lead_data.get('business_duration', ''),
        "telegram": lead_data.get('telegram', ''),
        "email": lead_data.get('email', ''),
        "business": lead_data.get('business', ''),
        "revenue": lead_data.get('revenue', ''),
        "participants": lead_data.get('participants', ''),
        "zoom_time": lead_data.get('zoom_time', ''),
        "segment": segment
    }
    save_to_supabase("leads_consultation", data)
    save_to_supabase("segments", {
        "user_id": user_id,
        "segment": segment
    })

def notify_admin_consultation(lead_data):
    """Отправляет уведомление администратору только для консультаций"""
    if ADMIN_CHAT_ID == 0:
        print("⚠️ ADMIN_CHAT_ID не установлен")
        return
    
    segment = determine_segment(lead_data.get('revenue', ''))
    notification = f"""
🔔 *НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ!*

👤 Имя: {lead_data.get('name')}
⏱️ Время функционирования бизнеса: {lead_data.get('business_duration')}
📱 Telegram: {lead_data.get('telegram')}
📧 Email: {lead_data.get('email')}
🏢 Бизнес: {lead_data.get('business')}
💰 Выручка: {lead_data.get('revenue')}
👥 На созвоне: {lead_data.get('participants')}
🎥 Предпочитаемое время Zoom: {lead_data.get('zoom_time')}
📊 *Сегмент:* {segment.upper()}
⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    try:
        bot.send_message(ADMIN_CHAT_ID, notification, parse_mode="Markdown")
        print(f"✅ Уведомление отправлено админу")
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")

def determine_segment(revenue):
    """Определяет сегмент по выручке"""
    revenue = str(revenue).lower()
    if 'small' in revenue or '< 300k' in revenue or '<300k' in revenue:
        return "small"
    elif 'medium' in revenue or '300k-1m' in revenue:
        return "medium"
    elif 'large' in revenue or '1m-5m' in revenue:
        return "large"
    else:
        return "enterprise"

# ===== ПРОВЕРКА ПОДПИСКИ =====
def check_user_subscription(user_id):
    """
    Проверяет подписку пользователя на канал.
    ВАЖНО: Это требует специальных прав бота!
    Если бот не админ в канале - функция вернёт False
    """
    try:
        member_status = bot.get_chat_member(CHANNEL_ID, user_id)
        # Статусы подписки: 'creator', 'administrator', 'member', 'restricted', 'left', 'kicked'
        if member_status.status in ['creator', 'administrator', 'member']:
            return True
        else:
            return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки подписки: {e}")
        # Если ошибка - возвращаем False для безопасности
        return False

# ===== WEBHOOK =====
@app.route('/telegram-webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        if json_data:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return "ERROR", 400

# ===== /START =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    print(f"🆔 User ID: {user_id}")
    log_action(user_id, user_name, "START_COMMAND", "Пользователь запустил бота")
    
    welcome_text = f"""👋 Привет, {user_name}!

🎯 Я бот AI2BIZ — помогу получить материалы по автоматизации продаж.

*Что я могу:*

1️⃣ Отправить PDF файлы → напиши: *файлы*
   (Выбери один из двух: "5 ошибок менеджеров" или "Чек-лист")

2️⃣ Записать на консультацию → напиши: *консультация*
   (Подробная заявка + бронирование времени)

*Материалы помогут:*
✅ Увеличить конверсию на 150-300%
✅ Автоматизировать работу менеджеров
✅ Не потерять 50% лидов

📚 Выбери действие!"""
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

# ===== ОСНОВНАЯ ОБРАБОТКА =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    text = message.text.lower().strip()
    
    # ФАЙЛЫ - ПРОВЕРКА ПОДПИСКИ
    if any(word in text for word in ["файл", "files", "ошибок", "чеклист"]):
        user_state[user_id] = "files"
        user_data[user_id] = {}
        
        # Отправляем сообщение с кнопками для подписки
        msg = bot.send_message(
            message.chat.id,
            """📱 *Важно!* Для получения материалов нужно подписаться на наш канал.

📢 Там мы делимся эксклюзивными материалами и инсайтами по автоматизации.

Подпишись и нажми "Я подписался" 👇""",
            parse_mode="Markdown",
            reply_markup=get_subscription_buttons()
        )
        bot.register_next_step_handler(msg, handle_subscription_check, user_id)
    
    # КОНСУЛЬТАЦИЯ - СВОЯ АНКЕТА
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт"]):
        user_state[user_id] = "consultation"
        user_data[user_id] = {}
        msg = bot.send_message(
            message.chat.id,
            "🎯 Отлично! Давайте запишемся на консультацию.\n\n*Как тебя зовут?*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, ask_consultation_business_duration, user_id)
    
    # АДМИНИСТРАТОР: РАССЫЛКА
    elif text.startswith('/broadcast_small') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "small", message.text.replace("/broadcast_small ", ""))
    elif text.startswith('/broadcast_medium') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "medium", message.text.replace("/broadcast_medium ", ""))
    elif text.startswith('/broadcast_large') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "large", message.text.replace("/broadcast_large ", ""))
    elif text.startswith('/broadcast_enterprise') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "enterprise", message.text.replace("/broadcast_enterprise ", ""))
    else:
        bot.send_message(
            message.chat.id,
            "❓ Команда не понята.\n\n*Используй:*\n• файлы\n• консультация",
            parse_mode="Markdown"
        )

# ===== КНОПКИ ПОДПИСКИ =====
def get_subscription_buttons():
    """Возвращает кнопки для проверки подписки"""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("✅ Я подписался")
    markup.add("🔗 Подписаться на канал")
    return markup

# ===== ПРОВЕРКА ПОДПИСКИ =====
def handle_subscription_check(message, user_id):
    """Проверяет подписку пользователя"""
    text = message.text.lower().strip()
    
    # Если нажал "Подписаться на канал" - даем ссылку
    if "подписаться" in text and "подписался" not in text:
        msg = bot.send_message(
            message.chat.id,
            f"""🔗 *Подпишись на канал:*

https://t.me/it_ai2biz

После подписки нажми кнопку "Я подписался" 👇""",
            parse_mode="Markdown",
            reply_markup=get_subscription_buttons()
        )
        bot.register_next_step_handler(msg, handle_subscription_check, user_id)
        return
    
    # Если нажал "Я подписался" - проверяем
    if "подписался" in text:
        if check_user_subscription(user_id):
            # Пользователь подписан - переходим к выбору файла
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("📄 5 ошибок менеджеров")
            markup.add("✅ Чек-лист")
            
            msg = bot.send_message(
                message.chat.id,
                "✅ *Отлично! Подписка подтверждена!*\n\n📚 Выбери материал:",
                parse_mode="Markdown",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, handle_file_selection, user_id)
        else:
            # Не подписан - просим еще раз
            msg = bot.send_message(
                message.chat.id,
                """❌ *Похоже, ты еще не подписан на канал.*

Подпишись на канал https://t.me/it_ai2biz и попробуй еще раз 👇""",
                parse_mode="Markdown",
                reply_markup=get_subscription_buttons()
            )
            bot.register_next_step_handler(msg, handle_subscription_check, user_id)

# ===== ВЫБОР ФАЙЛА =====
def handle_file_selection(message, user_id):
    """Обрабатывает выбор файла"""
    text = message.text.lower().strip()
    
    if "ошибок" in text or "менеджеров" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: 5 ошибок менеджеров")
    elif "чек" in text or "лист" in text:
        user_data[user_id]["file_type"] = "checklist"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: Чек-лист")
    else:
        # Неправильный выбор
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("📄 5 ошибок менеджеров")
        markup.add("✅ Чек-лист")
        
        msg = bot.send_message(
            message.chat.id,
            "❌ Пожалуйста, выбери один из предложенных вариантов",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return
    
    # Переходим к анкете
    msg = bot.send_message(
        message.chat.id,
        "📝 Отлично! Теперь заполни краткую анкету.\n\n*Как тебя зовут?*",
        parse_mode="Markdown",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, ask_files_business_duration, user_id)

# ===== АНКЕТА ФАЙЛОВ =====
def ask_files_business_duration(message, user_id):
    user_data[user_id]["name"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    
    msg = bot.send_message(
        message.chat.id,
        "*Сколько времени функционирует ваш бизнес?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, ask_files_telegram, user_id)

def ask_files_telegram(message, user_id):
    user_data[user_id]["business_duration"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Твой Telegram?*\n\n(@username или ссылка)",
        parse_mode="Markdown",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, ask_files_business, user_id)

def ask_files_business(message, user_id):
    user_data[user_id]["telegram"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Расскажи о своём бизнесе:*\n\nНиша, продукт, основные проблемы",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_files_revenue, user_id)

def ask_files_revenue(message, user_id):
    user_data[user_id]["business"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    
    msg = bot.send_message(
        message.chat.id,
        "*Выручка в месяц?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, finish_form_files, user_id)

def finish_form_files(message, user_id):
    user_data[user_id]["revenue"] = message.text
    app = user_data[user_id]
    
    # Сохраняем лид файлов
    save_lead_files(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_FILES", f"Заявка на файлы: {app.get('file_type')}")
    
    # Отправляем выбранный файл
    bot.send_message(
        message.chat.id,
        "📄 Отправляю твой файл...",
        parse_mode="Markdown",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    
    try:
        # Определяем какой файл отправить
        if app.get('file_type') == "5_mistakes":
            file_url = FILE_5_MISTAKES
            caption = "📄 *5 ошибок менеджеров, из-за которых теряются 50% лидов*\n\n✅ Этот материал поможет увеличить конверсию на 150-300%"
        else:
            file_url = FILE_CHECKLIST
            caption = "📄 *Чек-лист: 10 способов обнаружить, теряете ли вы лидов*\n\n✅ Проверьте свою воронку продаж прямо сейчас"
        
        bot.send_document(
            message.chat.id,
            file_url,
            caption=caption,
            parse_mode="Markdown"
        )
        
        log_action(user_id, app.get('name'), "DOWNLOAD_FILES", f"Получил файл: {app.get('file_type')}")
        
        # Призыв к действию
        call_to_action = """
🚀 *Готовы ускорить результаты?*

Файлы помогут вам понять проблему, но реальные результаты начинаются с автоматизации.

✅ Увеличение конверсии на 150-300%
✅ Сокращение времени обработки лидов в 5 раз
✅ Окупаемость инвестиций за 2-4 недели

💬 *Запишитесь на бесплатную консультацию* и узнайте:
• Какие процессы можно автоматизировать в вашем бизнесе
• На сколько вырастет выручка после внедрения
• Сколько стоит решение именно для вас

📅 Просто напишите: *консультация*

Специалист AI2BIZ свяжется с вами в течение часа!
"""
        bot.send_message(message.chat.id, call_to_action, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# ===== АНКЕТА КОНСУЛЬТАЦИИ =====
def ask_consultation_business_duration(message, user_id):
    user_data[user_id]["name"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    
    msg = bot.send_message(
        message.chat.id,
        "*Сколько времени функционирует ваш бизнес?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, ask_consultation_telegram, user_id)

def ask_consultation_telegram(message, user_id):
    user_data[user_id]["business_duration"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Твой Telegram?*\n\n(@username или ссылка)",
        parse_mode="Markdown",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, ask_consultation_email, user_id)

def ask_consultation_email(message, user_id):
    user_data[user_id]["telegram"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Email адрес?*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_consultation_business, user_id)

def ask_consultation_business(message, user_id):
    user_data[user_id]["email"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Расскажи о своём бизнесе:*\n\nНиша, выручка, продукт, проблемы",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_consultation_revenue, user_id)

def ask_consultation_revenue(message, user_id):
    user_data[user_id]["business"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    
    msg = bot.send_message(
        message.chat.id,
        "*Выручка в месяц?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, ask_consultation_participants, user_id)

def ask_consultation_participants(message, user_id):
    user_data[user_id]["revenue"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Я один", "С партнером")
    markup.add("Не принимаю решений")
    
    msg = bot.send_message(
        message.chat.id,
        "*Кто будет на созвоне?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, ask_consultation_zoom_time, user_id)

def ask_consultation_zoom_time(message, user_id):
    user_data[user_id]["participants"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Завтра (9:00 - 12:00)", "Завтра (12:00 - 18:00)")
    markup.add("После завтра", "В выходные")
    
    msg = bot.send_message(
        message.chat.id,
        "*Когда будет удобно выйти в Zoom?*",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, finish_form_consultation, user_id)

def finish_form_consultation(message, user_id):
    user_data[user_id]["zoom_time"] = message.text
    app = user_data[user_id]
    
    # Сохраняем лид консультации
    save_lead_consultation(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_CONSULTATION", "Заявка на консультацию")
    
    # Отправляем уведомление администратору ТОЛЬКО для консультации
    notify_admin_consultation(app)
    
    # Финальное сообщение пользователю
    confirmation = f"""✅ *Спасибо!* Заявка принята.

📋 *Твои данные:*
👤 {app.get('name')}
⏱️ {app.get('business_duration')}
📱 {app.get('telegram')}
📧 {app.get('email')}

🎯 Наш специалист свяжется с тобой в Telegram в течение часа и согласует точное время встречи.

⏰ Ты указал(а): {app.get('zoom_time')}

Спасибо, что выбрал AI2BIZ! 🚀"""
    
    bot.send_message(
        message.chat.id,
        confirmation,
        parse_mode="Markdown",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )

# ===== РАССЫЛКИ (только для админа) =====
def broadcast_by_segment(admin_id, segment, message_text):
    """Рассылка определённому сегменту"""
    if not message_text:
        bot.send_message(admin_id, "❌ Укажите текст рассылки\n\nПример: /broadcast_small Привет, это рассылка!")
        return
    
    try:
        import requests
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/segments?segment=eq.{segment}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            bot.send_message(admin_id, f"❌ Ошибка получения списка: {response.text}")
            return
        
        users = response.json()
        count = 0
        for user_obj in users:
            try:
                bot.send_message(user_obj['user_id'], message_text, parse_mode="Markdown")
                count += 1
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_obj['user_id']}: {e}")
        
        bot.send_message(admin_id, f"✅ Рассылка отправлена {count} пользователям сегмента {segment.upper()}")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка: {str(e)}")

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    return """
    <h1>✅ AI2BIZ Telegram Bot работает!</h1>
    <p><strong>Версия:</strong> Advanced V2 (выбор файлов + проверка подписки) - ИСПРАВЛЕННАЯ</p>
    <p><strong>Статус:</strong> Готов к использованию</p>
    <hr>
    <h2>📋 Функции:</h2>
    <ul>
        <li>✅ Две отдельные анкеты (файлы и консультация)</li>
        <li>✅ Выбор между двумя файлами: "5 ошибок менеджеров" или "Чек-лист"</li>
        <li>✅ Обязательная подписка на канал @it_ai2biz перед получением файлов</li>
        <li>✅ Кнопки-варианты для выручки и времени функционирования</li>
        <li>✅ Уведомления админу только на консультацию</li>
        <li>✅ Отправка выбранного пользователем файла</li>
    </ul>
    """

# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    print("🤖 Бот AI2BIZ запущен!")
    print("💾 Таблицы в Supabase: leads_consultation, leads_files, segments, stats")
    print(f"📱 Канал для подписки: {CHANNEL_ID}")
    bot.infinity_polling()
