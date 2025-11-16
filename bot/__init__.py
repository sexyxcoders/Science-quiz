import os
from dotenv import load_dotenv
from pyrogram import Client
from pymongo import MongoClient

# Load environment variables
load_dotenv()

# ----- Telegram Bot Config -----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# ----- MongoDB -----
MONGO_URI = os.getenv("MONGO_URI")
mongo = MongoClient(MONGO_URI)
db = mongo["science_quiz_bot"]

# Collections
users_col = db["users"]
questions_col = db["questions"]
attempts_col = db["attempts"]

# ----- Pyrogram Bot Client -----
app = Client(
    name="science-quiz-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    in_memory=False
)