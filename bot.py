import os
import re
import json
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
WORKSPACE_ID = os.environ.get("WORKSPACE_ID", "3f5319e9-360c-4c01-99ce-41a88f49634e")


def extract_token(text: str) -> dict:
    """JSON থেকে accessToken এবং sessionToken বের করো।"""
    result = {}
    try:
        data = json.loads(text)
        if "accessToken" in data:
            result["accessToken"] = data["accessToken"]
        if "sessionToken" in data:
            result["sessionToken"] = data["sessionToken"]
        if "account" in data and "id" in data["account"]:
            result["workspaceId"] = data["account"]["id"]
    except:
        # JSON parse না হলে regex দিয়ে try করো
        at = re.search(r'"accessToken"\s*:\s*"([^"]+)"', text)
        st = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', text)
        wi = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', text)
        if at:
            result["accessToken"] = at.group(1)
        if st:
            result["sessionToken"] = st.group(1)
        if wi:
            result["workspaceId"] = wi.group(1)
    return result


def get_access_token_from_session(session_token: str) -> str:
    try:
        response = requests.get(
            "https://chatgpt.com/api/auth/session",
            cookies={"__Secure-next-auth.session-token": session_token},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://chatgpt.com/",
            },
            timeout=30
        )
        data = response.json()
        return data.get("accessToken", "")
    except:
        return ""


def send_invite(email: str, context_data: dict, workspace_id: str) -> tuple:
    # accessToken সরাসরি আছে কিনা দেখো
    access_token = context_data.get("access_token", "")

    # না থাকলে session token দিয়ে নাও
    if not access_token:
        session_token = context_data.get("session_token", "")
        if session_token:
            access_token = get_access_token_from_session(session_token)

    if not access_token:
        return False, "Token নেই! `/settoken` দিয়ে session page-এর পুরো text পাঠাও।"

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
            return True, "✅ Invitation পাঠানো হয়েছে!"
        elif response.status_code == 401:
            return False, "Token expire! আবার `/settoken` দিয়ে নতুন token দাও।"
        elif response.status_code == 409:
            return False, "এই email আগেই invite করা হয়েছে!"
        else:
            return False, f"Error {response.status_code}: {response.text[:150]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Invitation Bot*\n\n"
        "📧 Client email দাও → Invitation যাবে!\n\n"
        "🔑 `/settoken` - Token set করো\n"
        "📊 `/status` - Status দেখো\n\n"
        "*Token set করতে:*\n"
        "chatgpt.com/api/auth/session খোলো → সব text copy করো → `/settoken` দিয়ে paste করো",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    has_token = "✅ আছে" if context.bot_data.get("access_token") or context.bot_data.get("session_token") else "❌ নেই"
    workspace = context.bot_data.get("workspace_id", WORKSPACE_ID)
    await update.message.reply_text(
        f"*Bot Status*\n\nToken: {has_token}\nWorkspace: `{workspace}`",
        parse_mode="Markdown"
    )


async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "chatgpt.com/api/auth/session এর পুরো text copy করে এভাবে দাও:\n`/settoken {পুরো text}`",
            parse_mode="Markdown"
        )
        return

    raw = " ".join(context.args)
    tokens = extract_token(raw)

    if not tokens:
        await update.message.reply_text("❌ Token খুঁজে পাইনি! পুরো JSON text দাও।")
        return

    if "accessToken" in tokens:
        context.bot_data["access_token"] = tokens["accessToken"]
    if "sessionToken" in tokens:
        context.bot_data["session_token"] = tokens["sessionToken"]
    if "workspaceId" in tokens:
        context.bot_data["workspace_id"] = tokens["workspaceId"]

    await update.message.reply_text(
        f"✅ Token set হয়েছে!\n"
        f"Workspace: `{tokens.get('workspaceId', WORKSPACE_ID)}`",
        parse_mode="Markdown"
    )


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "@" not in text or "." not in text.split("@")[-1]:
        await update.message.reply_text("❌ Valid email দাও!\nExample: client@gmail.com")
        return

    workspace = context.bot_data.get("workspace_id", WORKSPACE_ID)

    if not context.bot_data.get("access_token") and not context.bot_data.get("session_token"):
        await update.message.reply_text(
            "❌ Token নেই!\n`/settoken` দিয়ে token দাও।",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ `{text}` এ invitation পাঠাচ্ছি...", parse_mode="Markdown")

    success, message = send_invite(text, context.bot_data, workspace)

    if success:
        await update.message.reply_text(f"✅ *Done!*\n📧 {text}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ {message}", parse_mode="Markdown")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("settoken", set_token))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email))

    print("🤖 Bot চালু হয়েছে!")
    app.run_polling()


if __name__ == "__main__":
    main()
