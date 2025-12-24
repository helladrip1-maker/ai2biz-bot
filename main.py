#!/usr/bin/env python3
"""
AI2BIZ Telegram Bot - WEBHOOK VERSION
Работает на Render.com + Supabase
Загружает файлы из Supabase Storage
ТОЛЬКО WEBHOOK (БЕЗ POLLING)
"""

import os
import telebot
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv("TOKEN", "8250447998:AAF_vB2bjeB-_37z--52_Sk-18mqamdIR58")
ZOOM_LINK = os.getenv("ZOOM_LINK", "https://zoom.us/YOUR_ZOOM_LINK")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kbijiiabluexmotyhaez.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# URLs для файлов в Supabase Storage
FILE_5_MISTAKES = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/5%20mistakes%20of%20managers.pdf"
FILE_CHECKLIST = "https://kbijiiabluexmotyhaez.supabase.co/storage/v1/object/public/bot-files/Check%20list%2010%20ways.pdf"

# Инициализируем Flask и Bot (ВАЖНО: threaded=False для webhook)
bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# Временное хранилище для мультишаговых форм
user_data = {}

# ===== SUPABASE ФУНКЦИИ =====
def save_to_supabase(table, data):
    """Сохраняет данные в Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"⚠️ Supabase не настроена. Данные не сохранены: {data}")
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
        print(f"❌ Ошибка при сохранении: {e}")
        return False

def log_action(user_id, name, action, details=""):
    """Логирует действие в консоль и Supabase"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {action} | {name} ({user_id}) | {details}"
    print(log_msg)
    
    # Сохраняем в Supabase
    save_to_supabase("stats", {
        "user_id": user_id,
        "name": name,
        "action": action,
        "details": details
    })

def save_application(user_id, app_data):
    """Сохраняет заявку на консультацию"""
    data = {
        "user_id": user_id,
        "name": app_data.get('name', ''),
        "age": app_data.get('age', ''),
        "telegram": app_data.get('telegram', ''),
        "email": app_data.get('email', ''),
        "business": app_data.get('business', ''),
        "socials": app_data.get('socials', ''),
        "revenue": app_data.get('revenue', ''),
        "participants": app_data.get('participants', '')
    }
    
    save_to_supabase("applications", data)

# ===== WEBHOOK ENDPOINT =====
@app.route('/telegram-webhook', methods=['POST'])
def webhook():
    """Получает обновления от Telegram через webhook"""
    try:
        json_data = request.get_json()
        if json_data:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return "OK", 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
    return "ERROR", 400

# ===== КОМАНДА /START =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    
    log_action(user_id, user_name, "START_COMMAND", "Пользователь запустил бота")
    
    welcome_text = f"""👋 Привет, {user_name}!

🎯 Я бот AI2BIZ — помогу получить материалы по автоматизации продаж.

*Что я могу:*
1️⃣ Отправить PDF файлы → напиши: *ошибки* или *чеклист*
2️⃣ Записать на консультацию → напиши: *консультация*

*Материалы помогут:*
✅ Увеличить конверсию на 150-300%
✅ Автоматизировать работу менеджеров
✅ Не потерять 50% лидов

📚 Напиши ключевое слово и начнём!"""
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

