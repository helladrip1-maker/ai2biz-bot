#!/usr/bin/env python3
import os
import logging
from dotenv import load_dotenv
from main import check_pending_messages, init_google_sheets

# Настройка логирования для скрипта
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("check_pending")

def run():
    load_dotenv()
    logger.info("🚀 Starting check_pending script...")
    
    # Инициализируем соединение с таблицами
    # В main.py google_sheets и scheduler — глобальные переменные
    # Но так как мы запускаем как отдельный скрипт, импортируем функции
    
    # В main.py scheduler создается на уровне модуля. 
    # Когда мы импортируем check_pending_messages из main, инициализируется все, что на уровне модуля.
    
    check_pending_messages()
    logger.info("✅ Check pending completed")

if __name__ == "__main__":
    run()
