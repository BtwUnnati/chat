import time, sqlite3, asyncio
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)
from config import BOT_TOKEN, START_PHOTO_URL, SUPPORT_LINK, UPDATES_LINK

DB = "chatbot.db"
spam_users = {}
SUPPORTED_LANGS = {'en': "English", 'hi': "हिन्दी"}
SUPPORTED_GENDERS = {
    'male': {'en': "👦 Male", 'hi': "👦 पुरुष"},
    'female': {'en': "👧 Female", 'hi': "👧 महिला"},
    'other': {'en': "🏳️‍🌈 Other", 'hi': "🏳️‍🌈 अन्य"},
    'unspecified': {'en': "👤 Unspecified", 'hi': "👤 अव्यवस्थित"}
}

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        user_id INTEGER, group_id INTEGER, group_name TEXT, username TEXT, msg_time INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS usersettings (
        user_id INTEGER PRIMARY KEY,
        language TEXT DEFAULT 'en',
        gender TEXT DEFAULT 'unspecified'
    )''')
    conn.commit(); conn.close()

def get_user_lang(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT language FROM usersettings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] in SUPPORTED_LANGS else 'en'

def set_user_lang(user_id, lang):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO usersettings(user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE usersettings SET language=? WHERE user_id=?", (lang, user_id))
    conn.commit(); conn.close()

def get_user_gender(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT gender FROM usersettings WHERE user_id=?", (user_id,))
    row = c.fetchone(); conn.close()
    return row[0] if row and row[0] in SUPPORTED_GENDERS else 'unspecified'

def set_user_gender(user_id, gender):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO usersettings(user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE usersettings SET gender=? WHERE user_id=?", (gender, user_id))
    conn.commit(); conn.close()

def block_check(user_id):
    now = int(time.time())
    return user_id in spam_users and now < spam_users[user_id]

def block_user(user_id, group_id, username, context=None, lang='en'):
    spam_users[user_id] = int(time.time()) + 20*60
    text = {
        'en': f"🚨 {username} is flooding: blocked for 20 minutes for using the bot.",
        'hi': f"🚨 {username} बहुत ज्यादा संदेश भेज रहा है: 20 मिनट के लिए ब्लॉक किया गया।"
    }[lang]
    if context:
        asyncio.create_task(context.bot.send_message(group_id, text))

def count_messages_last(user_id, group_id, seconds=2):
    now = int(time.time())
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND group_id=? AND msg_time>=?", (user_id, group_id, now-seconds))
    count = c.fetchone()[0]
    conn.close(); return count

def add_message(user_id, group_id, group_name, username):
    now = int(time.time())
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO messages(user_id, group_id, group_name, username, msg_time) VALUES (?,?,?,?,?)", (user_id, group_id, group_name, username, now))
    conn.commit(); conn.close()

def get_group_stats_list(user_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    qry = "SELECT group_name, COUNT(*) as mcount FROM messages WHERE user_id=?"
    params = [user_id]
    if since:
        qry += " AND msg_time >= ?"
        params.append(since)
    qry += " GROUP BY group_id ORDER BY mcount DESC"
    c.execute(qry, params)
    data = c.fetchall()
    conn.close()
    return data

def get_leaderboard(group_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    query = "SELECT username, COUNT(*) FROM messages WHERE group_id=?"
    params = [group_id]
    if since:
        query += " AND msg_time >= ?"
        params.append(since)
    query += " GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 10"
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def get_total_group_msgs(group_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    query = "SELECT COUNT(*) FROM messages WHERE group_id=?"
    params = [group_id]
    if since:
        query += " AND msg_time >= ?"
        params.append(since)
    c.execute(query, params)
    total = c.fetchone()[0]
    conn.close()
    return total

def _dt(mode):
    now = datetime.now()
    if mode == 'today':
        return int(datetime(now.year, now.month, now.day).timestamp())
    elif mode == 'week':
        dt = now - timedelta(days=now.weekday())
        return int(datetime(dt.year, dt.month, dt.day).timestamp())
    return None

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

async def safe_send_photo(bot, chat_id, photo, caption, reply_markup):
    for _ in range(3):
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return
        except Exception as e:
            await asyncio.sleep(1)
    # fallback to text
    await bot.send_message(chat_id, caption, reply_markup=reply_markup, parse_mode='HTML')

async def safe_reply_photo(message, photo, caption, reply_markup):
    for _ in range(3):
        try:
            await message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return
        except Exception:
            await asyncio.sleep(1)
    await message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')

async def smart_edit_caption_or_text(query, caption, reply_markup=None, parse_mode=None):
    if getattr(query.message, "photo", None):
        try:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            await query.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await query.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode=parse_mode)

# ---------------- MENU HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    user_id = update.effective_user.id if hasattr(update, 'effective_user') else update.message.from_user.id
    lang = get_user_lang(user_id)
    keyboard = [
        [InlineKeyboardButton("➕ Add me in a group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats_overall")],
        [InlineKeyboardButton("❓ Support", url=SUPPORT_LINK),
         InlineKeyboardButton("🔔 Updates", url=UPDATES_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_reply_photo(update.message, START_PHOTO_URL, T("start_msg", lang), markup)

async def start_callback(cbq, context):
    user_id = cbq.from_user.id
    lang = get_user_lang(user_id)
    keyboard = [
        [InlineKeyboardButton("➕ Add me in a group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats_overall")],
        [InlineKeyboardButton("❓ Support", url=SUPPORT_LINK),
         InlineKeyboardButton("🔔 Updates", url=UPDATES_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await cbq.edit_message_media(
        InputMediaPhoto(START_PHOTO_URL, caption=T("start_msg", lang), parse_mode='HTML'),
        reply_markup=markup
    )

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    keyboard = [
        [InlineKeyboardButton("🌐 Language", callback_data="setlang"),
         InlineKeyboardButton("🧑 Gender", callback_data="gender_menu")],
        [InlineKeyboardButton(T("back", lang), callback_data="back_start")]
    ]
    msg = T("settings", lang)
    await smart_edit_caption_or_text(update.callback_query, msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def setlang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    btns = [[InlineKeyboardButton(v, callback_data="lang_"+k)] for k,v in SUPPORTED_LANGS.items()]
    btns.append([InlineKeyboardButton(T("back", lang), callback_data="settings")])
    msg = T("choose_lang", lang)
    await smart_edit_caption_or_text(update.callback_query, msg, reply_markup=InlineKeyboardMarkup(btns))

async def set_gender_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    btns = [
        [InlineKeyboardButton(SUPPORTED_GENDERS['male'][lang], callback_data="gender_male"),
         InlineKeyboardButton(SUPPORTED_GENDERS['female'][lang], callback_data="gender_female")],
        [InlineKeyboardButton(SUPPORTED_GENDERS['other'][lang], callback_data="gender_other"),
         InlineKeyboardButton(SUPPORTED_GENDERS['unspecified'][lang], callback_data="gender_unspecified")],
        [InlineKeyboardButton(T("back", lang), callback_data="settings")]
    ]
    msg = T("choose_gender", lang)
    await smart_edit_caption_or_text(update.callback_query, msg, reply_markup=InlineKeyboardMarkup(btns))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    user_id = cbq.from_user.id
    code = cbq.data.split("_")[1]
    set_user_lang(user_id, code)
    kb = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats_overall")]
    ]
    msg = T("lang_set", code)
    await smart_edit_caption_or_text(cbq, msg, reply_markup=InlineKeyboardMarkup(kb))

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    user_id = cbq.from_user.id
    code = cbq.data.split("_")[1]
    lang = get_user_lang(user_id)
    set_user_gender(user_id, code)
    kb = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats_overall")]
    ]
    msg = T("gender_set", lang)
    await smart_edit_caption_or_text(cbq, msg, reply_markup=InlineKeyboardMarkup(kb))

def stats_buttons(view):
    btns = [
        [
            InlineKeyboardButton(f"🌟 Overall{' ✅' if view == 'overall' else ''}", callback_data="yourstats_overall"),
            InlineKeyboardButton(f"📆 Today{' ✅' if view == 'today' else ''}", callback_data="yourstats_today"),
        ],
        [InlineKeyboardButton(f"📊 Week{' ✅' if view == 'week' else ''}", callback_data="yourstats_week")],
        [InlineKeyboardButton("Back", callback_data="back_start")]
    ]
    return InlineKeyboardMarkup(btns)

async def stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='overall', query=None):
    user_id = None
    if hasattr(update, 'message') and getattr(update, 'message', None):
        user_id = update.message.from_user.id
    elif getattr(update, "callback_query", None):
        user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    gender = SUPPORTED_GENDERS[get_user_gender(user_id)][lang]
    since = _dt(mode)
    rows = get_group_stats_list(user_id, since)
    msg = f"<b>{T('stats_title', lang)}</b>\n{gender}\n\n"
    if rows:
        for idx, (gname, cnt) in enumerate(rows, 1):
            msg += f"{idx}. 👫 <b>{gname}</b> • {cnt}\n"
    else:
        msg += T("no_data", lang)
    markup = stats_buttons(mode)
    if query:
        await query.edit_message_media(InputMediaPhoto(START_PHOTO_URL, caption=msg, parse_mode='HTML'), reply_markup=markup)
    elif hasattr(update, "message") and update.message:
        await safe_reply_photo(update.message, START_PHOTO_URL, msg, markup)

async def stats_buttons_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "yourstats_overall":
        await stats_menu(update, context, 'overall', query=update.callback_query)
    elif data == "yourstats_today":
        await stats_menu(update, context, 'today', query=update.callback_query)
    elif data == "yourstats_week":
        await stats_menu(update, context, 'week', query=update.callback_query)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='overall', query=None):
    user_id = None
    if hasattr(update, 'effective_user'):
        user_id = update.effective_user.id
    elif hasattr(update, "callback_query") and update.callback_query:
        user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    group_id = None
    if hasattr(update, 'effective_chat'):
        group_id = update.effective_chat.id
    elif hasattr(update, "callback_query") and update.callback_query:
        group_id = update.callback_query.message.chat.id
    since = _dt(mode)
    board = get_leaderboard(group_id, since)
    total = get_total_group_msgs(group_id, since)
    btns = [
        [InlineKeyboardButton(f"🌟 Overall{' ✅' if mode == 'overall' else ''}", callback_data="lb_overall"),
         InlineKeyboardButton(f"📆 Today{' ✅' if mode == 'today' else ''}", callback_data="lb_today")],
        [InlineKeyboardButton(f"📊 Week{' ✅' if mode == 'week' else ''}", callback_data="lb_week")]
    ]
    msg = f"📈 <b>LEADERBOARD</b>\n"
    if board:
        for i, (uname, cnt) in enumerate(board, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            msg += f"{medal} <b>{uname}</b>: {cnt}\n"
    else:
        msg += f"{T('no_data', lang)}\n"
    if mode == 'today':
        msg += f"\n<b>Today messages:</b> {total}"
    elif mode == 'week':
        msg += f"\n<b>Week messages:</b> {total}"
    else:
        msg += f"\n<b>Overall messages:</b> {total}"
    markup = InlineKeyboardMarkup(btns)
    if query:
        await query.edit_message_media(InputMediaPhoto(START_PHOTO_URL, caption=msg, parse_mode='HTML'), reply_markup=markup)
    else:
        await safe_reply_photo(update.message, START_PHOTO_URL, msg, markup)

async def lb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "lb_today":
        await ranking(update, context, mode='today', query=update.callback_query)
    elif data == "lb_week":
        await ranking(update, context, mode='week', query=update.callback_query)
    elif data == "lb_overall":
        await ranking(update, context, mode='overall', query=update.callback_query)

async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ranking(update, context, mode='overall')

async def yourstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stats_menu(update, context, 'overall')

async def mytop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stats_menu(update, context, 'overall')

async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type not in ["supergroup", "group"]:
        return
    group_id = chat.id
    group_name = chat.title or "Private"
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
    add_message(user_id, group_id, group_name, username)

async def inline_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cbq = update.callback_query
    data = cbq.data
    if data == "settings":
        await settings_menu(update, context)
    elif data in ["back", "back_start"]:
        await start_callback(cbq, context)
    elif data == "setlang":
        await setlang_menu(update, context)
    elif data == "gender_menu":
        await set_gender_menu(update, context)
    elif data.startswith("lang_"):
        await set_language(update, context)
    elif data.startswith("gender_"):
        await set_gender(update, context)
    elif data.startswith("yourstats_"):
        await stats_buttons_router(update, context)
    elif data.startswith("lb_"):
        await lb_buttons(update, context)

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("yourstats", yourstats_cmd))
    app.add_handler(CommandHandler("mytop", mytop_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    app.add_handler(CallbackQueryHandler(inline_router))
    print("Bot running. CTRL+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
    
