import os
import random
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Add only your Telegram ID and your girlfriend's Telegram ID here.
# First run the bot and use /myid to get your IDs.
ALLOWED_USER_IDS = {
    # 123456789,
    # 987654321,
}

# Optional: limit the bot to one private group.
# Keep empty at the beginning. Use /myid inside the group to get chat_id.
ALLOWED_CHAT_IDS = {
    # -1001234567890,
}

CARDS_FOLDER = Path("cards")
DATABASE_FILE = "game.db"
CURRENT_ROUNDS = {}


def init_db() -> None:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            card_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            round_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_vote(chat_id: int, user_id: int, username: str, card_name: str, score: int, round_id: str) -> None:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO votes (chat_id, user_id, username, card_name, score, round_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            user_id,
            username or "Unknown",
            card_name,
            score,
            round_id,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def get_score_summary(chat_id: int):
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT card_name, COUNT(*) as votes_count, ROUND(AVG(score), 2) as avg_score
        FROM votes
        WHERE chat_id = ?
        GROUP BY card_name
        ORDER BY avg_score DESC, votes_count DESC
        """,
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def reset_scores(chat_id: int) -> None:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM votes WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def is_allowed_user(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS


def is_allowed_chat(chat_id: int) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


async def check_access(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return False

    if not is_allowed_chat(chat.id):
        if update.message:
            await update.message.reply_text("This bot is not allowed in this chat.")
        return False

    if not is_allowed_user(user.id):
        if update.message:
            await update.message.reply_text(
                "Private access. Use /myid, then add your Telegram ID inside ALLOWED_USER_IDS in bot.py."
            )
        return False

    return True


def get_random_card():
    if not CARDS_FOLDER.exists():
        return None

    valid_extensions = [".png", ".jpg", ".jpeg", ".webp"]
    cards = [file for file in CARDS_FOLDER.iterdir() if file.suffix.lower() in valid_extensions]
    if not cards:
        return None

    return random.choice(cards)


def build_score_keyboard(round_id: str) -> InlineKeyboardMarkup:
    row_1 = [InlineKeyboardButton(str(i), callback_data=f"vote:{round_id}:{i}") for i in range(1, 6)]
    row_2 = [InlineKeyboardButton(str(i), callback_data=f"vote:{round_id}:{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row_1, row_2])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to your private priority game.\n\n"
        "Commands:\n"
        "/myid - get your Telegram user ID and chat ID\n"
        "/new - send a random card\n"
        "/score - show the ranking\n"
        "/reset - delete scores for this chat\n\n"
        "Setup: add your ID and your girlfriend's ID in ALLOWED_USER_IDS."
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(
        f"User ID: {user.id}\n"
        f"Username: @{user.username if user.username else 'no_username'}\n"
        f"Chat ID: {chat.id}\n\n"
        "Copy your User ID into ALLOWED_USER_IDS."
    )


async def new_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return

    chat = update.effective_chat
    card = get_random_card()

    if card is None:
        await update.message.reply_text("No images found. Add images into the cards folder.")
        return

    round_id = uuid.uuid4().hex[:8]
    CURRENT_ROUNDS[round_id] = {"chat_id": chat.id, "card_name": card.name, "votes": {}}

    caption = (
        "🎲 New random card\n\n"
        f"Card: {card.stem}\n\n"
        "Choose a priority from 1 to 10."
    )

    with open(card, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=photo,
            caption=caption,
            reply_markup=build_score_keyboard(round_id),
        )


async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    await query.answer()

    if not is_allowed_chat(chat.id):
        await query.answer("This bot is not allowed in this chat.", show_alert=True)
        return

    if not is_allowed_user(user.id):
        await query.answer("Private access. You are not allowed to play.", show_alert=True)
        return

    try:
        _, round_id, score_text = query.data.split(":")
        score = int(score_text)
    except ValueError:
        await query.answer("Invalid button.", show_alert=True)
        return

    if round_id not in CURRENT_ROUNDS:
        await query.answer("This round is no longer active. Use /new.", show_alert=True)
        return

    round_data = CURRENT_ROUNDS[round_id]

    if user.id in round_data["votes"]:
        await query.answer("You have already voted for this card.", show_alert=True)
        return

    username = user.username or user.first_name or "Unknown"
    round_data["votes"][user.id] = {"username": username, "score": score}

    save_vote(
        chat_id=chat.id,
        user_id=user.id,
        username=username,
        card_name=round_data["card_name"],
        score=score,
        round_id=round_id,
    )

    votes_text = "".join([f"- {vote['username']}: {vote['score']}/10\n" for vote in round_data["votes"].values()])

    caption = (
        "✅ Vote saved\n\n"
        f"Card: {round_data['card_name']}\n\n"
        f"Current votes:\n{votes_text}\n"
        "Use /new for another card."
    )

    await query.edit_message_caption(caption=caption, reply_markup=build_score_keyboard(round_id))


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return

    rows = get_score_summary(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("No score saved yet.")
        return

    text = "🏆 General ranking:\n\n"
    for index, row in enumerate(rows, start=1):
        card_name, votes_count, avg_score = row
        text += f"{index}. {card_name}\n   Average: {avg_score}/10 | Votes: {votes_count}\n\n"

    await update.message.reply_text(text)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    reset_scores(update.effective_chat.id)
    await update.message.reply_text("Scores deleted for this chat.")


def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing. Create a .env file based on .env.example.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("new", new_card))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(handle_vote, pattern=r"^vote:"))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
