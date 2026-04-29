import os
import re
import json
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DEFAULT_WORKSPACE_ID = os.environ.get("WORKSPACE_ID", "")
MAX_MEMBERS = 6


# ─────────────────────────────────────────
# Helper: JSON থেকে token ও workspace বের করো
# ─────────────────────────────────────────
def extract_from_json(text: str) -> dict:
    result = {}
    try:
        data = json.loads(text)
        if "accessToken" in data:
            result["accessToken"] = data["accessToken"]
        if "account" in data and "id" in data["account"]:
            result["workspaceId"] = data["account"]["id"]
    except Exception:
        at = re.search(r'"accessToken"\s*:\s*"([^"]+)"', text)
        wi = re.search(r'"id"\s*:\s*"([a-f0-9\-]{36})"', text)
        if at:
            result["accessToken"] = at.group(1)
        if wi:
            result["workspaceId"] = wi.group(1)
    return result


# ─────────────────────────────────────────
# Invite পাঠানো
# ─────────────────────────────────────────
def send_invite(email: str, access_token: str, workspace_id: str) -> tuple[bool, str]:
    url = f"https://chatgpt.com/backend-api/accounts/{workspace_id}/invites"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Oai-Language": "en-US",
    }

    payload = {
        "email_addresses": [email],
        "resend_emails": True,
        "role": "standard-user",
        "seat_type": "default",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        logging.info(
            f"INVITE | email={email} | status={response.status_code} | body={response.text[:500]}"
        )

        # ── 401 / 403 → token expired ──
        if response.status_code in (401, 403):
            return False, "token_expired"

        # ── 409 → already invited ──
        if response.status_code == 409:
            return False, "already_invited"

        # ── 429 → rate limited ──
        if response.status_code == 429:
            return False, "rate_limited"

        # ── 200 / 201 → parse carefully ──
        if response.status_code in (200, 201):
            body = response.text.strip()

            # Empty body = token সমস্যা
            if not body:
                return False, "token_expired"

            try:
                data = response.json()
            except Exception:
                return False, f"JSON parse error: {body[:100]}"

            # errored_emails চেক
            errored = data.get("errored_emails", [])
            if errored:
                err_msg = errored[0].get("error", "Unknown error")
                # Already member / already invited
                if "already" in err_msg.lower() or "member" in err_msg.lower():
                    return False, "already_invited"
                return False, f"API Error: {err_msg}"

            # সফল invite
            invites = data.get("account_invites", [])
            if isinstance(invites, list) and len(invites) > 0:
                return True, "success"

            # invites list empty কিন্তু error নেই → সম্ভবত সফল
            if "account_invites" in data:
                return False, f"Invite হয়নি (empty list): {body[:150]}"

            # অন্য যেকোনো 200 response
            return True, "success"

        # অন্য status code
        return False, f"Unexpected status {response.status_code}: {response.text[:150]}"

    except requests.exceptions.Timeout:
        return False, "Timeout — সার্ভার সাড়া দেয়নি"
    except requests.exceptions.ConnectionError:
        return False, "Connection error — internet চেক করো"
    except Exception as e:
        return False, f"Error: {str(e)}"


# ─────────────────────────────────────────
# /start
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *ChatGPT Team Invitation Bot*\n\n"
        "📧 Client এর email দাও → Invitation যাবে!\n\n"
        "*Commands:*\n"
        "🔑 `/token` — Token update করো\n"
        "🏢 `/setworkspace ID` — নতুন workspace set করো\n"
        "📊 `/status` — Current status দেখো\n"
        "🔄 `/reset` — Member count reset করো\n"
        "❓ `/help` — সাহায্য",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────
# /help
# ─────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*কিভাবে ব্যবহার করবে:*\n\n"
        "1️⃣ `/token` দাও\n"
        "2️⃣ `chatgpt.com/api/auth/session` খোলো\n"
        "3️⃣ পুরো JSON paste করো\n"
        "4️⃣ `/done` দাও\n"
        "5️⃣ এখন email দাও → invite যাবে!\n\n"
        "⚠️ Token ~24 ঘণ্টা পর expire হয়।\n"
        "Expire হলে আবার `/token` দাও।",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────
# /status
# ─────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    access_token = context.bot_data.get("access_token", "")
    workspace = context.bot_data.get("workspace_id") or DEFAULT_WORKSPACE_ID
    count = context.bot_data.get("member_count", 0)
    token_status = "✅ আছে" if access_token else "❌ নেই"
    remaining = MAX_MEMBERS - count

    await update.message.reply_text(
        f"*📊 Bot Status*\n\n"
        f"🔑 Token: {token_status}\n"
        f"🏢 Workspace: `{workspace or 'সেট করা হয়নি'}`\n"
        f"👥 Members: {count}/{MAX_MEMBERS}\n"
        f"🪑 বাকি Seat: {remaining}",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────
# /token → token collection শুরু
# ─────────────────────────────────────────
async def token_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collecting_token"] = True
    context.user_data["token_parts"] = []
    await update.message.reply_text(
        "🔑 *Token Mode চালু!*\n\n"
        "Browser এ এই URL খোলো:\n"
        "`chatgpt.com/api/auth/session`\n\n"
        "পুরো text copy করে এখানে paste করো।\n"
        "বড় হলে কয়েক ভাগে paste করো।\n"
        "শেষ হলে `/done` দাও।",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────
# /done → token save করো
# ─────────────────────────────────────────
async def token_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("collecting_token"):
        await update.message.reply_text(
            "⚠️ আগে `/token` command দাও!", parse_mode="Markdown"
        )
        return

    parts = context.user_data.get("token_parts", [])
    if not parts:
        await update.message.reply_text("❌ কোনো text পাইনি! আবার `/token` দিয়ে চেষ্টা করো।")
        return

    combined = "".join(parts)
    tokens = extract_from_json(combined)

    context.user_data["collecting_token"] = False
    context.user_data["token_parts"] = []

    if tokens.get("accessToken"):
        context.bot_data["access_token"] = tokens["accessToken"]
        workspace_id = tokens.get("workspaceId") or DEFAULT_WORKSPACE_ID
        if tokens.get("workspaceId"):
            context.bot_data["workspace_id"] = tokens["workspaceId"]

        await update.message.reply_text(
            f"✅ *Token সফলভাবে সেট হয়েছে!*\n\n"
            f"🏢 Workspace: `{workspace_id}`\n\n"
            f"এখন client এর email দাও!",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ *Token খুঁজে পাইনি!*\n\n"
            "নিশ্চিত করো যে `chatgpt.com/api/auth/session` এর পুরো JSON paste করেছো।\n"
            "আবার `/token` দিয়ে চেষ্টা করো।",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────
# /setworkspace
# ─────────────────────────────────────────
async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/setworkspace WORKSPACE_ID`\n\nExample:\n`/setworkspace 3f5319e9-360c-4c01-99ce-41a88f49634e`",
            parse_mode="Markdown",
        )
        return
    workspace_id = context.args[0].strip()
    context.bot_data["workspace_id"] = workspace_id
    context.bot_data["member_count"] = 0
    await update.message.reply_text(
        f"✅ *নতুন Workspace সেট হয়েছে!*\n\n"
        f"🏢 ID: `{workspace_id}`\n"
        f"👥 Count reset হয়েছে।",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────
# /reset
# ─────────────────────────────────────────
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data["member_count"] = 0
    await update.message.reply_text("✅ Member count reset হয়েছে!")


# ─────────────────────────────────────────
# Message handler (email / token parts)
# ─────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # ── Token collection mode ──
    if context.user_data.get("collecting_token"):
        context.user_data["token_parts"].append(text)
        parts_count = len(context.user_data["token_parts"])
        await update.message.reply_text(
            f"✅ Part {parts_count} পেয়েছি!\n"
            f"আরো থাকলে paste করো। শেষ হলে `/done` দাও।",
            parse_mode="Markdown",
        )
        return

    # ── Email validation ──
    email_pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, text):
        await update.message.reply_text(
            "❌ Valid email দাও!\nExample: `client@gmail.com`",
            parse_mode="Markdown",
        )
        return

    # ── Check token ──
    access_token = context.bot_data.get("access_token", "")
    if not access_token:
        await update.message.reply_text(
            "❌ *Token নেই!*\n`/token` দিয়ে আগে token সেট করো।",
            parse_mode="Markdown",
        )
        return

    # ── Check workspace ──
    workspace = context.bot_data.get("workspace_id") or DEFAULT_WORKSPACE_ID
    if not workspace:
        await update.message.reply_text(
            "❌ *Workspace ID নেই!*\n`/setworkspace ID` দিয়ে সেট করো।",
            parse_mode="Markdown",
        )
        return

    # ── Check seat ──
    count = context.bot_data.get("member_count", 0)
    if count >= MAX_MEMBERS:
        await update.message.reply_text(
            f"⚠️ *Workspace ভরে গেছে! ({count}/{MAX_MEMBERS})*\n\n"
            f"নতুন workspace এর জন্য:\n"
            f"1️⃣ `/setworkspace NEW_ID`\n"
            f"2️⃣ `/token` (নতুন token নাও)",
            parse_mode="Markdown",
        )
        return

    # ── Send invite ──
    sending_msg = await update.message.reply_text(
        f"⏳ `{text}` এ invitation পাঠাচ্ছি...",
        parse_mode="Markdown",
    )

    success, message = send_invite(text, access_token, workspace)

    if success:
        count += 1
        context.bot_data["member_count"] = count
        remaining = MAX_MEMBERS - count

        reply = f"✅ *Invitation পাঠানো হয়েছে!*\n📧 {text}\n👥 {count}/{MAX_MEMBERS}"

        if remaining == 0:
            reply += f"\n\n⚠️ *Workspace ভরে গেছে!*\nনতুন workspace বানাও → `/setworkspace`"
        elif remaining <= 2:
            reply += f"\n⚠️ মাত্র *{remaining}* টি seat বাকি!"

        await sending_msg.edit_text(reply, parse_mode="Markdown")

    elif message == "token_expired":
        context.bot_data["access_token"] = ""
        await sending_msg.edit_text(
            "❌ *Token Expire হয়ে গেছে!*\n\n"
            "নতুন token নিতে:\n"
            "1️⃣ `chatgpt.com/api/auth/session` খোলো\n"
            "2️⃣ `/token` দাও\n"
            "3️⃣ JSON paste করো\n"
            "4️⃣ `/done` দাও",
            parse_mode="Markdown",
        )

    elif message == "already_invited":
        await sending_msg.edit_text(
            f"⚠️ *{text}* আগেই invite করা হয়েছে বা workspace member!",
            parse_mode="Markdown",
        )

    elif message == "rate_limited":
        await sending_msg.edit_text(
            "⚠️ *Rate Limited!*\nকিছুক্ষণ পর আবার চেষ্টা করো।",
            parse_mode="Markdown",
        )

    else:
        await sending_msg.edit_text(
            f"❌ *Error:*\n`{message}`\n\nToken expire হলে `/token` দাও।",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN environment variable সেট করা নেই!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("token", token_start))
    app.add_handler(CommandHandler("done", token_done))
    app.add_handler(CommandHandler("setworkspace", set_workspace))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot চালু হয়েছে! Ctrl+C দিয়ে বন্ধ করো।")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
