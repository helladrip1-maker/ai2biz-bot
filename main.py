#!/usr/bin/env python3
"""
AI2BIZ Telegram Bot - ADVANCED VERSION
- Анкета перед файлами
- Уведомления админу в Telegram
- Сегментация и рассылки
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
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))  # ← НОВАЯ ПЕРЕМЕННАЯ

FILE_5_MISTAKES = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/5%20mistakes%20of%20managers.pdf"
FILE_CHECKLIST = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check%20list%2010%20ways.pdf"

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_data = {}
user_state = {}  # new_user: ожидание заполнения анкеты, consultation: для консультации

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

def save_lead(user_id, lead_data):
    """Сохраняет лид в таблицу leads"""
    # Определяем сегмент по выручке
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
        "age": lead_data.get('age', ''),
        "telegram": lead_data.get('telegram', ''),
        "email": lead_data.get('email', ''),
        "business": lead_data.get('business', ''),
        "socials": lead_data.get('socials', ''),
        "revenue": lead_data.get('revenue', ''),
        "participants": lead_data.get('participants', ''),
        "segment": segment
    }
    
    save_to_supabase("leads", data)
    
    # Сохраняем в таблицу segments для рассылок
    save_to_supabase("segments", {
        "user_id": user_id,
        "segment": segment
    })

def notify_admin(lead_data):
    """Отправляет уведомление администратору"""
    if ADMIN_CHAT_ID == 0:
        print("⚠️ ADMIN_CHAT_ID не установлен")
        return
    
    segment = determine_segment(lead_data.get('revenue', ''))
    
    notification = f"""
🔔 *НОВАЯ ЗАЯВКА!*

👤 Имя: {lead_data.get('name')}
📅 Возраст: {lead_data.get('age')}
📱 Telegram: {lead_data.get('telegram')}
📧 Email: {lead_data.get('email')}
🏢 Бизнес: {lead_data.get('business')}
🌐 Соцсети: {lead_data.get('socials')}
💰 Выручка: {lead_data.get('revenue')}
👥 На созвоне: {lead_data.get('participants')}

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
    
    # Выводим user_id для админа
    print(f"🆔 User ID: {user_id}")
    
    log_action(user_id, user_name, "START_COMMAND", "Пользователь запустил бота")
    
    welcome_text = f"""👋 Привет, {user_name}!

🎯 Я бот AI2BIZ — помогу получить материалы по автоматизации продаж.

*Что я могу:*
1️⃣ Отправить PDF файлы → напиши: *файлы*
   (Нужно заполнить анкету)
2️⃣ Записать на консультацию → напиши: *консультация*

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
    
    # ФАЙЛЫ - ТРЕБУЕТСЯ АНКЕТА
    if any(word in text for word in ["файл", "files", "ошибок", "чеклист"]):
        user_state[user_id] = "new_user"  # ← НОВОЕ: состояние
        user_data[user_id] = {}
        
        msg = bot.send_message(
            message.chat.id,
            "📝 Отлично! Для получения файлов заполни анкету.\n\n*Как тебя зовут?*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, ask_age, user_id)
    
    # КОНСУЛЬТАЦИЯ
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт"]):
        user_state[user_id] = "consultation"
        user_data[user_id] = {}
        
        msg = bot.send_message(
            message.chat.id,
            "🎯 Отлично! Давайте запишемся на консультацию.\n\n*Как тебя зовут?*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, ask_age, user_id)
    
    # АДМИНИСТРАТОР: РАССЫЛКА
    elif text.startswith('/broadcast_small') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "small", message.text.replace("/broadcast_small ", ""))
    
    elif text.startswith('/broadcast_medium') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "medium", message.text.replace("/broadcast_medium ", ""))
    
    elif text.startswith('/broadcast_large') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "large", message.text.replace("/broadcast_large ", ""))
    
    elif text.startswith('/broadcast_enterprise') and user_id == ADMIN_CHAT_ID:
        broadcast_by_segment(user_id, "enterprise", message.text.replace("/broadcast_enterprise ", ""))
    
    elif text == '/broadcast_all' and user_id == ADMIN_CHAT_ID:
        broadcast_to_all(user_id)
    
    else:
        bot.send_message(
            message.chat.id,
            "❓ Команда не понята.\n\n*Используй:*\n• файлы\n• консультация",
            parse_mode="Markdown"
        )

# ===== АНКЕТА (одна для файлов и консультации) =====
def ask_age(message, user_id):
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["name"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Сколько вам лет?*\n\n17-20 / 21-30 / 31-40 / 41-50",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_telegram, user_id)

def ask_telegram(message, user_id):
    user_data[user_id]["age"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Твой Telegram?* (@username или ссылка)",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_email, user_id)

def ask_email(message, user_id):
    user_data[user_id]["telegram"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Email адрес?*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_business, user_id)

def ask_business(message, user_id):
    user_data[user_id]["email"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Расскажи о своём бизнесе:*\n\nНиша, выручка, продукт, проблемы",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_socials, user_id)

def ask_socials(message, user_id):
    user_data[user_id]["business"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Социальные сети или сайт компании?*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_revenue, user_id)

def ask_revenue(message, user_id):
    user_data[user_id]["socials"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Выручка в месяц?*\n\n< 300K / 300K-1M / 1M-5M / 5M+",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_participants, user_id)

def ask_participants(message, user_id):
    user_data[user_id]["revenue"] = message.text
    msg = bot.send_message(
        message.chat.id,
        "*Кто будет на созвоне?*\n\nЯ один / С партнером / Не принимаю решений",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, finish_form, user_id)

def finish_form(message, user_id):
    user_data[user_id]["participants"] = message.text
    app = user_data[user_id]
    state = user_state.get(user_id, "new_user")
    
    # Сохраняем лид в БД
    save_lead(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED", f"Заявка ({state})")
    
    # Отправляем уведомление админу
    notify_admin(app)
    
    # ЕСЛИ ФАЙЛЫ
    if state == "new_user":
        bot.send_message(
            message.chat.id,
            "📄 Отправляю файлы: *5 ошибок менеджеров* и *Чек-лист*\n\nПожалуйста, подождите...",
            parse_mode="Markdown"
        )
        
        try:
            bot.send_document(
                message.chat.id,
                FILE_5_MISTAKES,
                caption="📄 *5 ошибок менеджеров, из-за которых теряются 50% лидов*\n\n✅ Этот материал поможет увеличить конверсию на 150-300%",
                parse_mode="Markdown"
            )
            bot.send_document(
                message.chat.id,
                FILE_CHECKLIST,
                caption="📄 *Чек-лист: 10 способов обнаружить, теряете ли вы лидов*\n\n✅ Проверьте свою воронку продаж прямо сейчас",
                parse_mode="Markdown"
            )
            log_action(user_id, app.get('name'), "DOWNLOAD_FILES", "Получил файлы")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    
    # ЕСЛИ КОНСУЛЬТАЦИЯ
    elif state == "consultation":
        confirmation = f"""✅ *Спасибо!* Заявка принята.

