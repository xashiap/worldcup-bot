import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# States
(REGISTER_NATIONAL_ID, REGISTER_NAME,
 MAIN_MENU, PREDICT_ROUND, PREDICT_MATCH, PREDICT_GOAL1, PREDICT_GOAL2) = range(7)

# ===== DB =====
def init_db():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        national_id TEXT UNIQUE,
        full_name TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT, team2 TEXT,
        date TEXT, round INTEGER,
        goal1 INTEGER DEFAULT NULL,
        goal2 INTEGER DEFAULT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, match_id INTEGER,
        pred_goal1 INTEGER, pred_goal2 INTEGER,
        points INTEGER DEFAULT NULL,
        UNIQUE(user_id, match_id)
    )''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def register_user(user_id, national_id, full_name):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, national_id, full_name) VALUES (?,?,?)",
                  (user_id, national_id, full_name))
        conn.commit()
        result = True
    except:
        result = False
    conn.close()
    return result

def get_matches_by_round(round_num):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE round=? ORDER BY date", (round_num,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_match(match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE id=?", (match_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_prediction(user_id, match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM predictions WHERE user_id=? AND match_id=?", (user_id, match_id))
    row = c.fetchone()
    conn.close()
    return row

def save_prediction(user_id, match_id, g1, g2):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''INSERT INTO predictions (user_id, match_id, pred_goal1, pred_goal2)
                 VALUES (?,?,?,?)
                 ON CONFLICT(user_id, match_id) DO UPDATE SET pred_goal1=?, pred_goal2=?, points=NULL''',
              (user_id, match_id, g1, g2, g1, g2))
    conn.commit()
    conn.close()

def add_match_db(team1, team2, date, round_num):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("INSERT INTO matches (team1, team2, date, round) VALUES (?,?,?,?)",
              (team1, team2, date, round_num))
    conn.commit()
    conn.close()

def calc_points(pg1, pg2, rg1, rg2):
    if pg1 == rg1 and pg2 == rg2:
        return 10
    pd = pg1 - pg2
    rd = rg1 - rg2
    if pd == rd:
        return 7
    pw = (pg1 > pg2) - (pg1 < pg2)
    rw = (rg1 > rg2) - (rg1 < rg2)
    if pw == rw:
        return 5
    return 2

def set_result_db(match_id, g1, g2):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("UPDATE matches SET goal1=?, goal2=? WHERE id=?", (g1, g2, match_id))
    c.execute("SELECT user_id, pred_goal1, pred_goal2 FROM predictions WHERE match_id=?", (match_id,))
    preds = c.fetchall()
    for (uid, pg1, pg2) in preds:
        pts = calc_points(pg1, pg2, g1, g2)
        c.execute("UPDATE predictions SET points=? WHERE user_id=? AND match_id=?", (pts, uid, match_id))
    conn.commit()
    conn.close()

def get_leaderboard(user_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT u.full_name, u.national_id, COALESCE(SUM(p.points),0) as score
                 FROM users u LEFT JOIN predictions p ON u.user_id=p.user_id
                 GROUP BY u.user_id ORDER BY score DESC LIMIT 5''')
    top5 = c.fetchall()
    c.execute('''SELECT u.full_name, u.national_id, COALESCE(SUM(p.points),0) as score,
                 (SELECT COUNT(*)+1 FROM users u2
                  LEFT JOIN predictions p2 ON u2.user_id=p2.user_id
                  GROUP BY u2.user_id
                  HAVING COALESCE(SUM(p2.points),0) > COALESCE(SUM(p.points),0)) as rank
                 FROM users u LEFT JOIN predictions p ON u.user_id=p.user_id
                 WHERE u.user_id=?
                 GROUP BY u.user_id''', (user_id,))
    my_row = c.fetchone()
    conn.close()
    return top5, my_row

# ===== Keyboards =====
def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("⚽ شروع پیش‌بینی"), KeyboardButton("🏆 امتیازات")]],
        resize_keyboard=True
    )

def round_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("دور اول"), KeyboardButton("دور دوم")],
         [KeyboardButton("دور سوم"), KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True
    )

def goals_keyboard():
    rows = []
    row = []
    for i in range(1, 11):
        row.append(KeyboardButton(str(i)))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"👋 خوش برگشتی {user[2]}!",
            reply_markup=main_keyboard()
        )
        return MAIN_MENU
    await update.message.reply_text(
        "👋 سلام! به ربات پیش‌بینی جام جهانی ۲۰۲۶ خوش اومدی!\n\n"
        "لطفاً کد ملی ۱۰ رقمی خودت رو وارد کن:",
        reply_markup=ReplyKeyboardRemove()
    )
    return REGISTER_NATIONAL_ID

async def get_national_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nid = update.message.text.strip()
    if not nid.isdigit() or len(nid) != 10:
        await update.message.reply_text("❌ کد ملی باید ۱۰ رقم باشه. دوباره وارد کن:")
        return REGISTER_NATIONAL_ID
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE national_id=?", (nid,))
    exists = c.fetchone()
    conn.close()
    if exists:
        await update.message.reply_text("❌ این کد ملی قبلاً ثبت شده.")
        return REGISTER_NATIONAL_ID
    context.user_data['national_id'] = nid
    await update.message.reply_text("✅ حالا نام و نام خانوادگی کامل خودت رو وارد کن:")
    return REGISTER_NAME

