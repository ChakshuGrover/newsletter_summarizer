import os
import logging
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path, override=True)

# API Keys
GEMINI_API_KEY_1 = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")
API_KEYS = [key for key in [GEMINI_API_KEY_1, GEMINI_API_KEY_2] if key]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File Paths
SECRET_FILE = "credentials.json"
TOKEN_PICKLE_FILE = 'token.pickle'
HISTORY_FILE = 'top_stories_history.json'
LOG_FILE = 'newsletter_summarizer.log'
LAST_RUN_FILE = 'last_run_date.txt'
ARCHIVE_DIR = 'archives'

# Gmail Settings
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]
EXPECTED_EMAIL = "chakshugrover.newsletters@gmail.com"
RECIPIENT_EMAILS = [
    "chakshu.grover8@gmail.com",
    "karansinghkjs346@gmail.com",
    "shah.harshil1102@gmail.com",
    "anjistic@gmail.com",
]


# Logging Setup
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=LOG_FILE
    )
