import sqlite3
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, START_PHOTO_URL, SUPPORT_LINK, UPDATES_LINK

DB = "chatbot.db"
spam_users = {}

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            user_id INTEGER, group_id INTEGER, username TEXT, msg_count INTEGER, 
            msg_time INTEGER, PRIMARY KEY(user_id, group_id, msg_time)
        )
    ''')
    conn.commit()
    conn.close()

def add_msg(user_id, group_id, username):
    now = int(time.time())
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages(user_id, group_id, username, msg_count, msg_time)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, group_id, username, 1, now))
    conn.commit()
    conn.close()

def get_leaderboard(group_id, since):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if since:
        c.execute('''
            SELECT username, SUM(msg_count) as total FROM messages 
            WHERE group_id=? AND msg_time > ?
            GROUP BY user_id ORDER BY total DESC LIMIT 10
        ''', (group_id, since))
    else:
        c.execute('''
            SELECT username, SUM(msg_count) as total FROM messages 
            WHERE group_id=?
            GROUP BY user_id ORDER BY total DESC LIMIT 10
        ''', (group_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_msgs(group_id, since):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if since:
        c.execute('SELECT SUM(msg_count) FROM messages WHERE group_id=? AND msg_time > ?', (group_id, since))
    else:
        c.execute('SELECT SUM(msg_count) FROM messages WHERE group_id=?', (group_id,))
    val = c.fetchone()[0]
    conn.close()
    return val or 0

def get_user_mygroups(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        SELECT group_id, SUM(msg_count) as total FROM messages 
        WHERE user_id=?
        GROUP BY group_id ORDER BY total DESC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🏆 Your stats", callback_data="mystats")],
        [InlineKeyboardButton("❓ Support", url=SUPPORT_LINK),
         InlineKeyboardButton("🔔 Updates", url=UPDATES_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(
        photo=START_PHOTO_URL,
        caption="💬 Welcome, this bot will count group messages, create rankings and give prizes to users!\n\nBy using this bot, you consent to data processing.",
        reply_markup=reply_markup
    )

def block_check(user_id):
    now = int(time.time())
    # Unblock after 20 min
    if user_id in spam_users and now < spam_users[user_id]:
        return True
    return False

def set_block(user_id):
    spam_users[user_id] = int(time.time()) + 20*60

async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    group_id = update.message.chat.id
    user_id = user.id
    username = user.username or user.first_name
    now = int(time.time())

    if block_check(user_id):
        await update.message.reply_text("🚫 You are blocked for spam! Wait 20min.")
        return
    # Last message in group for user within 7s counts as spam
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        SELECT msg_time FROM messages WHERE user_id=? AND group_id=? 
        ORDER BY msg_time DESC LIMIT 1
    ''', (user_id, group_id))
    row = c.fetchone()
    conn.close()
    if row and now - row[0] < 7:
        set_block(user_id)
        await update.message.reply_text("🚫 Spam detected! You are blocked for 20 minutes.")
        return
    add_msg(user_id, group_id, username)

def leaderboard_message(board, total):
    msg = "📈 <b>LEADERBOARD</b>\n"
    for i, (username, count) in enumerate(board, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        msg += f"{medal} <b>{username}</b>: {count}\n"
    msg += f"\n<b>Total messages:</b> {total}"
    return msg

def group_time_value(mode):
    now = datetime.now()
    if mode == 'today':
        dt = datetime(now.year, now.month, now.day)
    elif mode == 'week':
        dt = now - timedelta(days=now.weekday())
        dt = datetime(dt.year, dt.month, dt.day)
    else: # overall
        return 0
    return int(dt.timestamp())

async def rankings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await leaderboard_core(update, context, mode='overall')

async def leaderboard_core(update, context, mode='overall', query=None):
    group_id = update.effective_chat.id
    since = group_time_value(mode)
    leaderboard = get_leaderboard(group_id, since)
    total = get_total_msgs(group_id, since)
    buttons = [
        [InlineKeyboardButton("🌟 Overall", callback_data='lb_overall'),
         InlineKeyboardButton("📆 Today", callback_data='lb_today'),
         InlineKeyboardButton("📊 Week", callback_data='lb_week')]
    ]
    markup = InlineKeyboardMarkup(buttons)
    photo_url = START_PHOTO_URL  # Aap apni custom photo laga sakte hain

    msg_text = "<b>LEADERBOARD</b>\n"
    if leaderboard:
        for i, (username, count) in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            msg_text += f"{medal} <b>{username}</b>: {count}\n"
    else:
        msg_text += "No data yet.\n"
    msg_text += f"\n<b>Total messages:</b> {total}"

    if query:
        await query.edit_message_media(
            InputMediaPhoto(photo_url, caption=msg_text, parse_mode='HTML'),
            reply_markup=markup
        )
    else:
        await update.message.reply_photo(
            photo=photo_url,
            caption=msg_text,
            reply_markup=markup,
            parse_mode='HTML'
        )

async def lb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "lb_today":
        await leaderboard_core(update, context, mode='today', query=query)
    elif data == "lb_week":
        await leaderboard_core(update, context, mode='week', query=query)
    elif data == "lb_overall":
        await leaderboard_core(update, context, mode='overall', query=query)
    else:
        await query.answer()

async def mytop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    rows = get_user_mygroups(user_id)
    msg = "📊 <b>Your Group Rankings</b>\n"
    if rows:
        for gid, total in rows:
            msg += f"Group <code>{gid}</code>: <b>{total}</b> messages\n"
    else:
        msg += "No data yet.\n"
    await update.message.reply_text(msg, parse_mode='HTML')

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Settings (demo, add real settings if needed).")

# Add other commands similarly as needed (topgame, topusers, profile, groupstats, etc.)
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    total = sum([x[1] for x in get_user_mygroups(user_id)])
    await update.message.reply_text(f"👤 Your total chats: <b>{total}</b>", parse_mode='HTML')

async def topusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # For demo purpose, shows global leaderboard
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT username, SUM(msg_count) as total FROM messages GROUP BY user_id ORDER BY total DESC LIMIT 10')
    leaderboard = c.fetchall()
    c.execute('SELECT SUM(msg_count) FROM messages')
    total = c.fetchone()[0] or 0
    conn.close()
    msg = leaderboard_message(leaderboard, total)
    await update.message.reply_text(msg, parse_mode='HTML')

async def groupstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.message.chat.id
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT username, SUM(msg_count) FROM messages WHERE group_id=? GROUP BY user_id', (group_id,))
    data = c.fetchall()
    conn.close()
    msg = "📊 Group Stats:\n"
    for uname, count in data:
        msg += f"{uname}: {count}\n"
    await update.message.reply_text(msg, parse_mode='HTML')

async def mygifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 Your gifts: (Demo, implement as needed)")

async def hangman(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎲 Hangman started (Demo, implement as needed)")

async def stophangman(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛑 Hangman stopped (Demo, implement as needed)")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("")

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rankings", rankings))
    app.add_handler(CommandHandler("mytop", mytop))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("groupstats", groupstats))
    app.add_handler(CommandHandler("mygifts", mygifts))
    app.add_handler(CommandHandler("topusers", topusers))
    app.add_handler(CommandHandler("hangman", hangman))
    app.add_handler(CommandHandler("stophangman", stophangman))
    app.add_handler(CommandHandler("settings", settings))
    # leaderboard with inline buttons
    app.add_handler(CallbackQueryHandler(lb_buttons, pattern="^lb_"))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    print("Bot is running!")
    app.run_polling()
    
if __name__ == "__main__":
    main()
  
