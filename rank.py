import os, time, sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)
from config import BOT_TOKEN, START_PHOTO_URL, SUPPORT_LINK, UPDATES_LINK, OWNER_LINK

DB = "chatbot.db"
LEADERBOARD_IMAGE = "leaderboard_chart.png"
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
        user_id INTEGER,
        name TEXT,
        group_id INTEGER,
        group_name TEXT,
        msg_time INTEGER
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

def add_message(user, group_id, group_name):
    now = int(time.time())
    display_name = (user.full_name or user.first_name or user.username or str(user.id))[:32]
    user_id = user.id
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (user_id, name, group_id, group_name, msg_time) VALUES (?, ?, ?, ?, ?)",
        (user_id, display_name, group_id, group_name, now)
    )
    conn.commit()
    conn.close()

def get_leaderboard(group_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    query = "SELECT user_id, name, COUNT(*) FROM messages WHERE group_id=?"
    params = [group_id]
    if since:
        query += " AND msg_time >= ?"
        params.append(since)
    query += " GROUP BY user_id, name ORDER BY COUNT(*) DESC LIMIT 10"
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def get_total_msgs(group_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    q = "SELECT COUNT(*) FROM messages WHERE group_id=?"
    params = [group_id]
    if since:
        q += " AND msg_time >= ?"
        params.append(since)
    c.execute(q, params)
    tot = c.fetchone()[0]
    conn.close()
    return tot

def get_user_stats_across_groups(user_id, since=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    qry = "SELECT group_name, COUNT(*) FROM messages WHERE user_id=?"
    params = [user_id]
    if since:
        qry += " AND msg_time >= ?"
        params.append(since)
    qry += " GROUP BY group_id ORDER BY COUNT(*) DESC"
    c.execute(qry, params)
    rows = c.fetchall()
    conn.close()
    return rows

def _dt(mode):
    now = datetime.now()
    if mode == 'today':
        return int(datetime(now.year, now.month, now.day).timestamp())
    elif mode == 'week':
        start = now - timedelta(days=now.weekday())
        return int(datetime(start.year, start.month, start.day).timestamp())
    return None

def plot_leaderboard_image(leaders):
    users = [u[1][:11] + ("..." if len(u[1]) > 11 else "") for u in leaders]
    counts = [u[2] for u in leaders]
    plt.figure(figsize=(8, 4.6), dpi=160)
    ax = plt.gca()
    bars = ax.barh(users[::-1], counts[::-1], color='#c94a5a', zorder=3)
    plt.title("LEADERBOARD", fontsize=32, fontweight='bold', color='white', pad=25)
    ax.set_facecolor('#430006')
    plt.gcf().patch.set_facecolor('#430006')
    ax.spines['left'].set_color('white')
    ax.spines['bottom'].set_color('white')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(colors='white', left=False, bottom=False)
    plt.xticks([], [])
    plt.yticks(fontsize=16, color='white', fontweight='bold')
    for bar, count in zip(bars, counts[::-1]):
        plt.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height()/2, str(count),
                 va='center', ha='left', fontsize=15, color='white', fontweight='bold')
    plt.tight_layout(rect=[0,0,1,0.95])
    plt.savefig(LEADERBOARD_IMAGE, bbox_inches='tight', transparent=False)
    plt.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add me in a group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="yourstats_overall")],
        [InlineKeyboardButton("👑 Owner", url=OWNER_LINK)],
        [InlineKeyboardButton("❓ Support", url=SUPPORT_LINK),
         InlineKeyboardButton("🔔 Updates", url=UPDATES_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(
        photo=START_PHOTO_URL,
        caption="💬 Welcome, this bot will count group messages, create rankings and give prizes to users!\n\nBy using this bot, you consent to data processing.",
        reply_markup=markup
    )

async def show_settings(update, lang):
    keyboard = [
        [InlineKeyboardButton("🌐 Language", callback_data="setlang"),
         InlineKeyboardButton("🧑 Gender", callback_data="gender_menu")],
        [InlineKeyboardButton("Back", callback_data="back_start")]
    ]
    msg = "⚙️ Choose your settings below:" if lang == "en" else "⚙️ अपनी सेटिंग्स चुनें:"
    query = getattr(update, "callback_query", None)
    if query:
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_language_menu(update, lang):
    btns = [[InlineKeyboardButton(v, callback_data="lang_"+k)] for k,v in SUPPORTED_LANGS.items()]
    btns.append([InlineKeyboardButton("Back", callback_data="settings")])
    msg = "🌐 Choose language:" if lang == "en" else "🌐 भाषा चुनें:"
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns))

async def set_language(update, lang):
    user_id = update.callback_query.from_user.id
    code = update.callback_query.data.split("_")[1]
    set_user_lang(user_id, code)
    await update.callback_query.edit_message_text("✅ Language updated." if lang == "en" else "✅ भाषा अपडेट हो गई।")