# ===== ОБРАБОТКА ВСЕХ СООБЩЕНИЙ =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Гость"
    text = message.text.lower().strip()
    
    # ОШИБКИ
    if any(word in text for word in ["ошибок", "ошиб", "5 ошибок"]):
        bot.send_message(
            message.chat.id,
            "📄 Отправляю файл: *5 ошибок менеджеров, из-за которых теряется 50% лидов*\n\nПожалуйста, подождите...",
            parse_mode="Markdown"
        )
        
        try:
            bot.send_document(
                message.chat.id,
                FILE_5_MISTAKES,
                caption="📄 *5 ошибок менеджеров, из-за которых теряются 50% лидов*\n\n✅ Этот материал поможет увеличить конверсию на 150-300%",
                parse_mode="Markdown"
            )
            log_action(user_id, user_name, "DOWNLOAD_FILE", "5 mistakes of managers.pdf")
        except Exception as e:
            print(f"❌ Ошибка отправки файла: {e}")
            bot.send_message(message.chat.id, f"❌ Ошибка при отправке файла: {str(e)}")
    
    # ЧЕКЛИСТ
    elif any(word in text for word in ["чеклист", "чек", "способ", "10"]):
        bot.send_message(
            message.chat.id,
            "📄 Отправляю файл: *Чек-лист: 10 способов обнаружить, теряете ли вы лидов*\n\nПожалуйста, подождите...",
            parse_mode="Markdown"
        )
        
        try:
            bot.send_document(
                message.chat.id,
                FILE_CHECKLIST,
                caption="📄 *Чек-лист: 10 способов обнаружить, теряете ли вы лидов*\n\n✅ Проверьте свою воронку продаж прямо сейчас",
                parse_mode="Markdown"
            )
            log_action(user_id, user_name, "DOWNLOAD_FILE", "Check list 10 ways.pdf")
        except Exception as e:
            print(f"❌ Ошибка отправки файла: {e}")
            bot.send_message(message.chat.id, f"❌ Ошибка при отправке файла: {str(e)}")
    
    # КОНСУЛЬТАЦИЯ
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт"]):
        user_data[user_id] = {"user_name": user_name}
        msg = bot.send_message(
            message.chat.id,
            "🎯 Отлично! Давайте запишемся на консультацию.\n\n*Как тебя зовут?*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, ask_age, user_id)
    
    else:
        bot.send_message(
            message.chat.id,
            "❓ Я не понял команду.\n\n*Используй:*\n"
            "• ошибки\n"
            "• чеклист\n"
            "• консультация",
            parse_mode="Markdown"
        )

# ===== АНКЕТА КОНСУЛЬТАЦИИ =====
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
    
    # Сохраняем заявку
    save_application(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED", "Заявка на консультацию")
    
    confirmation = f"""✅ *Спасибо!* Заявка принята.

📋 *Твои данные:*
👤 {app.get('name', 'N/A')}
📅 {app.get('age', 'N/A')} лет
📱 {app.get('telegram', 'N/A')}
📧 {app.get('email', 'N/A')}

🔗 *Ссылка на Zoom встречу:*
{ZOOM_LINK}

⏰ Менеджер свяжется с тобой через 30 минут!

Вопросы? → @it_ai2biz_bot"""
    
    bot.send_message(message.chat.id, confirmation, parse_mode="Markdown")

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 AI2BIZ Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                background: linear-gradient(135deg, #208D8F 0%, #1A7478 100%); 
                min-height: 100vh; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
            }
            .container { 
                background: white; 
                border-radius: 12px; 
                padding: 40px; 
                max-width: 500px; 
                box-shadow: 0 10px 40px rgba(0,0,0,0.2); 
            }
            h1 { color: #208D8F; margin-bottom: 10px; font-size: 28px; }
            .status { 
                display: inline-block; 
                background: #20B8AA; 
                color: white; 
                padding: 8px 16px; 
                border-radius: 20px; 
                font-size: 12px; 
                font-weight: bold;
                margin-bottom: 20px; 
            }
            p { color: #666; line-height: 1.6; margin-bottom: 12px; }
            ul { padding-left: 20px; color: #666; }
            li { margin-bottom: 10px; }
            .info { 
                background: #f5f5f5; 
                padding: 15px; 
                border-radius: 8px; 
                margin-top: 20px; 
                font-size: 13px; 
                color: #666; 
            }
            h3 { color: #208D8F; margin-top: 20px; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 AI2BIZ Telegram Bot</h1>
            <div class="status">✅ ОНЛАЙН</div>
            
            <p><strong>Бот:</strong> @it_ai2biz_bot</p>
            <p><strong>Платформа:</strong> Render + Supabase</p>
            <p><strong>Тип подключения:</strong> Webhook</p>
            <p><strong>Статус:</strong> <strong style="color: #20B8AA;">Работает 24/7</strong></p>
            
            <h3>📊 Функции:</h3>
            <ul>
                <li>📄 Раздача PDF файлов</li>
                <li>📝 Запись на консультацию</li>
                <li>💾 Сохранение заявок в БД</li>
                <li>📊 Логирование действий</li>
                <li>🔗 Отправка Zoom ссылки</li>
            </ul>
            
            <div class="info">
                <strong>✅ Всё готово!</strong><br>
                Бот полностью функционален и готов к использованию.
            </div>
        </div>
    </body>
    </html>
    """

# ===== ЗАПУСК ПРИЛОЖЕНИЯ =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Запуск бота на порте {port}...")
    print(f"🤖 TOKEN: {TOKEN[:20]}...")
    print(f"📍 Webhook endpoint: /telegram-webhook")
    print(f"⚠️ ТОЛЬКО WEBHOOK - polling ОТКЛЮЧЕН")
    app.run(host="0.0.0.0", port=port, debug=False)
