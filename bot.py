import os
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
SESSION_TOKEN = os.environ.get("SESSION_TOKEN", "")
WORKSPACE_ID = os.environ.get("WORKSPACE_ID", "3f5319e9-360c-4c01-99ce-41a88f49634e")


def get_access_token(session_token: str) -> str:
    """Session token দিয়ে নতুন access token নাও।"""
    try:
        response = requests.get(
            "https://chatgpt.com/api/auth/session",
            cookies={"__Secure-next-auth.session-token": session_token},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://chatgpt.com/",
            },
            timeout=30
        )
        data = response.json()
        return data.get("accessToken", "")
    except Exception as e:
        logging.error(f"Token refresh error: {e}")
        return ""


def send_invite(email: str, session_token: str, workspace_id: str) -> tuple:
    # প্রতিবার নতুন access token নাও
    access_token = get_access_token(session_token)

    if not access_token:
        return False, "Session token দিয়ে access token নেওয়া যায়নি! `/setsession` দিয়ে নতুন session token দাও।"

    url = f"https://chatgpt.com/backend-api/accounts/{workspace_id}/invites"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
    }

    payload = {
        "email_addresses": [email],
        "resend_emails": True,
        "role": "standard-user",
        "seat_type": "default"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logging.info(f"Status: {response.status_code} | Response: {response.text[:300]}")

        if response.status_code in [200, 201]:
            return True, "Invitation সফলভাবে পাঠানো হয়েছে! ✅"
        elif response.status_code == 401:
            return False, "Session expire হয়েছে! `/setsession` দিয়ে নতুন session token দাও।"
        elif response.status_code == 409:
            return False, "এই email আগেই invite করা হয়েছে!"
        elif response.status_code == 403:
            return False, f"403 Forbidden: {response.text[:100]}"
        else:
            return False, f"Error {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Invitation Bot*\n\n"
        "Client-এর email পাঠাও → Invitation চলে যাবে!\n\n"
        "⚙️ `/setsession TOKEN` - Session token set করো\n"
        "📊 `/status` - Bot status চেক করো",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = context.bot_data.get("session_token", SESSION_TOKEN)
    has_token = "✅ Session token আছে" if token else "❌ Session token নেই"
    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"{has_token}\n"
        f"Workspace: `{WORKSPACE_ID}`",
        parse_mode="Markdown"
    )


async def set_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/setsession YOUR_SESSION_TOKEN`", parse_mode="Markdown")
        return

    token = context.args[0]
    context.bot_data["session_token"] = token
    await update.message.reply_text("✅ Session token update হয়েছে!")


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "@" not in text or "." not in text.split("@")[-1]:
        await update.message.reply_text("❌ Valid email দাও!\nExample: client@gmail.com")
        return

    token = context.bot_data.get("session_token", SESSION_TOKEN)

    if not token:
        await update.message.reply_text(
            "❌ Session token নেই!\n`/setsession YOUR_TOKEN` দিয়ে set করো।",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ `{text}` এ invitation পাঠাচ্ছি...", parse_mode="Markdown")

    success, message = send_invite(text, token, WORKSPACE_ID)

    if success:
        await update.message.reply_text(f"✅ *Done!*\n📧 {text}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ {message}", parse_mode="Markdown")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setsession", set_session))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email))

    print("🤖 Bot চালু হয়েছে!")
    app.run_polling()


if __name__ == "__main__":
    main()
