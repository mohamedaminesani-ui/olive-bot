# Telegram Priority Game

Private Telegram game for two people. The bot sends a random image card, then each allowed player chooses a priority from 1 to 10 using buttons.

## 1. Create your Telegram bot

1. Open Telegram.
2. Search for `@BotFather`.
3. Send `/newbot`.
4. Choose a name and a username ending with `bot`.
5. Copy the token.

## 2. Install the project

```bash
git clone https://github.com/mohamedaminesani-ui/olive-bot.git
cd olive-bot/telegram-priority-game
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 3. Configure the token

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

On Windows, you can also create `.env` manually.

Inside `.env`, add your BotFather token:

```env
BOT_TOKEN=YOUR_REAL_TOKEN_HERE
```

Never share this token publicly.

## 4. Get your Telegram IDs

Run the bot:

```bash
python bot.py
```

Open the bot in Telegram and send:

```text
/myid
```

Ask the second player to do the same. Then open `bot.py` and add both IDs:

```python
ALLOWED_USER_IDS = {
    123456789,
    987654321,
}
```

Restart the bot.

## 5. Add images

Put your images inside the `cards` folder.

Accepted formats:

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

Examples:

```text
cards/voyage.png
cards/restaurant.png
cards/cadeau.png
cards/weekend.png
```

## 6. Commands

| Command | Function |
|---|---|
| `/start` | Show help |
| `/myid` | Show your Telegram user ID and chat ID |
| `/new` | Send a random card |
| `/score` | Show ranking by average score |
| `/reset` | Delete scores for the current chat |

## 7. Play in a private group

Create a private Telegram group with only the two players and the bot.

Inside the group, send:

```text
/myid
```

Copy the Chat ID into `ALLOWED_CHAT_IDS` if you want to restrict the bot to that group only.

```python
ALLOWED_CHAT_IDS = {
    -1001234567890,
}
```

## Important

This bot runs locally while your computer is on. For 24/7 use, deploy it on a VPS or a hosting platform.
