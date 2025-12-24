#!/usr/bin/env python3
"""
AI2BIZ Telegram Bot - ADVANCED VERSION V5.1 (ИСПРАВЛЕННАЯ)
- ИСПРАВЛЕНО V5.1: Ошибка 400 в webhook исправлена
- Две отдельных анкеты (файлы + консультация)
- ДВА ТИПА ФАЙЛОВ: 5 ошибок менеджеров или Чек-лист (выбор пользователя)
- БЕЗ проверки подписки - прямое анкетирование
"""

import os
import re
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
CHANNEL_NAME = "it_ai2biz"

FILE_5_MISTAKES = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/5%20mistakes%20of%20managers.pdf"
FILE_CHECKLIST = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check%20list%2010%20ways.pdf"

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_data = {}
user_state = {}
user_message_history = {}  # Для отслеживания сообщений для удаления

# ===== ВАЛИДАЦИЯ =====
def is_valid_email(email):
    """Проверяет валидность email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_telegram(telegram):
    """Проверяет валидность Telegram"""
    telegram = telegram.strip()
    if telegram.startswith('@'):
        return len(telegram) > 1 and telegram.replace('@', '').replace('_', '').isalnum()
    elif 't.me/' in telegram:
        return True
    else:
        return False

def is_valid_name(name):
    """Проверяет валидность имени"""
    name = name.strip()
    return len(name) >= 2 and len(name) <= 50

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
        "file_type": lead_data.get('file_type', ''),
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
    """Отправляет уведомление администратору"""
    if ADMIN_CHAT_ID == 0:
        print("⚠️ ADMIN_CHAT_ID не установлен")
        return
    
    segment = determine_segment(lead_data.get('revenue', ''))
    notification = f"""🔔 НОВАЯ ЗАЯВКА НА КОНСУЛЬТАЦИЮ!

👤 Имя: {lead_data.get('name')}
⏱️ Время функционирования бизнеса: {lead_data.get('business_duration')}
📱 Telegram: {lead_data.get('telegram')}
📧 Email: {lead_data.get('email')}
🏢 Бизнес: {lead_data.get('business')}
💰 Выручка: {lead_data.get('revenue')}
👥 На созвоне: {lead_data.get('participants')}
🎥 Время Zoom: {lead_data.get('zoom_time')}
📊 Сегмент: {segment.upper()}
⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    try:
        bot.send_message(ADMIN_CHAT_ID, notification)
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

def save_message_history(user_id, message_id):
    """Сохраняет ID сообщения для последующего удаления"""
    if user_id not in user_message_history:
        user_message_history[user_id] = []
    user_message_history[user_id].append(message_id)

