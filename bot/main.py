# bot/main.py
"""
Science Quiz Bot - Async Pyrogram + Motor (MongoDB)
Features:
- /start, /quiz [category], /categories, /myscore, /leaderboard
- pending_questions workflow with expiry and ownership checks
- MCQ/TF (options + answer_index) and short-answer
- stores users, questions, attempts, pending_questions in MongoDB

Environment variables (use .env):
BOT_TOKEN, API_ID, API_HASH, MONGO_URI, MONGO_DB, QUESTION_TIME_LIMIT
"""
import os
import json
import time
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bson import ObjectId

load_dotenv()

# -------------------------
# Config
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "quizbot")
QUESTION_TIME_LIMIT = int(os.getenv("QUESTION_TIME_LIMIT", "20"))

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("science_quiz_bot")

# Pyrogram client
app = Client("science_quiz_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Motor client (async)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[MONGO_DB]
COL_USERS = db.users
COL_QUESTIONS = db.questions
COL_PENDING = db.pending_questions
COL_ATTEMPTS = db.attempts
COL_CATEGORIES = db.categories

# -------------------------
# Helpers
# -------------------------
def now_ts() -> int:
    return int(time.time())

def iso_now():
    return datetime.now(timezone.utc)

async def ensure_indexes():
    # run once at startup
    try:
        await COL_USERS.create_index("tg_id", unique=True)
        await COL_QUESTIONS.create_index([("category", 1)])
        await COL_PENDING.create_index([("tg_user_id", 1), ("used", 1), ("expire_at", 1)])
        # text index for admin search
        try:
            await COL_QUESTIONS.create_index([("text", "text")])
        except Exception:
            pass
        logger.info("Indexes ensured")
    except Exception as e:
        logger.exception("Error ensuring indexes: %s", e)

async def ensure_user(tg_user):
    """Return user document; create if missing."""
    if not tg_user:
        return None
    doc = await COL_USERS.find_one({"tg_id": tg_user.id})
    if doc:
        return doc
    new = {
        "tg_id": tg_user.id,
        "username": getattr(tg_user, "username", "") or "",
        "first_name": getattr(tg_user, "first_name", "") or "",
        "last_name": getattr(tg_user, "last_name", "") or "",
        "score": 0,
        "plays": 0,
        "last_play": None,
        "created_at": iso_now()
    }
    res = await COL_USERS.insert_one(new)
    return await COL_USERS.find_one({"_id": res.inserted_id})

def build_options_keyboard(options, pending_id):
    """options: list[str]; pending_id: ObjectId"""
    buttons = []
    for i, opt in enumerate(options):
        cb = f"p|{str(pending_id)}|{i}"
        buttons.append([InlineKeyboardButton(f"{i+1}. {opt}", callback_data=cb)])
    return InlineKeyboardMarkup(buttons)

# -------------------------
# Commands / Handlers
# -------------------------
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await ensure_user(message.from_user)
    text = (
        "👋 Welcome to the Science Quiz Bot!\n\n"
        "Commands:\n"
        "/quiz - start a random quiz\n"
        "/quiz <category> - quiz from category\n"
        "/categories - list categories\n"
        "/myscore - your score\n"
        "/leaderboard - top players\n"
    )
    await message.reply_text(text)

@app.on_message(filters.command("categories"))
async def categories_handler(client, message):
    cats = await COL_CATEGORIES.find().sort("name", 1).to_list(length=1000)
    if not cats:
        await message.reply_text("No categories available. Add some via admin panel.")
        return
    lines = []
    for c in cats:
        lines.append(f"- {c.get('name')} ({str(c.get('_id'))})")
    await message.reply_text("Categories:\n" + "\n".join(lines))

@app.on_message(filters.command("myscore"))
async def myscore_handler(client, message):
    await ensure_user(message.from_user)
    user = await COL_USERS.find_one({"tg_id": message.from_user.id})
    if not user:
        await message.reply_text("User record not found.")
        return
    await message.reply_text(f"Your score: {user.get('score',0)} points\nPlays: {user.get('plays',0)}")

@app.on_message(filters.command("leaderboard"))
async def leaderboard_handler(client, message):
    rows = await COL_USERS.find().sort("score", -1).limit(10).to_list(length=10)
    if not rows:
        await message.reply_text("No scores yet.")
        return
    txt = "🏆 Leaderboard\n\n"
    for i, r in enumerate(rows, start=1):
        name = r.get("username") or r.get("first_name") or "User"
        txt += f"{i}. {name} — {r.get('score',0)} pts\n"
    await message.reply_text(txt)

@app.on_message(filters.command("quiz"))
async def quiz_handler(client, message):
    # ensure user
    await ensure_user(message.from_user)
    parts = message.text.strip().split(maxsplit=1)
    category = None
    if len(parts) > 1:
        category = parts[1].strip()
    query = {}
    if category:
        query["category"] = category
    count = await COL_QUESTIONS.count_documents(query)
    if count == 0:
        await message.reply_text("No questions available for that category." if category else "No questions available.")
        return
    import random
    skip = random.randrange(count)
    docs = await COL_QUESTIONS.find(query).skip(skip).limit(1).to_list(length=1)
    if not docs:
        await message.reply_text("Failed to fetch a question. Try again.")
        return
    q = docs[0]
    options = q.get("options", []) or []
    q_text = q.get("text") or q.get("q_text") or q.get("question") or "Question text missing."

    # create pending question
    now = now_ts()
    expire = now + QUESTION_TIME_LIMIT
    pending_doc = {
        "chat_id": message.chat.id,
        "tg_user_id": message.from_user.id,
        "question_id": q["_id"],
        "message_id": None,
        "created_at": now,
        "expire_at": expire,
        "used": False
    }
    res = await COL_PENDING.insert_one(pending_doc)
    pending_id = res.inserted_id

    if q.get("q_type", "mcq") in ("mcq", "tf"):
        kb = build_options_keyboard(options, pending_id)
        sent = await message.reply_text(f"❓ {q_text}\nYou have {QUESTION_TIME_LIMIT} seconds to answer.", reply_markup=kb)
        await COL_PENDING.update_one({"_id": pending_id}, {"$set": {"message_id": sent.message_id}})
    else:
        sent = await message.reply_text(f"❓ {q_text}\nReply with your answer (short). You have {QUESTION_TIME_LIMIT} seconds.")
        await COL_PENDING.update_one({"_id": pending_id}, {"$set": {"message_id": sent.message_id}})

    # update user plays/last_play
    await COL_USERS.update_one({"tg_id": message.from_user.id},
                               {"$inc": {"plays": 1}, "$set": {"last_play": iso_now()}},
                               upsert=True)

@app.on_callback_query()
async def callback_handler(client, callback_query):
    data = (callback_query.data or "")
    if not data.startswith("p|"):
        # ignore other callbacks here
        return

    parts = data.split("|")
    if len(parts) != 3:
        await callback_query.answer("Invalid callback.", show_alert=True)
        return

    try:
        pending_oid = ObjectId(parts[1])
        chosen_index = int(parts[2])
    except Exception:
        await callback_query.answer("Invalid data.", show_alert=True)
        return

    pending = await COL_PENDING.find_one({"_id": pending_oid})
    if not pending:
        await callback_query.answer("This question is no longer available.", show_alert=True)
        return

    # ownership check
    if pending.get("tg_user_id") != callback_query.from_user.id:
        await callback_query.answer("This question was requested by another user.", show_alert=True)
        return

    # used check
    if pending.get("used"):
        await callback_query.answer("This question was already answered.", show_alert=True)
        return

    # expiry check
    if now_ts() > pending.get("expire_at", 0):
        await COL_PENDING.update_one({"_id": pending_oid}, {"$set": {"used": True}})
        await callback_query.answer("Time's up!", show_alert=True)
        await callback_query.message.reply_text("⏱️ Time's up — you didn't answer in time.")
        return

    q = await COL_QUESTIONS.find_one({"_id": pending["question_id"]})
    if not q:
        await callback_query.answer("Question missing.", show_alert=True)
        await COL_PENDING.update_one({"_id": pending_oid}, {"$set": {"used": True}})
        return

    correct = False
    if q.get("q_type", "mcq") in ("mcq", "tf"):
        correct_index = q.get("answer_index")
        try:
            if correct_index is not None and int(correct_index) == chosen_index:
                correct = True
        except Exception:
            correct = False

    points = 10 if correct else 0

    # ensure user document and persist attempt
    user = await COL_USERS.find_one({"tg_id": callback_query.from_user.id})
    if not user:
        user = await ensure_user(callback_query.from_user)

    attempt = {
        "user_id": user["_id"],
        "question_id": q["_id"],
        "chosen_answer": chosen_index,
        "correct": bool(correct),
        "points": points,
        "created_at": iso_now()
    }
    await COL_ATTEMPTS.insert_one(attempt)
    if points:
        await COL_USERS.update_one({"_id": user["_id"]}, {"$inc": {"score": points}})

    # mark pending used
    await COL_PENDING.update_one({"_id": pending_oid}, {"$set": {"used": True}})

    resp_text = "✅ Correct!" if correct else "❌ Incorrect."
    explanation = q.get("explanation", "") or ""
    await callback_query.answer(resp_text, show_alert=True)
    await callback_query.message.reply_text(f"{resp_text}\n\n{explanation}")

@app.on_message(filters.private & ~filters.command)
async def short_answer_handler(client, message):
    # handle short-answer questions by matching latest pending short question for the user
    now = now_ts()
    pending = await COL_PENDING.find_one(
        {"tg_user_id": message.from_user.id, "used": False, "expire_at": {"$gte": now}},
        sort=[("created_at", -1)]
    )
    if not pending:
        return  # nothing to do

    q = await COL_QUESTIONS.find_one({"_id": pending["question_id"]})
    if not q or q.get("q_type") != "short":
        return

    user = await ensure_user(message.from_user)
    given = message.text.strip()
    correct = False
    try:
        answer_text = (q.get("answer_text") or "").strip().lower()
        correct = (given.strip().lower() == answer_text)
    except Exception:
        correct = False

    points = 10 if correct else 0

    attempt = {
        "user_id": user["_id"],
        "question_id": q["_id"],
        "chosen_answer": given,
        "correct": bool(correct),
        "points": points,
        "created_at": iso_now()
    }
    await COL_ATTEMPTS.insert_one(attempt)
    if points:
        await COL_USERS.update_one({"_id": user["_id"]}, {"$inc": {"score": points}})

    await COL_PENDING.update_one({"_id": pending["_id"]}, {"$set": {"used": True}})

    if correct:
        await message.reply_text("✅ Correct!")
    else:
        await message.reply_text(f"❌ Incorrect. Answer: {q.get('answer_text','(no answer)')}")

# -------------------------
# Startup
# -------------------------
if __name__ == "__main__":
    import asyncio
    # ensure indexes before starting
    asyncio.get_event_loop().run_until_complete(ensure_indexes())
    logger.info("Starting Science Quiz Bot...")
    app.run()