async def show_gender_menu(update, lang):
    btns = [
        [InlineKeyboardButton(SUPPORTED_GENDERS['male'][lang], callback_data="gender_male"),
         InlineKeyboardButton(SUPPORTED_GENDERS['female'][lang], callback_data="gender_female")],
        [InlineKeyboardButton(SUPPORTED_GENDERS['other'][lang], callback_data="gender_other"),
         InlineKeyboardButton(SUPPORTED_GENDERS['unspecified'][lang], callback_data="gender_unspecified")],
        [InlineKeyboardButton("Back", callback_data="settings")]
    ]
    msg = "🧑 What's your gender?" if lang == "en" else "🧑 अपना लिंग चुनें:"
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns))

async def set_gender(update, lang):
    user_id = update.callback_query.from_user.id
    code = update.callback_query.data.split("_")[1]
    set_user_gender(user_id, code)
    await update.callback_query.edit_message_text("✅ Gender updated." if lang == "en" else "✅ लिंग अपडेट हो गया।")

def stats_buttons(tab):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🌟 Overall{' ✅' if tab == 'overall' else ''}", callback_data="yourstats_overall"),
            InlineKeyboardButton(f"📆 Today{' ✅' if tab == 'today' else ''}", callback_data="yourstats_today"),
        ],
        [InlineKeyboardButton(f"📊 Week{' ✅' if tab == 'week' else ''}", callback_data="yourstats_week")],
        [InlineKeyboardButton("Back", callback_data="back_start")]
    ])

async def show_user_stats(update, tab, query=None):
    if hasattr(update, 'message') and update.message:
        user_id = update.message.from_user.id
    else:
        user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    since = _dt(tab) if tab in ["today", "week"] else None
    data = get_user_stats_across_groups(user_id, since)
    gender = SUPPORTED_GENDERS[get_user_gender(user_id)][lang]
    msg = f"<b>YOUR STATS</b>\n{gender}\n\n"
    if data:
        for idx, (gname, cnt) in enumerate(data, 1):
            msg += f"{idx}. 👫 <b>{gname}</b> • {cnt}\n"
    else:
        msg += "No data yet." if lang == "en" else "अभी कोई डेटा नहीं।"
    markup = stats_buttons(tab)
    if query:
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=markup)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='overall', query=None):
    group_id = update.effective_chat.id if hasattr(update, 'effective_chat') else update.callback_query.message.chat.id
    since = _dt(mode)
    board = get_leaderboard(group_id, since)
    total = get_total_msgs(group_id, since)
    btns = [
        [InlineKeyboardButton(f"🌟 Overall{' ✅' if mode == 'overall' else ''}", callback_data="lb_overall"),
         InlineKeyboardButton(f"📆 Today{' ✅' if mode == 'today' else ''}", callback_data="lb_today")],
        [InlineKeyboardButton(f"📊 Week{' ✅' if mode == 'week' else ''}", callback_data="lb_week")]
    ]
    markup = InlineKeyboardMarkup(btns)
    if board:
        plot_leaderboard_image(board)
        caption_lines = []
        for i, (uid, name, cnt) in enumerate(board, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            user_link = f'<a href="tg://user?id={uid}">{name}</a>'
            caption_lines.append(f"{medal} {user_link} • {cnt}")
        msg = "\n".join(caption_lines)
        msg += f"\n\n<b>Total messages:</b> {total}"
    else:
        msg = "<b>LEADERBOARD</b>\nNo data yet.\n\n<b>Total messages:</b> 0"
    if query:
        await query.edit_message_media(media=InputMediaPhoto(open(LEADERBOARD_IMAGE, 'rb'), caption=msg, parse_mode='HTML'), reply_markup=markup)
    else:
        await update.message.reply_photo(photo=open(LEADERBOARD_IMAGE, 'rb'), caption=msg, reply_markup=markup, parse_mode='HTML')

async def lb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "lb_today":
        await ranking(update, context, mode='today', query=q)
    elif q.data == "lb_week":
        await ranking(update, context, mode='week', query=q)
    elif q.data == "lb_overall":
        await ranking(update, context, mode='overall', query=q)

async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ranking(update, context, mode='overall')

async def yourstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_user_stats(update, "overall")

async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type not in ["supergroup", "group"]:
        return
    group_id = chat.id
    group_name = chat.title or "Private"
    add_message(user, group_id, group_name)

async def inline_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    user_id = update.callback_query.from_user.id
    lang = get_user_lang(user_id)
    # Settings and back menu
    if data == "settings":
        await show_settings(update, lang)
    elif data == "setlang":
        await show_language_menu(update, lang)
    elif data.startswith("lang_"):
        await set_language(update, lang)
    elif data == "gender_menu":
        await show_gender_menu(update, lang)
    elif data.startswith("gender_"):
        await set_gender(update, lang)
    elif data == "back_start":
        await start(update.callback_query, context)
    # User stats menu with filters
    elif data.startswith("yourstats_"):
        tab = data.split("_")[1]
        await show_user_stats(update, tab, query=update.callback_query)
    # Leaderboard tabs
    elif data.startswith("lb_"):
        await lb_buttons(update, context)

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("yourstats", yourstats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    app.add_handler(CallbackQueryHandler(inline_router))
    print("Bot running.")
    app.run_polling()

if __name__ == "__main__":
    main()
