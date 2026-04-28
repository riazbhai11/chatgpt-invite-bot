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
CHATGPT_SESSION_COOKIE = os.environ.get("CHATGPT_SESSION_COOKIE", "")
MAX_MEMBERS = 6


def get_access_token(session_cookie: str) -> str:
    """Session cookie দিয়ে নতুন access token নাও।"""
    try:
        response = requests.get(
            "https://chatgpt.com/api/auth/session",
            cookies={"__Secure-next-auth.session-token": session_cookie},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://chatgpt.com/",
                "Accept": "application/json",
            },
            timeout=30
        )
        data = response.json()
        token = data.get("accessToken", "")
        workspace = data.get("account", {}).get("id", "")
        return token, workspace
    except Exception as e:
        logging.error(f"Token refresh error: {e}")
        return "", ""


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
        if at:
            result["accessToken"] = at.group(1)
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
            # Check if actually succeeded
            if data.get("errored_emails"):
                error = data["errored_emails"][0].get("error", "Unknown error")
                return False, f"❌ {error}"
            if data.get("account_invites"):
                return True, "success"
            return False, f"Unknown response: {response.text[:100]}"
        elif response.status_code in [401, 403]:
            return False, "token_expired"
        elif response.status_code == 409:
            return False, "already_invited"
        else:
            return False, f"Error {response.status_code}: {response.text[:150]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def get_token(context) -> tuple:
    """Access token এবং workspace নাও — auto refresh সহ।"""
    # ১. bot_data তে আছে?
    access_token = context.bot_data.get("access_token", "")
    workspace = context.bot_data.get("workspace_id", "") or WORKSPACE_ID

    if access_token:
        return access_token, workspace

    # ২. Session cookie দিয়ে refresh করো
    session_cookie = context.bot_data.get("session_cookie", "") or CHATGPT_SESSION_COOKIE
    if session_cookie:
        token, ws = get_access_token(session_cookie)
        if token:
            context.bot_data["access_token"] = token
            if ws:
                context.bot_data["workspace_id"] = ws
                workspace = ws
            return token, workspace

    return "", workspace


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Invitation Bot*\n\n"
        "📧 Client email দাও → Invitation যাবে!\n\n"
        "*Commands:*\n"
        "🔑 `/settoken` - Mobile থেকে token দাও\n"
        "🍪 `/setcookie` - PC থেকে session cookie দাও\n"
        "🏢 `/setworkspace ID` - নতুন workspace\n"
        "📊 `/status` - Status দেখো\n"
        "🔄 `/reset` - Count reset করো",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_cookie = context.bot_data.get("session_cookie", "") or CHATGPT_SESSION_COOKIE
    access_token = context.bot_data.get("access_token", "")
    workspace = context.bot_data.get("workspace_id", "") or WORKSPACE_ID
    count = context.bot_data.get("member_count", 0)

    cookie_status = "✅ আছে (auto refresh)" if session_cookie else "❌ নেই"
    token_status = "✅ আছে" if access_token else "❌ নেই"

    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"🍪 Session Cookie: {cookie_status}\n"
        f"🔑 Access Token: {token_status}\n"
        f"🏢 Workspace: `{workspace}`\n"
        f"👥 Members: {count}/{MAX_MEMBERS}",
        parse_mode="Markdown"
    )


async def set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "PC-তে DevTools → Application → Cookies → chatgpt.com\n"
            "`__Secure-next-auth.session-token` এর value copy করো:\n"
            "`/setcookie VALUE`",
            parse_mode="Markdown"
        )
        return
    cookie = " ".join(context.args).strip()
    context.bot_data["session_cookie"] = cookie
    context.bot_data["access_token"] = ""  # Force refresh

    # Test করো
    token, ws = get_access_token(cookie)
    if token:
        context.bot_data["access_token"] = token
        if ws:
            context.bot_data["workspace_id"] = ws
        await update.message.reply_text(
            f"✅ Session cookie set হয়েছে!\n"
            f"Auto token refresh চালু!\n"
            f"Workspace: `{ws or WORKSPACE_ID}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ Cookie দেওয়া হয়েছে কিন্তু token নেওয়া যায়নি। Cookie ঠিক আছে তো?")


async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/settoken {session page এর text}`", parse_mode="Markdown")
        return

    raw = " ".join(context.args)
    tokens = extract_from_json(raw)

    if tokens.get("accessToken"):
        context.bot_data["access_token"] = tokens["accessToken"]
        if tokens.get("workspaceId"):
            context.bot_data["workspace_id"] = tokens["workspaceId"]
        await update.message.reply_text("✅ Token set হয়েছে!")
    elif len(raw) > 100:
        context.bot_data["access_token"] = raw.strip()
        await update.message.reply_text("✅ Token set হয়েছে!")
    else:
        await update.message.reply_text("❌ Token খুঁজে পাইনি!")


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


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "@" not in text or "." not in text.split("@")[-1]:
        await update.message.reply_text("❌ Valid email দাও!\nExample: client@gmail.com")
        return

    count = context.bot_data.get("member_count", 0)

    if count >= MAX_MEMBERS:
        await update.message.reply_text(
            f"⚠️ Workspace ভরে গেছে! ({MAX_MEMBERS}/{MAX_MEMBERS})\n\n"
            f"নতুন workspace বানাও:\n"
            f"1️⃣ `/setworkspace NEW_ID`\n"
            f"2️⃣ `/settoken` বা `/setcookie`",
            parse_mode="Markdown"
        )
        return

    access_token, workspace = get_token(context)

    if not access_token:
        await update.message.reply_text(
            "❌ Token নেই!\n\n"
            "Mobile: chatgpt.com/api/auth/session → copy → `/settoken`\n"
            "PC: `/setcookie` দিয়ে session cookie দাও",
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
        # Auto refresh try করো
        context.bot_data["access_token"] = ""
        access_token, workspace = get_token(context)
        if access_token:
            success2, message2 = send_invite(text, access_token, workspace)
            if success2:
                count += 1
                context.bot_data["member_count"] = count
                await update.message.reply_text(f"✅ *Done!* (token auto refresh)\n📧 {text}\n👥 {count}/{MAX_MEMBERS}", parse_mode="Markdown")
                return
        await update.message.reply_text(
            "❌ Token expire!\n\nMobile: chatgpt.com/api/auth/session → `/settoken`",
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
    app.add_handler(CommandHandler("setcookie", set_cookie))
    app.add_handler(CommandHandler("setworkspace", set_workspace))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email))

    print("🤖 Bot চালু হয়েছে!")
    app.run_polling()


if __name__ == "__main__":
    main()
