import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8080))
