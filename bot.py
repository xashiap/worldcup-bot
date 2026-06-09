import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import sqlite3
from datetime import datetime

# ===== تنظیمات =====
TOKEN = "8476684193:AAHzd_PU7mKpsmX1EvjxNUQI9c6yX5zJMvU"
ADMIN_ID = 6595586966  # آیدی عددی تلگرام خودت

# ===== دیتابیس =====
def init_db():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT, team2 TEXT,
        date TEXT, result TEXT DEFAULT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, username TEXT,
        match_id INTEGER, prediction TEXT,
        UNIQUE(user_id, match_id)
    )''')
    conn.commit()
    conn.close()

def get_matches():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches ORDER BY date")
    matches = c.fetchall()
    conn.close()
    return matches

def get_user_prediction(user_id, match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT prediction FROM predictions WHERE user_id=? AND match_id=?", (user_id, match_id))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_prediction(user_id, username, match_id, prediction):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''INSERT INTO predictions (user_id, username, match_id, prediction)
                 VALUES (?,?,?,?)
                 ON CONFLICT(user_id, match_id) DO UPDATE SET prediction=?''',
              (user_id, username, match_id, prediction, prediction))
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''
        SELECT p.username, COUNT(*) as score
        FROM predictions p
        JOIN matches m ON p.match_id = m.id
        WHERE m.result IS NOT NULL AND p.prediction = m.result
        GROUP BY p.user_id
        ORDER BY score DESC
        LIMIT 10
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def add_match_db(team1, team2, date):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("INSERT INTO matches (team1, team2, date) VALUES (?,?,?)", (team1, team2, date))
    conn.commit()
    conn.close()

def set_result_db(match_id, result):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("UPDATE matches SET result=? WHERE id=?", (result, match_id))
    conn.commit()
    conn.close()

# ===== دستورات کاربر =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ به ربات پیش‌بینی جام جهانی ۲۰۲۶ خوش اومدی!\n\n"
        "📋 /matches — لیست بازی‌ها و پیش‌بینی\n"
        "🏆 /score — جدول امتیازات"
    )

async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matches = get_matches()
    if not matches:
        await update.message.reply_text("هنوز بازی‌ای ثبت نشده.")
        return
    for m in matches:
        mid, team1, team2, date, result = m
        user_pred = get_user_prediction(update.effective_user.id, mid)
        status = f"پیش‌بینی تو: {user_pred}" if user_pred else "هنوز پیش‌بینی نکردی"
        if result:
            status += f" | نتیجه: {result}"
        keyboard = [
            [
                InlineKeyboardButton(f"🏅 {team1}", callback_data=f"pred_{mid}_{team1}"),
                InlineKeyboardButton("🤝 مساوی", callback_data=f"pred_{mid}_draw"),
                InlineKeyboardButton(f"🏅 {team2}", callback_data=f"pred_{mid}_{team2}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚽ {team1} vs {team2}\n📅 {date}\n{status}",
            reply_markup=reply_markup if not result else None
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_", 2)
    match_id = int(data[1])
    prediction = data[2]
    user = query.from_user
    save_prediction(user.id, user.username or user.first_name, match_id, prediction)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ پیش‌بینی‌ات ثبت شد: {prediction}")

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    board = get_leaderboard()
    if not board:
        await update.message.reply_text("هنوز امتیازی ثبت نشده.")
        return
    text = "🏆 جدول امتیازات:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, pts) in enumerate(board):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} {username} — {pts} امتیاز\n"
    await update.message.reply_text(text)

# ===== دستورات ادمین =====
async def add_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # فرمت: /addmatch ایران|آمریکا|2026-06-15
    try:
        parts = " ".join(context.args).split("|")
        add_match_db(parts[0].strip(), parts[1].strip(), parts[2].strip())
        await update.message.reply_text(f"✅ بازی {parts[0]} vs {parts[1]} اضافه شد.")
    except:
        await update.message.reply_text("فرمت: /addmatch تیم۱|تیم۲|تاریخ")

async def set_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # فرمت: /setresult 1|ایران
    try:
        parts = " ".join(context.args).split("|")
        set_result_db(int(parts[0].strip()), parts[1].strip())
        await update.message.reply_text(f"✅ نتیجه بازی {parts[0]} ثبت شد.")
    except:
        await update.message.reply_text("فرمت: /setresult شماره_بازی|برنده")

# ===== اجرا =====
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("matches", matches))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("addmatch", add_match))
    app.add_handler(CommandHandler("setresult", set_result))
    app.add_handler(CallbackQueryHandler(button))
    print("✅ بات شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()