from os import getenv
from os.path import join, dirname
from dotenv import load_dotenv

# Create .env file path.
dotenv_path = join(dirname(__file__), ".env")

# Load file from the path.
load_dotenv(dotenv_path)

# telegram bot token. Get it here https://t.me/BotFather
API_TOKEN = getenv("API_TOKEN", "")

VK_TOKEN_LINK = getenv("VK_TOKEN_LINK", "")

REDIS_HOST = getenv("REDIS_HOST", "")
REDIS_PORT = int(getenv("REDIS_PORT", ""))
REDIS_PASSWORD = getenv("REDIS_PASSWORD", "")

URL_BASE = 'https://api.telegram.org/file/bot' + API_TOKEN + '/'
LOG_PATH = '/tmp/memstrual.log'

ADMIN_ID = int(getenv("ADMIN_ID", ""))