📋 *Твои данные:*
👤 {app.get('name')}
📅 {app.get('age')} лет
📱 {app.get('telegram')}
📧 {app.get('email')}

🔗 *Ссылка на Zoom:*
{ZOOM_LINK}

⏰ Менеджер свяжется с тобой через 30 минут!"""
        
        bot.send_message(message.chat.id, confirmation, parse_mode="Markdown")

# ===== РАССЫЛКИ (только для админа) =====
def broadcast_by_segment(admin_id, segment, message_text):
    """Рассылка определённому сегменту"""
    if not message_text:
        bot.send_message(admin_id, "❌ Укажите текст рассылки\n\nПример: /broadcast_small Привет, это рассылка!")
        return
    
    try:
        import requests
        
        # Получаем всех пользователей сегмента
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

def broadcast_to_all(admin_id):
    """Рассылка всем"""
    bot.send_message(admin_id, "📤 Укажите текст:\n\n/broadcast_all_text Ваш текст")

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI2BIZ Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial; background: #f5f5f5; padding: 40px; }
            .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
            h1 { color: #208D8F; }
            .status { display: inline-block; background: #20B8AA; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }
            ul { color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 AI2BIZ Bot</h1>
            <div class="status">✅ ОНЛАЙН</div>
            <p><strong>Версия:</strong> Advanced (с анкетой, уведомлениями, рассылками)</p>
            <h3>📊 Функции:</h3>
            <ul>
                <li>📝 Анкета перед файлами</li>
                <li>🔔 Уведомления админу в Telegram</li>
                <li>📊 Сегментация клиентов</li>
                <li>📤 Рассылки по сегментам</li>
                <li>💾 Сохранение в Supabase</li>
            </ul>
        </div>
    </body>
    </html>
    """

# ===== ЗАПУСК =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Бот запущен на порте {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)