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
MAX_MEMBERS = 6


def extract_from_json(text: str) -> dict:
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
            data = response.json()
            if data.get("errored_emails"):
                error = data["errored_emails"][0].get("error", "Unknown error")
                return False, f"❌ {error}"
            if data.get("account_invites"):
                return True, "success"
            return False, f"Unknown: {response.text[:100]}"
        elif response.status_code in [401, 403]:
            return False, "token_expired"
        elif response.status_code == 409:
            return False, "already_invited"
        else:
            return False, f"Error {response.status_code}: {response.text[:150]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Invitation Bot*\n\n"
        "📧 Client email দাও → Invitation যাবে!\n\n"
        "*Commands:*\n"
        "🔑 `/token` - Token update করো\n"
        "🏢 `/setworkspace ID` - নতুন workspace\n"
        "📊 `/status` - Status দেখো\n"
        "🔄 `/reset` - Count reset করো",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    access_token = context.bot_data.get("access_token", "")
    workspace = context.bot_data.get("workspace_id", "") or WORKSPACE_ID
    count = context.bot_data.get("member_count", 0)
    token_status = "✅ আছে" if access_token else "❌ নেই"
    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"🔑 Token: {token_status}\n"
        f"🏢 Workspace: `{workspace}`\n"
        f"👥 Members: {count}/{MAX_MEMBERS}",
        parse_mode="Markdown"
    )


async def token_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Token collection mode শুরু করো।"""
    context.user_data["collecting_token"] = True
    context.user_data["token_parts"] = []
    await update.message.reply_text(
        "🔑 *Token Mode চালু!*\n\n"
        "এখন chatgpt.com/api/auth/session এর পুরো text paste করো।\n"
        "২ ভাগে আসলেও চলবে — সব parts আসার পর `/done` দাও।",
        parse_mode="Markdown"
    )


async def token_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Token collection শেষ করো।"""
    if not context.user_data.get("collecting_token"):
        await update.message.reply_text("আগে `/token` দাও!", parse_mode="Markdown")
        return

    parts = context.user_data.get("token_parts", [])
    if not parts:
        await update.message.reply_text("❌ কোনো text পাইনি! আবার `/token` দিয়ে শুরু করো।")
        return

    combined = "".join(parts)
    tokens = extract_from_json(combined)

    context.user_data["collecting_token"] = False
    context.user_data["token_parts"] = []

    if tokens.get("accessToken"):
        context.bot_data["access_token"] = tokens["accessToken"]
        if tokens.get("workspaceId"):
            context.bot_data["workspace_id"] = tokens["workspaceId"]
        await update.message.reply_text(
            f"✅ *Token set হয়েছে!*\n"
            f"Workspace: `{tokens.get('workspaceId', context.bot_data.get('workspace_id', WORKSPACE_ID))}`\n\n"
            f"এখন email দাও!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Token খুঁজে পাইনি!\n"
            "chatgpt.com/api/auth/session এর পুরো text দিয়েছ তো?\n"
            "আবার `/token` দিয়ে try করো।"
        )


async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/setworkspace WORKSPACE_ID`", parse_mode="Markdown")
        return
    workspace_id = context.args[0].strip()
    context.bot_data["workspace_id"] = workspace_id
    context.bot_data["member_count"] = 0
    await update.message.reply_text(
        f"✅ নতুন Workspace set!\nID: `{workspace_id}`\nCount reset হয়েছে।",
        parse_mode="Markdown"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data["member_count"] = 0
    await update.message.reply_text("✅ Member count reset হয়েছে!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Token collection mode চলছে?
    if context.user_data.get("collecting_token"):
        context.user_data["token_parts"].append(text)
        parts_count = len(context.user_data["token_parts"])
        await update.message.reply_text(
            f"✅ Part {parts_count} পেয়েছি!\n"
            f"আরো আছে? paste করো। শেষ হলে `/done` দাও।",
            parse_mode="Markdown"
        )
        return

    # Email check
    if "@" not in text or "." not in text.split("@")[-1]:
        await update.message.reply_text("❌ Valid email দাও!\nExample: client@gmail.com")
        return

    count = context.bot_data.get("member_count", 0)
    access_token = context.bot_data.get("access_token", "")
    workspace = context.bot_data.get("workspace_id", "") or WORKSPACE_ID

    if count >= MAX_MEMBERS:
        await update.message.reply_text(
            f"⚠️ Workspace ভরে গেছে! ({MAX_MEMBERS}/{MAX_MEMBERS})\n\n"
            f"নতুন workspace বানাও:\n"
            f"1️⃣ `/setworkspace NEW_ID`\n"
            f"2️⃣ `/token`",
            parse_mode="Markdown"
        )
        return

    if not access_token:
        await update.message.reply_text(
            "❌ Token নেই!\n`/token` দিয়ে token দাও।",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ `{text}` এ invitation পাঠাচ্ছি...", parse_mode="Markdown")

    success, message = send_invite(text, access_token, workspace)

    if success:
        count += 1
        context.bot_data["member_count"] = count
        remaining = MAX_MEMBERS - count

        reply = f"✅ *Done!*\n📧 {text}\n👥 {count}/{MAX_MEMBERS}"
        if remaining == 0:
            reply += f"\n\n⚠️ *Workspace ভরে গেছে!* নতুন workspace বানাও।"
        elif remaining <= 2:
            reply += f"\n⚠️ মাত্র {remaining} জন বাকি!"

        await update.message.reply_text(reply, parse_mode="Markdown")

    elif message == "token_expired":
        context.bot_data["access_token"] = ""
        await update.message.reply_text(
            "❌ Token expire!\n`/token` দিয়ে নতুন token দাও।",
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
    app.add_handler(CommandHandler("token", token_start))
    app.add_handler(CommandHandler("done", token_done))
    app.add_handler(CommandHandler("setworkspace", set_workspace))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot চালু হয়েছে!")
    app.run_polling()


if __name__ == "__main__":
    main()
