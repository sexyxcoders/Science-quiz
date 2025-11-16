from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone
from ..utils.db import COL_USERS
from ..utils.helpers import ensure_user


@Client.on_message(filters.command("start"))
async def start_handler(client, message):
    """Handle /start command."""
    user = await ensure_user(message.from_user)

    welcome_text = (
        "👋 **Welcome to Science Quiz Bot!**\n\n"
        "Test your knowledge in Physics, Chemistry, Biology, Astronomy, and more!\n\n"
        "🎯 *Available Commands:*\n"
        "• `/quiz` — Start a random quiz\n"
        "• `/quiz <category>` — Quiz from specific category\n"
        "• `/categories` — Show all categories\n"
        "• `/myscore` — View your score & stats\n"
        "• `/leaderboard` — Top players list\n"
        "• `/help` — Get help\n\n"
        "Let’s start and see how smart you are! 🧠💡"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎮 Start Quiz", callback_data="start_quiz"),
            ],
            [
                InlineKeyboardButton("📂 Categories", callback_data="show_categories"),
            ],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data="show_leaderboard"),
            ]
        ]
    )

    await message.reply_text(welcome_text, reply_markup=keyboard)