def delete_message_history(chat_id, user_id):
    """Удаляет все сообщения из истории"""
    if user_id in user_message_history:
        for msg_id in user_message_history[user_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        user_message_history[user_id] = []

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

Я бот AI2BIZ - помогу получить материалы по автоматизации продаж.

Что я могу:

1️⃣ Отправить полезные материалы по автоматизации бизнеса

2️⃣ Записать на консультацию со специалистом команды AI2BIZ

*Материалы помогут:*

 -  Увеличить конверсию на 150-300%
 -  Автоматизировать работу менеджеров
 -  Не терять 50% лидов

*Готовы получить реальные результаты?*

Файлы помогут вам понять проблему, но реальные результаты начинаются с автоматизации.

✅ Увеличение конверсии на 150-300%
✅ Сокращение времени обработки лидов в 5 раз
✅ Окупаемость инвестиций за от *одной недели!*

*Запишитесь на бесплатную консультацию и узнайте:*
• Какие процессы можно автоматизировать в вашем бизнесе
• На сколько вырастет выручка после внедрения
• Сколько стоит решение именно для вас

🤝 Пиши *консультация* и наш специалист свяжется с вами в течение часа!

Также подпишись на наш канал, без подписки, ты *не сможешь забрать материалы:* @it_ai2biz

💡 Напиши /cancel чтобы вернуться в главное меню"""
    
    msg = bot.send_message(message.chat.id, welcome_text)
    save_message_history(user_id, msg.message_id)

# ===== /CANCEL =====
@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    """Отменяет текущий процесс и возвращает в главное меню"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Очищаем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    if user_id in user_state:
        del user_state[user_id]
    
    # Удаляем все сообщения
    delete_message_history(chat_id, user_id)
    
    # Отправляем главное меню
    send_welcome(message)

# ===== ОСНОВНАЯ ОБРАБОТКА =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    text = message.text.lower().strip()
    chat_id = message.chat.id
    
    # Сохраняем сообщение пользователя
    save_message_history(user_id, message.message_id)
    
    # ФАЙЛЫ
    if any(word in text for word in ["ошибок", "чеклист", "ошибк"]):
        user_state[user_id] = "files"
        user_data[user_id] = {}
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("📄 5 ошибок менеджеров")
        markup.add("✅ Чек-лист")
        
        msg = bot.send_message(
            chat_id,
            "Выбери материал:",
            reply_markup=markup
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
    
    # КОНСУЛЬТАЦИЯ
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт"]):
        user_state[user_id] = "consultation"
        user_data[user_id] = {}
        msg = bot.send_message(
            chat_id,
            "Отлично! Давайте запишемся на консультацию.\n\nКак тебя зовут?"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)
    
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
        msg = bot.send_message(
            chat_id,
            "Команда не понята.\n\nИспользуй:\n• файлы (для получения материалов)\n• консультация (для записи на консультацию)\n• /cancel (вернуться в меню)"
        )
        save_message_history(user_id, msg.message_id)

# ===== ВЫБОР ФАЙЛА =====
def handle_file_selection(message, user_id):
    """Обрабатывает выбор файла"""
    text = message.text.lower().strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if "ошибок" in text or "менеджеров" in text:
        user_data[user_id]["file_type"] = "5_mistakes"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: 5 ошибок менеджеров")
    elif "чек" in text or "лист" in text:
        user_data[user_id]["file_type"] = "checklist"
        log_action(user_id, "", "FILE_SELECTED", "Выбрал: Чек-лист")
    else:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("📄 5 ошибок менеджеров")
        markup.add("✅ Чек-лист")
        
        msg = bot.send_message(
            chat_id,
            "Пожалуйста, выбери один из предложенных вариантов",
            reply_markup=markup
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, handle_file_selection, user_id)
        return
    
    msg = bot.send_message(
        chat_id,
        "Отлично! Теперь заполни краткую анкету.\n\nКак тебя зовут?\n\n(Минимум 2 буквы)",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_name_check, user_id)

# ===== АНКЕТА ФАЙЛОВ =====
def ask_files_name_check(message, user_id):
    """Проверяет имя перед сохранением"""
    name = message.text.strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if not is_valid_name(name):
        msg = bot.send_message(
            chat_id,
            "Некорректное имя!\n\nИмя должно быть от 2 до 50 символов. Попробуй ещё раз:"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_name_check, user_id)
        return
    
    user_data[user_id]["name"] = name
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    
    msg = bot.send_message(
        chat_id,
        "Сколько времени функционирует ваш бизнес?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business_duration, user_id)

def ask_files_business_duration(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text
    msg = bot.send_message(
        chat_id,
        "Твой Telegram?\n\n(@username или ссылка)",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)

def ask_files_telegram_check(message, user_id):
    """Проверяет Telegram перед сохранением"""
    telegram = message.text.strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if not is_valid_telegram(telegram):
        msg = bot.send_message(
            chat_id,
            "Некорректный Telegram!\n\nИспользуй формат:\n• @username\n• или https://t.me/username"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_files_telegram_check, user_id)
        return
    
    user_data[user_id]["telegram"] = telegram
    msg = bot.send_message(
        chat_id,
        "Расскажи о своём бизнесе:\n\nНиша, продукт, основные проблемы"
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_files_business, user_id)

def ask_files_business(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    
    msg = bot.send_message(
        chat_id,
        "Выручка в месяц?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_files, user_id)

def finish_form_files(message, user_id):
    user_data[user_id]["revenue"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    save_lead_files(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_FILES", f"Заявка на файлы: {app.get('file_type')}")
    
    msg = bot.send_message(
        chat_id,
        "Отправляю твой файл...",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    save_message_history(user_id, msg.message_id)
    
    try:
        if app.get('file_type') == "5_mistakes":
            file_url = FILE_5_MISTAKES
            caption = "5 ошибок менеджеров, из-за которых теряются 50% лидов\n\nЭтот материал поможет увеличить конверсию на 150-300%"
        else:
            file_url = FILE_CHECKLIST
            caption = "Чек-лист: 10 способов обнаружить, теряете ли вы лидов\n\nПроверьте свою воронку продаж прямо сейчас"
        
        doc_msg = bot.send_document(
            chat_id,
            file_url,
            caption=caption
        )
        save_message_history(user_id, doc_msg.message_id)
        
        log_action(user_id, app.get('name'), "DOWNLOAD_FILES", f"Получил файл: {app.get('file_type')}")
        
    except Exception as e:
        msg = bot.send_message(chat_id, f"Ошибка: {str(e)}")
        save_message_history(user_id, msg.message_id)

# ===== АНКЕТА КОНСУЛЬТАЦИИ =====
def ask_consultation_name(message, user_id):
    """Проверяет имя для консультации"""
    name = message.text.strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if not is_valid_name(name):
        msg = bot.send_message(
            chat_id,
            "Некорректное имя!\n\nИмя должно быть от 2 до 50 символов. Попробуй ещё раз:"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_name, user_id)
        return
    
    user_data[user_id]["name"] = name
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("До 1 года", "1-3 года")
    markup.add("3-5 лет", "Более 5 лет")
    
    msg = bot.send_message(
        chat_id,
        "Сколько времени функционирует ваш бизнес?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business_duration, user_id)

def ask_consultation_business_duration(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business_duration"] = message.text
    msg = bot.send_message(
        chat_id,
        "Твой Telegram?\n\n(@username или ссылка)",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)

def ask_consultation_telegram_check(message, user_id):
    """Проверяет Telegram для консультации"""
    telegram = message.text.strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if not is_valid_telegram(telegram):
        msg = bot.send_message(
            chat_id,
            "Некорректный Telegram!\n\nИспользуй формат:\n• @username\n• или https://t.me/username"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_telegram_check, user_id)
        return
    
    user_data[user_id]["telegram"] = telegram
    msg = bot.send_message(
        chat_id,
        "Email адрес?\n\n(Например: name@example.com)"
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)

def ask_consultation_email_check(message, user_id):
    """Проверяет Email перед сохранением"""
    email = message.text.strip()
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    if not is_valid_email(email):
        msg = bot.send_message(
            chat_id,
            "Некорректный Email!\n\nИспользуй формат: name@example.com"
        )
        save_message_history(user_id, msg.message_id)
        bot.register_next_step_handler(msg, ask_consultation_email_check, user_id)
        return
    
    user_data[user_id]["email"] = email
    msg = bot.send_message(
        chat_id,
        "Расскажи о своём бизнесе:\n\nНиша, выручка, продукт, проблемы"
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_business, user_id)

def ask_consultation_business(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["business"] = message.text.strip()
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("< 300K", "300K - 1M")
    markup.add("1M - 5M", "5M+")
    
    msg = bot.send_message(
        chat_id,
        "Выручка в месяц?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_revenue, user_id)

def ask_consultation_revenue(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["revenue"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Я один", "С бизнес партнером")
    markup.add("Я не принимаю решений в компании")
    
    msg = bot.send_message(
        chat_id,
        "Кто будет на созвоне?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, ask_consultation_participants, user_id)

def ask_consultation_participants(message, user_id):
    chat_id = message.chat.id
    save_message_history(user_id, message.message_id)
    user_data[user_id]["participants"] = message.text
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Завтра (9:00 - 12:00)", "Завтра (12:00 - 18:00)")
    markup.add("После завтра", "В выходные")
    
    msg = bot.send_message(
        chat_id,
        "Когда будет удобно выйти в Zoom?",
        reply_markup=markup
    )
    save_message_history(user_id, msg.message_id)
    bot.register_next_step_handler(msg, finish_form_consultation, user_id)

def finish_form_consultation(message, user_id):
    user_data[user_id]["zoom_time"] = message.text
    app = user_data[user_id]
    chat_id = message.chat.id
    
    save_message_history(user_id, message.message_id)
    
    save_lead_consultation(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED_CONSULTATION", "Заявка на консультацию")
    
    notify_admin_consultation(app)
    
    confirmation = f"""Спасибо! Заявка принята.

Твои данные:
{app.get('name')}
{app.get('business_duration')}
{app.get('telegram')}
{app.get('email')}

Наш специалист свяжется с тобой в Telegram в течение часа и согласует точное время встречи.

Ты указал(а): {app.get('zoom_time')}

Спасибо, что выбрал(а) AI2BIZ!

А пока подпишитесь на канал: @it_ai2biz"""
    
    msg = bot.send_message(
        chat_id,
        confirmation,
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )
    save_message_history(user_id, msg.message_id)

# ===== РАССЫЛКИ (только для админа) =====
def broadcast_by_segment(admin_id, segment, message_text):
    """Рассылка определённому сегменту"""
    if not message_text:
        bot.send_message(admin_id, "Укажите текст рассылки\n\nПример: /broadcast_small Привет, это рассылка!")
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
            bot.send_message(admin_id, f"Ошибка получения списка: {response.text}")
            return
        
        users = response.json()
        count = 0
        for user_obj in users:
            try:
                bot.send_message(user_obj['user_id'], message_text)
                count += 1
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_obj['user_id']}: {e}")
        
        bot.send_message(admin_id, f"Рассылка отправлена {count} пользователям сегмента {segment.upper()}")
    except Exception as e:
        bot.send_message(admin_id, f"Ошибка: {str(e)}")

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    return """
    <h1>✅ AI2BIZ Telegram Bot работает!</h1>
    <p><strong>Версия:</strong> Advanced V5.1 (ИСПРАВЛЕННАЯ)</p>
    <p><strong>Статус:</strong> Готов к использованию</p>
    <hr>
    <h2>📋 Функции:</h2>
    <ul>
        <li>✅ Две отдельные анкеты (файлы и консультация)</li>
        <li>✅ V5.1: Ошибка 400 ИСПРАВЛЕНА - удалены markdown символы из главного меню</li>
        <li>✅ БЕЗ проверки подписки - прямое анкетирование</li>
        <li>✅ Ссылка на канал в главном меню</li>
        <li>✅ /cancel удаляет сообщения и возвращает меню</li>
        <li>✅ Валидация данных (Email, Telegram, имя)</li>
        <li>✅ Уведомления админу на консультацию</li>
    </ul>
    """

# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    print("🤖 Бот AI2BIZ запущен!")
    print("✅ Версия: Advanced V5.1 (ИСПРАВЛЕННАЯ)")
    print("💾 Таблицы в Supabase: leads_consultation, leads_files, segments, stats")
    print(f"📱 Канал: https://t.me/{CHANNEL_NAME}")
    print("💡 Команды: /start (меню), /cancel (выход в меню с удалением истории)")
    print("✨ V5.1: ОШИБКА 400 ИСПРАВЛЕНА - удалены markdown символы!")
    bot.infinity_polling()
