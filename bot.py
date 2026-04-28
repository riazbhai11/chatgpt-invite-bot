import os
import re
import json
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
WORKSPACE_ID = os.environ.get("WORKSPACE_ID", "3f5319e9-360c-4c01-99ce-41a88f49634e")
MAX_MEMBERS = 6


def extract_token(text: str) -> dict:
    result = {}
    try:
        data = json.loads(text)
        if "accessToken" in data:
            result["accessToken"] = data["accessToken"]
        if "account" in data and "id" in data["account"]:
            result["workspaceId"] = data["account"]["id"]
    except:
        at = re.search(r'"accessToken"\s*:\s*"([^"]+)"', text)
        wi = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', text)
        if at:
            result["accessToken"] = at.group(1)
        if wi:
            result["workspaceId"] = wi.group(1)
    return result


def send_invite(email: str, access_token: str, workspace_id: str) -> tuple:
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
            return False, "token_expired"
        elif response.status_code == 409:
            return False, "already_invited"
        elif response.status_code == 403:
            return False, "token_expired"
        else:
            return False, f"Error {response.status_code}: {response.text[:150]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Invitation Bot*\n\n"
        "📧 Client email দাও → Invitation যাবে!\n\n"
        "*Commands:*\n"
        "🔑 `/settoken` - Token update করো\n"
        "🏢 `/setworkspace ID` - নতুন workspace set করো\n"
        "📊 `/status` - Status দেখো\n"
        "🔄 `/reset` - Member count reset করো",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = context.bot_data.get("access_token") or ACCESS_TOKEN
    workspace = context.bot_data.get("workspace_id") or WORKSPACE_ID
    count = context.bot_data.get("member_count", 0)
    has_token = "✅ আছে" if token else "❌ নেই"
    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"Token: {has_token}\n"
        f"Workspace: `{workspace}`\n"
        f"Members: {count}/{MAX_MEMBERS}",
        parse_mode="Markdown"
    )


async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "chatgpt.com/api/auth/session এর পুরো text copy করে দাও:\n`/settoken {text}`",
            parse_mode="Markdown"
        )
        return

    raw = " ".join(context.args)
    tokens = extract_token(raw)

    if tokens.get("accessToken"):
        context.bot_data["access_token"] = tokens["accessToken"]
        if tokens.get("workspaceId"):
            context.bot_data["workspace_id"] = tokens["workspaceId"]
        await update.message.reply_text(
            f"✅ Token set হয়েছে!\n"
            f"Workspace: `{tokens.get('workspaceId', context.bot_data.get('workspace_id', WORKSPACE_ID))}`",
            parse_mode="Markdown"
        )
    elif len(raw) > 100:
        context.bot_data["access_token"] = raw.strip()
        await update.message.reply_text("✅ Token set হয়েছে!")
    else:
        await update.message.reply_text("❌ Token খুঁজে পাইনি! পুরো JSON text দাও।")


async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/setworkspace WORKSPACE_ID`", parse_mode="Markdown")
        return

    workspace_id = context.args[0].strip()
    context.bot_data["workspace_id"] = workspace_id
    context.bot_data["member_count"] = 0
    await update.message.reply_text(
        f"✅ নতুন Workspace set হয়েছে!\n"
        f"ID: `{workspace_id}`\n"
        f"Member count reset হয়েছে।",
        parse_mode="Markdown"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data["member_count"] = 0
    await update.message.reply_text("✅ Member count reset হয়েছে!")


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "@" not in text or "." not in text.split("@")[-1]:
        await update.message.reply_text("❌ Valid email দাও!\nExample: client@gmail.com")
        return

    access_token = context.bot_data.get("access_token") or ACCESS_TOKEN
    workspace = context.bot_data.get("workspace_id") or WORKSPACE_ID
    count = context.bot_data.get("member_count", 0)

    if not access_token:
        await update.message.reply_text(
            "❌ Token নেই!\n`/settoken` দিয়ে token দাও।",
            parse_mode="Markdown"
        )
        return

    # 6 জন হয়ে গেলে warn করো
    if count >= MAX_MEMBERS:
        await update.message.reply_text(
            f"⚠️ এই workspace-এ {MAX_MEMBERS} জন হয়ে গেছে!\n\n"
            f"নতুন workspace বানাও, তারপর:\n"
            f"`/setworkspace NEW_WORKSPACE_ID`\n"
            f"`/settoken NEW_TOKEN`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ `{text}` এ invitation পাঠাচ্ছি...", parse_mode="Markdown")

    success, message = send_invite(text, access_token, workspace)

    if success:
        count += 1
        context.bot_data["member_count"] = count
        remaining = MAX_MEMBERS - count

        reply = f"✅ *Done!*\n📧 {text}\n👥 Members: {count}/{MAX_MEMBERS}"
        if remaining == 0:
            reply += f"\n\n⚠️ *Workspace ভরে গেছে!* নতুন workspace বানাও।"
        elif remaining <= 2:
            reply += f"\n⚠️ মাত্র {remaining} জন বাকি আছে!"

        await update.message.reply_text(reply, parse_mode="Markdown")

    elif message == "token_expired":
        await update.message.reply_text(
            "❌ Token expire হয়েছে!\n\n"
            "chatgpt.com/api/auth/session খোলো → copy করো → `/settoken` দাও।",
            parse_mode="Markdown"
        )
    elif message == "already_invited":
        await update.message.reply_text("⚠️ এই email আগেই invite করা হয়েছে!")
    else:
        await update.message.reply_text(f"❌ {message}", parse_mode="Markdown")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("settoken", set_token))
    app.add_handler(CommandHandler("setworkspace", set_workspace))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email))

    print("🤖 Bot চালু হয়েছে!")
    app.run_polling()


if __name__ == "__main__":
    main()