async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ نام معتبر نیست. دوباره وارد کن:")
        return REGISTER_NAME
    nid = context.user_data['national_id']
    success = register_user(update.effective_user.id, nid, name)
    if success:
        await update.message.reply_text(
            f"✅ ثبت‌نام موفق!\nخوش اومدی {name} 🎉",
            reply_markup=main_keyboard()
        )
        return MAIN_MENU
    else:
        await update.message.reply_text("❌ خطا در ثبت‌نام. دوباره /start بزن.")
        return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⚽ شروع پیش‌بینی":
        await update.message.reply_text("کدوم دور؟", reply_markup=round_keyboard())
        return PREDICT_ROUND
    elif text == "🏆 امتیازات":
        top5, my_row = get_leaderboard(update.effective_user.id)
        msg = "🏆 جدول امتیازات:\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (name, nid, score) in enumerate(top5):
            last4 = nid[-4:]
            msg += f"{medals[i]} {name} ({last4}) — {score} امتیاز\n"
        if my_row:
            my_name, my_nid, my_score = my_row[0], my_row[1], my_row[2]
            msg += f"\n\n👤 امتیاز تو: {my_score} امتیاز"
        await update.message.reply_text(msg, reply_markup=main_keyboard())
        return MAIN_MENU
    return MAIN_MENU

async def predict_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("منوی اصلی:", reply_markup=main_keyboard())
        return MAIN_MENU
    round_map = {"دور اول": 1, "دور دوم": 2, "دور سوم": 3}
    if text not in round_map:
        await update.message.reply_text("یکی از دورها رو انتخاب کن:", reply_markup=round_keyboard())
        return PREDICT_ROUND
    round_num = round_map[text]
    context.user_data['round'] = round_num
    matches = get_matches_by_round(round_num)
    if not matches:
        await update.message.reply_text("هنوز بازی‌ای برای این دور ثبت نشده.", reply_markup=round_keyboard())
        return PREDICT_ROUND
    context.user_data['matches'] = matches
    context.user_data['match_index'] = 0
    return await show_match(update, context)

async def show_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matches = context.user_data['matches']
    idx = context.user_data['match_index']
    if idx >= len(matches):
        await update.message.reply_text("✅ پیش‌بینی همه بازی‌ها ثبت شد!", reply_markup=main_keyboard())
        return MAIN_MENU
    match = matches[idx]
    mid, team1, team2, date, round_num, g1, g2 = match
    context.user_data['current_match'] = match
    pred = get_prediction(update.effective_user.id, mid)
    status = ""
    if pred:
        status = f"\n📝 پیش‌بینی قبلی تو: {team1} {pred[3]} - {pred[4]} {team2}"
    if g1 is not None:
        status += f"\n✅ نتیجه: {team1} {g1} - {g2} {team2}"
        context.user_data['match_index'] += 1
        return await show_match(update, context)
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("⏭ رد کردن"), KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        f"⚽ بازی {idx+1} از {len(matches)}\n"
        f"📅 {date}\n"
        f"🆚 {team1} vs {team2}{status}\n\n"
        f"گل‌های {team1} چنده؟ (۱ تا ۱۰)",
        reply_markup=goals_keyboard()
    )
    return PREDICT_GOAL1

async def predict_goal1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("کدوم دور؟", reply_markup=round_keyboard())
        return PREDICT_ROUND
    if text == "⏭ رد کردن":
        context.user_data['match_index'] += 1
        return await show_match(update, context)
    if not text.isdigit() or not (1 <= int(text) <= 10):
        await update.message.reply_text("❌ عدد ۱ تا ۱۰ وارد کن:")
        return PREDICT_GOAL1
    context.user_data['pred_goal1'] = int(text)
    match = context.user_data['current_match']
    team2 = match[2]
    await update.message.reply_text(
        f"گل‌های {team2} چنده؟ (۱ تا ۱۰)",
        reply_markup=goals_keyboard()
    )
    return PREDICT_GOAL2

async def predict_goal2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or not (1 <= int(text) <= 10):
        await update.message.reply_text("❌ عدد ۱ تا ۱۰ وارد کن:")
        return PREDICT_GOAL2
    g2 = int(text)
    g1 = context.user_data['pred_goal1']
    match = context.user_data['current_match']
    mid, team1, team2 = match[0], match[1], match[2]
    save_prediction(update.effective_user.id, mid, g1, g2)
    await update.message.reply_text(f"✅ ثبت شد: {team1} {g1} - {g2} {team2}")
    context.user_data['match_index'] += 1
    return await show_match(update, context)

# ===== Admin =====
async def add_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        parts = " ".join(context.args).split("|")
        add_match_db(parts[0].strip(), parts[1].strip(), parts[2].strip(), int(parts[3].strip()))
        await update.message.reply_text(f"✅ بازی {parts[0]} vs {parts[1]} دور {parts[3]} اضافه شد.")
    except:
        await update.message.reply_text("فرمت: /addmatch تیم۱|تیم۲|تاریخ|دور")

async def set_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        parts = " ".join(context.args).split("|")
        set_result_db(int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip()))
        await update.message.reply_text(f"✅ نتیجه بازی {parts[0]} ثبت شد.")
    except:
        await update.message.reply_text("فرمت: /setresult شماره|گل_تیم۱|گل_تیم۲")

# ===== Main =====
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_national_id)],
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
            PREDICT_ROUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_round)],
            PREDICT_GOAL1: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_goal1)],
            PREDICT_GOAL2: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_goal2)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("addmatch", add_match))
    app.add_handler(CommandHandler("setresult", set_result))

    print("✅ بات شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()
