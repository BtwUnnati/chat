import time
import sqlite3
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)
from config import BOT_TOKEN, START_PHOTO_URL, SUPPORT_LINK, UPDATES_LINK

DB = "chatbot.db"
spam_users = {}
supported_langs = {'en': "English", 'hi': "हिन्दी"}
supported_genders = {
    'male': {'en': "👦 Male", 'hi': "👦 पुरुष"},
    'female': {'en': "👧 Female", 'hi': "👧 महिला"},
    'other': {'en': "🏳️‍🌈 Other", 'hi': "🏳️‍🌈 अन्य"},
    'unspecified': {'en': "👤 Unspecified", 'hi': "👤 अव्यवस्थित"}
}

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        user_id INTEGER, group_id INTEGER, username TEXT, msg_time INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS usersettings (
        user_id INTEGER PRIMARY KEY,
        language TEXT DEFAULT 'en',
        gender TEXT DEFAULT 'unspecified'
    )''')
    conn.commit()
    conn.close()

def get_user_lang(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT language FROM usersettings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] in supported_langs else 'en'

def set_user_lang(user_id, lang):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO usersettings(user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE usersettings SET language=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()

def get_user_gender(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT gender FROM usersettings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] in supported_genders else 'unspecified'

def set_user_gender(user_id, gender):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO usersettings(user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE usersettings SET gender=? WHERE user_id=?", (gender, user_id))
    conn.commit()
    conn.close()

def count_messages_last(user_id, group_id, seconds=2):
    now = int(time.time())
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT msg_time FROM messages WHERE user_id=? AND group_id=? AND msg_time>=?", 
              (user_id, group_id, now-seconds))
    count = len(c.fetchall())
    conn.close()
    return count

def add_message(user_id, group_id, username):
    now = int(time.time())
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages(user_id, group_id, username, msg_time) VALUES (?,?,?,?)", 
        (user_id, group_id, username, now)
    )
    conn.commit()
    conn.close()

def get_leaderboard(group_id, since=0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if since > 0:
        c.execute(
            "SELECT username, COUNT(*) as c FROM messages WHERE group_id=? AND msg_time>? GROUP BY user_id ORDER BY c DESC LIMIT 10", 
            (group_id, since)
        )
    else:
        c.execute(
            "SELECT username, COUNT(*) as c FROM messages WHERE group_id=? GROUP BY user_id ORDER BY c DESC LIMIT 10", 
            (group_id,)
        )
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_msgs(group_id, since=0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if since > 0:
        c.execute("SELECT COUNT(*) FROM messages WHERE group_id=? AND msg_time>?", (group_id, since))
    else:
        c.execute("SELECT COUNT(*) FROM messages WHERE group_id=?", (group_id,))
    val = c.fetchone()[0]
    conn.close()
    return val or 0

def get_user_groups(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT group_id, COUNT(*) as c FROM messages WHERE user_id=? GROUP BY group_id ORDER BY c DESC", 
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def user_stats(user_id, since=0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if since > 0:
        c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND msg_time>?", (user_id, since))
    else:
        c.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,))
    res = c.fetchone()[0]
    conn.close()
    return res or 0

def block_check(user_id):
    now = int(time.time())
    if user_id in spam_users and now < spam_users[user_id]:
        return True
    return False

def block_user(user_id, group_id, username, context=None, lang='en'):
    spam_users[user_id] = int(time.time()) + 20*60
    # Group warning
    text = {
        'en': f"🚨 {username} is flooding: blocked for 20 minutes for using the bot.",
        'hi': f"🚨 {username} बहुत ज्यादा संदेश भेज रहा है: 20 मिनट के लिए ब्लॉक किया गया।"
    }[lang]
    if context:
        context.bot.send_message(group_id, text)

def T(key, lang):
    texts = {
        "start_msg": {
            "en": "💬 Welcome, this bot will count group messages, create rankings and give prizes to users!\n\nBy using this bot, you consent to data processing.",
            "hi": "💬 स्वागत है! यह बोट ग्रुप में भेजे गए मैसेज गिनता है, रैंकिंग बनाता है और यूजर्स को इनाम देता है!\n\nइस बोट के इस्तेमाल से आप डेटा प्रोसेसिंग के लिए सहमत हैं।"
        },
        "settings": {"en": "⚙️ Choose your settings below:", "hi": "⚙️ अपनी सेटिंग्स चुनें:"},
        "choose_lang": {"en": "🌐 Choose language:", "hi": "🌐 भाषा चुनें:"},
        "choose_gender": {"en": "🧑 What's your gender?", "hi": "🧑 अपना लिंग चुनें:"},
        "lang_set": {"en": "✅ Language updated.", "hi": "✅ भाषा अपडेट हो गई।"},
        "gender_set": {"en": "✅ Gender updated.", "hi": "✅ लिंग अपडेट हो गया।"},
        "stats_title": {"en": "YOUR STATS", "hi": "आपकी रैंकिंग"},
        "no_data": {"en": "No data yet.", "hi": "अभी कोई डेटा नहीं।"},
        "spam_warn": {"en": "🚫 You are blocked for spam! Wait 20min.", "hi": "🚫 आपको स्पैम के लिए 20 मिनट तक ब्लॉक किया गया है।"},
        "week": {"en": "This week's stats", "hi": "इस सप्ताह के आँकड़े"},
        "today": {"en": "Today's stats", "hi": "आज के आँकड़े"},
        "overall": {"en": "Overall stats", "hi": "कुल आँकड़े"},
        "back": {"en": "Back", "hi": "वापस"}
    }
    return texts[key][lang]

def _dt(mode):
    now = datetime.now()
    if mode == 'today':
        return int(datetime(now.year, now.month, now.day).timestamp())
    elif mode == 'week':
        dt = now - timedelta(days=now.weekday())
        return int(datetime(dt.year, dt.month, dt.day).timestamp())
    return 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    keyboard = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats")],
        [InlineKeyboardButton("❓ Support", url=SUPPORT_LINK),
         InlineKeyboardButton("🔔 Updates", url=UPDATES_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(
        photo=START_PHOTO_URL,
        caption=T("start_msg", lang),
        reply_markup=markup
    )

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    keyboard = [
        [InlineKeyboardButton("🌐 Language", callback_data="setlang"),
         InlineKeyboardButton("🧑 Gender", callback_data="gender_menu")],
        [InlineKeyboardButton(T("back", lang), callback_data="back")]
    ]
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            T("settings", lang), reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            T("settings", lang), reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def setlang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    btns = [[InlineKeyboardButton(v, callback_data="lang_"+k)] for k,v in supported_langs.items()]
    btns.append([InlineKeyboardButton(T("back", lang), callback_data="settings")])
    await update.callback_query.edit_message_text(
        T("choose_lang", lang), reply_markup=InlineKeyboardMarkup(btns)
    )

async def set_gender_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    btns = [
        [InlineKeyboardButton(supported_genders['male'][lang], callback_data="gender_male"),
         InlineKeyboardButton(supported_genders['female'][lang], callback_data="gender_female")],
        [InlineKeyboardButton(supported_genders['other'][lang], callback_data="gender_other"),
         InlineKeyboardButton(supported_genders['unspecified'][lang], callback_data="gender_unspecified")],
        [InlineKeyboardButton(T("back", lang), callback_data="settings")]
    ]
    await update.callback_query.edit_message_text(
        T("choose_gender", lang), reply_markup=InlineKeyboardMarkup(btns)
    )

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    user_id = cbq.from_user.id
    code = cbq.data.split("_")[1]
    set_user_lang(user_id, code)
    kb = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats")]
    ]
    await cbq.edit_message_text(T("lang_set", code), reply_markup=InlineKeyboardMarkup(kb))

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    user_id = cbq.from_user.id
    code = cbq.data.split("_")[1]
    lang = get_user_lang(user_id)
    set_user_gender(user_id, code)
    kb = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats")]
    ]
    await cbq.edit_message_text(T("gender_set", lang), reply_markup=InlineKeyboardMarkup(kb))

async def stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    gender = supported_genders[get_user_gender(user_id)][lang]
    overall = user_stats(user_id)
    today = user_stats(user_id, since=_dt('today'))
    week = user_stats(user_id, since=_dt('week'))

    msg = (
        f"<b>{T('stats_title', lang)}</b>\n"
        f"{gender}\n"
        f"\n<b>{T('overall', lang)}:</b>\n<i>Messages:</i> {overall}"
        f"\n\n<b>{T('today', lang)}:</b>\n<i>Messages:</i> {today}"
        f"\n\n<b>{T('week', lang)}:</b>\n<i>Messages:</i> {week}"
    )
    kb = [[InlineKeyboardButton(T("back", lang), callback_data="back")]]
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='overall', query=None):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    group_id = update.effective_chat.id

    since = _dt(mode)
    board = get_leaderboard(group_id, since)
    total = get_total_msgs(group_id, since)
    btns = [
        [InlineKeyboardButton("🌟 Overall", callback_data="lb_overall"),
         InlineKeyboardButton("📆 Today", callback_data="lb_today"),
         InlineKeyboardButton("📊 Week", callback_data="lb_week")]
    ]
    text = f"📈 <b>LEADERBOARD</b>\n"
    if board:
        for i, (uname, cnt) in enumerate(board, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} <b>{uname}</b>: {cnt}\n"
    else:
        text += f"{T('no_data', lang)}\n"
    text += f"\n<b>Total messages:</b> {total}"

    markup = InlineKeyboardMarkup(btns)
    if query:
        await query.edit_message_media(
            InputMediaPhoto(START_PHOTO_URL, caption=text, parse_mode='HTML'),
            reply_markup=markup
        )
    else:
        await update.message.reply_photo(
            START_PHOTO_URL, caption=text,
            reply_markup=markup, parse_mode='HTML'
        )

async def lb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "lb_today":
        await ranking(update, context, mode='today', query=query)
    elif query.data == "lb_week":
        await ranking(update, context, mode='week', query=query)
    elif query.data == "lb_overall":
        await ranking(update, context, mode='overall', query=query)

async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ranking(update, context, mode='overall')

async def yourstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    gender = supported_genders[get_user_gender(user_id)][lang]
    overall = user_stats(user_id)
    today = user_stats(user_id, since=_dt('today'))
    week = user_stats(user_id, since=_dt('week'))

    msg = (
        f"<b>{T('stats_title', lang)}</b>\n"
        f"{gender}\n"
        f"\n<b>{T('overall', lang)}:</b>\n<i>Messages:</i> {overall}"
        f"\n\n<b>{T('today', lang)}:</b>\n<i>Messages:</i> {today}"
        f"\n\n<b>{T('week', lang)}:</b>\n<i>Messages:</i> {week}"
    )
    await update.message.reply_text(msg, parse_mode='HTML')

async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    group_id = update.effective_chat.id
    user_id = user.id
    username = user.username or user.first_name
    lang = get_user_lang(user_id)

    if block_check(user_id):
        await update.message.reply_text(T("spam_warn", lang))
        return

    msgc = count_messages_last(user_id, group_id, 2)
    if msgc >= 10:
        block_user(user_id, group_id, username, context, lang)
        return

    add_message(user_id, group_id, username)

async def inline_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    data = cbq.data
    if data == "settings" or data == "back":
        await settings_menu(update, context)
    elif data == "setlang":
        await setlang_menu(update, context)
    elif data == "gender_menu":
        await set_gender_menu(update, context)
    elif data.startswith("lang_"):
        await set_language(update, context)
    elif data.startswith("gender_"):
        await set_gender(update, context)
    elif data == "yourstats":
        await stats_menu(update, context)
    elif data in ["lb_overall", "lb_today", "lb_week"]:
        await lb_buttons(update, context)

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("mytop", yourstats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    app.add_handler(CallbackQueryHandler(inline_router))
    print("Bot running. CTRL+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
                        
