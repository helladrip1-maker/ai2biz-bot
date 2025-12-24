#!/usr/bin/env python3
"""
AI2BIZ Telegram Bot - Main Entry Point
Работает на Render.com + Supabase
Загружает файлы из Supabase Storage
"""

import os
import telebot
from datetime import datetime
from flask import Flask, request
import json
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

# Инициализируем Flask и Bot
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Временное хранилище для мультишаговых форм
user_data = {}

# ===== СУPABASE ФУНКЦИИ =====
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
            print(f"✅ Сохранено в {table}: {data}")
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
    user_name = message.from_user.first_name or "Guest"
    
    log_action(user_id, user_name, "START_COMMAND", "User started bot")
    
    welcome_text = f"""👋 Hello, {user_name}!

🎯 I am AI2BIZ bot - helping you get materials on sales automation.

*What I can do:*
1️⃣ Send PDF files → write: *mistakes* or *checklist*
2️⃣ Sign up for a consultation → write: *consultation*

*These materials will help:*
✅ Increase conversion by 150-300%
✅ Automate manager work
✅ Not lose 50% of leads

📚 Write a keyword and let's start!"""
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

# ===== ОБРАБОТКА ВСЕХ СООБЩЕНИЙ =====
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Guest"
    text = message.text.lower().strip()
    
    # ОШИБКИ / MISTAKES
    if any(word in text for word in ["mistake", "ошибок", "ошиб", "5 ошибок", "5 mistakes"]):
        bot.send_message(
            message.chat.id,
            "📄 Sending: *5 mistakes of managers who lose 50% of leads*\n\nPlease wait...",
            parse_mode="Markdown"
        )
        
        try:
            bot.send_document(
                message.chat.id,
                FILE_5_MISTAKES,
                caption="📄 *5 mistakes of managers who lose 50% of leads*\n\n✅ This material will help increase conversion by 150-300%",
                parse_mode="Markdown"
            )
            log_action(user_id, user_name, "DOWNLOAD_FILE", "5 mistakes of managers.pdf")
        except Exception as e:
            print(f"❌ Error sending file: {e}")
            bot.send_message(message.chat.id, f"❌ Error sending file: {str(e)}")
    
    # ЧЕКЛИСТ / CHECKLIST
    elif any(word in text for word in ["checklist", "чеклист", "чек", "способ", "10", "check list"]):
        bot.send_message(
            message.chat.id,
            "📄 Sending: *Check list: 10 ways to detect lost leads*\n\nPlease wait...",
            parse_mode="Markdown"
        )
        
        try:
            bot.send_document(
                message.chat.id,
                FILE_CHECKLIST,
                caption="📄 *Check list: 10 ways to detect lost leads*\n\n✅ Check your sales funnel right now",
                parse_mode="Markdown"
            )
            log_action(user_id, user_name, "DOWNLOAD_FILE", "Check list 10 ways.pdf")
        except Exception as e:
            print(f"❌ Error sending file: {e}")
            bot.send_message(message.chat.id, f"❌ Error sending file: {str(e)}")
    
    # КОНСУЛЬТАЦИЯ / CONSULTATION
    elif any(word in text for word in ["консультац", "запись", "созвон", "консульт", "consultation", "consult", "call"]):
        user_data[user_id] = {"user_name": user_name}
        msg = bot.send_message(
            message.chat.id,
            "🎯 Great! Let's sign up for a consultation.\n\n*What is your name?*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, ask_age, user_id)
    
    else:
        bot.send_message(
            message.chat.id,
            "❓ I did not understand the command.\n\n*Use:*\n"
            "• mistakes\n"
            "• checklist\n"
            "• consultation",
            parse_mode="Markdown"
        )

# ===== АНКЕТА КОНСУЛЬТАЦИИ =====
def ask_age(message, user_id):
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["name"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*How old are you?*\n\n17-20 / 21-30 / 31-40 / 41-50",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_telegram, user_id)

def ask_telegram(message, user_id):
    user_data[user_id]["age"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Your Telegram?* (@username or link)",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_email, user_id)

def ask_email(message, user_id):
    user_data[user_id]["telegram"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Email address?*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_business, user_id)

def ask_business(message, user_id):
    user_data[user_id]["email"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Tell me about your business:*\n\nNiche, revenue, product, problems",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_socials, user_id)

def ask_socials(message, user_id):
    user_data[user_id]["business"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Company social media or website?*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_revenue, user_id)

def ask_revenue(message, user_id):
    user_data[user_id]["socials"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Monthly revenue?*\n\n< 300K / 300K-1M / 1M-5M / 5M+",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ask_participants, user_id)

def ask_participants(message, user_id):
    user_data[user_id]["revenue"] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "*Who will be on the call?*\n\nMe alone / With partner / I don't make decisions",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, finish_form, user_id)

def finish_form(message, user_id):
    user_data[user_id]["participants"] = message.text
    app = user_data[user_id]
    
    # Сохраняем заявку
    save_application(user_id, app)
    log_action(user_id, app.get('name'), "FORM_SUBMITTED", "Consultation request")
    
    confirmation = f"""✅ *Thank you!* Application accepted.

📋 *Your data:*
👤 {app.get('name', 'N/A')}
📅 {app.get('age', 'N/A')} years
📱 {app.get('telegram', 'N/A')}
📧 {app.get('email', 'N/A')}

🔗 *Zoom link:*
{ZOOM_LINK}

⏰ Manager will contact you within 30 minutes!

Questions? → @it_ai2biz_bot"""
    
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
            <div class="status">✅ ONLINE</div>
            
            <p><strong>Bot:</strong> @it_ai2biz_bot</p>
            <p><strong>Platform:</strong> Render + Supabase</p>
            <p><strong>Connection:</strong> Webhook</p>
            <p><strong>Status:</strong> <strong style="color: #20B8AA;">Live 24/7</strong></p>
            
            <h3>📊 Features:</h3>
            <ul>
                <li>📄 PDF file distribution</li>
                <li>📝 Consultation sign-up form</li>
                <li>💾 Lead database saving</li>
                <li>📊 Action logging</li>
                <li>🔗 Zoom link sending</li>
            </ul>
            
            <div class="info">
                <strong>✅ All set!</strong><br>
                Bot is fully functional and ready to collect leads.
            </div>
        </div>
    </body>
    </html>
    """

# ===== ЗАПУСК ПРИЛОЖЕНИЯ =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Starting bot on port {port}...")
    print(f"🤖 TOKEN: {TOKEN[:20]}...")
    print(f"📍 Webhook: /telegram-webhook")
    print(f"📄 File 1: {FILE_5_MISTAKES[:50]}...")
    print(f"📄 File 2: {FILE_CHECKLIST[:50]}...")
    app.run(host="0.0.0.0", port=port, debug=False)
