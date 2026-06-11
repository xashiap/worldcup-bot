import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

RULES_TEXT = """📜 قوانین مسابقه پیش‌بینی جام جهانی ۲۰۲۶

👤 ثبت‌نام
هر نفر فقط با یک کد ملی می‌تونه شرکت کنه.

⚽ پیش‌بینی
قبل از شروع هر بازی می‌تونی نتیجه دقیق رو پیش‌بینی کنی.
بعد از قفل شدن بازی دیگه امکان پیش‌بینی وجود نداره.

🎯 امتیازدهی

🥇 پیش‌بینی دقیق نتیجه — ۱۰ امتیاز
مثال: نتیجه واقعی ایران ۲ - آمریکا ۱ / پیش‌بینی تو: ایران ۲ - آمریکا ۱

🥈 تفاضل گل درست — ۷ امتیاز
مثال: نتیجه واقعی ایران ۳ - آمریکا ۱ / پیش‌بینی تو: ایران ۲ - آمریکا ۰ (تفاضل هر دو ۲ تاست)

🥉 پیش‌بینی تیم برنده یا تساوی — ۵ امتیاز
مثال: نتیجه واقعی ایران ۳ - آمریکا ۱ / پیش‌بینی تو: ایران ۵ - آمریکا ۲ (برنده رو درست گفتی)

✅ شرکت در پیش‌بینی — ۲ امتیاز
مثال: نتیجه واقعی ایران ۲ - آمریکا ۰ / پیش‌بینی تو: آمریکا ۱ - ایران ۰ (کلاً اشتباه ولی شرکت کردی)

🏆 جدول امتیازات
امتیازات هر دور و امتیاز کل به صورت جداگانه نمایش داده میشه."""

# States
(REGISTER_NATIONAL_ID, REGISTER_PHONE, REGISTER_NAME,
 MAIN_MENU, PREDICT_ROUND, PREDICT_KNOCKOUT,
 PREDICT_MATCH_SELECT, PREDICT_GOAL1, PREDICT_GOAL2,
 RESET_CONFIRM, BROADCAST_MSG) = range(11)

ROUND_MAP = {
    "دور اول": 1, "دور دوم": 2, "دور سوم": 3,
    "یک شانزدهم نهایی": 4, "یک هشتم نهایی": 5,
    "یک چهارم نهایی": 6, "نیمه نهایی": 7, "فینال و رده‌بندی": 8
}

ROUND_NAMES = {v: k for k, v in ROUND_MAP.items()}

# ===== DB =====
def init_db():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        national_id TEXT UNIQUE,
        phone TEXT,
        full_name TEXT
    )''')
    # Add phone column if not exists (for existing DBs)
    try:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT, team2 TEXT,
        date TEXT, round INTEGER,
        goal1 INTEGER DEFAULT NULL,
        goal2 INTEGER DEFAULT NULL,
        locked INTEGER DEFAULT 0
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

def get_all_user_ids():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def national_id_exists(nid):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE national_id=?", (nid,))
    row = c.fetchone()
    conn.close()
    return row is not None

def register_user(user_id, national_id, phone, full_name):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, national_id, phone, full_name) VALUES (?,?,?,?)",
                  (user_id, national_id, phone, full_name))
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

def delete_match_db(match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("DELETE FROM predictions WHERE match_id=?", (match_id,))
    c.execute("DELETE FROM matches WHERE id=?", (match_id,))
    conn.commit()
    conn.close()

def lock_match_db(match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("UPDATE matches SET locked=1 WHERE id=?", (match_id,))
    conn.commit()
    conn.close()

def unlock_match_db(match_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("UPDATE matches SET locked=0 WHERE id=?", (match_id,))
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
    c.execute("UPDATE matches SET goal1=?, goal2=?, locked=1 WHERE id=?", (g1, g2, match_id))
    c.execute("SELECT user_id, pred_goal1, pred_goal2 FROM predictions WHERE match_id=?", (match_id,))
    preds = c.fetchall()
    for (uid, pg1, pg2) in preds:
        pts = calc_points(pg1, pg2, g1, g2)
        c.execute("UPDATE predictions SET points=? WHERE user_id=? AND match_id=?", (pts, uid, match_id))
    conn.commit()
    conn.close()

def reset_all_db():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("DELETE FROM predictions")
    c.execute("UPDATE matches SET goal1=NULL, goal2=NULL, locked=0")
    conn.commit()
    conn.close()

def get_leaderboard_by_round(round_num):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT u.full_name, u.national_id, COALESCE(SUM(p.points),0) as score
                 FROM users u
                 JOIN predictions p ON u.user_id=p.user_id
                 JOIN matches m ON p.match_id=m.id
                 WHERE m.round=? AND p.points IS NOT NULL AND p.points > 0
                 GROUP BY u.user_id
                 ORDER BY score DESC LIMIT 5''', (round_num,))
    top5 = c.fetchall()
    conn.close()
    return top5

def get_user_score_by_round(user_id, round_num):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT COALESCE(SUM(p.points),0)
                 FROM predictions p
                 JOIN matches m ON p.match_id=m.id
                 WHERE p.user_id=? AND m.round=? AND p.points IS NOT NULL''', (user_id, round_num))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_leaderboard_knockout():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT u.full_name, u.national_id, COALESCE(SUM(p.points),0) as score
                 FROM users u
                 JOIN predictions p ON u.user_id=p.user_id
                 JOIN matches m ON p.match_id=m.id
                 WHERE m.round IN (4,5,6,7,8) AND p.points IS NOT NULL AND p.points > 0
                 GROUP BY u.user_id
                 ORDER BY score DESC LIMIT 5''')
    top5 = c.fetchall()
    conn.close()
    return top5

def get_user_score_knockout(user_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT COALESCE(SUM(p.points),0)
                 FROM predictions p
                 JOIN matches m ON p.match_id=m.id
                 WHERE p.user_id=? AND m.round IN (4,5,6,7,8) AND p.points IS NOT NULL''', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_leaderboard_total():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT u.full_name, u.national_id, COALESCE(SUM(p.points),0) as score
                 FROM users u
                 JOIN predictions p ON u.user_id=p.user_id
                 WHERE p.points IS NOT NULL AND p.points > 0
                 GROUP BY u.user_id
                 ORDER BY score DESC LIMIT 5''')
    top5 = c.fetchall()
    conn.close()
    return top5

def get_user_total_score(user_id):
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT COALESCE(SUM(points),0) FROM predictions
                 WHERE user_id=? AND points IS NOT NULL''', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_all_users_full():
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute('''SELECT u.user_id, u.national_id, u.phone, u.full_name, COALESCE(SUM(p.points),0) as score
                 FROM users u
                 LEFT JOIN predictions p ON u.user_id=p.user_id AND p.points IS NOT NULL
                 GROUP BY u.user_id
                 ORDER BY score DESC''')
    rows = c.fetchall()
    conn.close()
    return rows

# ===== Keyboards =====
def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("⚽ شروع پیش‌بینی"), KeyboardButton("🏆 امتیازات")],
         [KeyboardButton("📜 قوانین")]],
        resize_keyboard=True
    )

def round_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("دور اول"), KeyboardButton("دور دوم"), KeyboardButton("دور سوم")],
         [KeyboardButton("مراحل حذفی"), KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True
    )

def knockout_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("یک شانزدهم نهایی"), KeyboardButton("یک هشتم نهایی")],
         [KeyboardButton("یک چهارم نهایی"), KeyboardButton("نیمه نهایی")],
         [KeyboardButton("فینال و رده‌بندی"), KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True
    )

def goals_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("0"), KeyboardButton("1"), KeyboardButton("2"),
          KeyboardButton("3"), KeyboardButton("4")],
         [KeyboardButton("5"), KeyboardButton("6"), KeyboardButton("7"),
          KeyboardButton("8"), KeyboardButton("9")],
         [KeyboardButton("10"), KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True
    )

def matches_keyboard(matches, user_id):
    buttons = []
    for m in matches:
        mid, team1, team2, date, round_num, g1, g2, locked = m
        pred = get_prediction(user_id, mid)
        label = f"{team1} vs {team2}"
        if pred:
            label += " ✅"
        if locked or g1 is not None:
            label += " 🔒"
        buttons.append([KeyboardButton(label)])
    buttons.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"👋 خوش برگشتی {user[3]}!",
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
    if national_id_exists(nid):
        await update.message.reply_text("❌ این کد ملی قبلاً ثبت شده. کد دیگه‌ای وارد کن:")
        return REGISTER_NATIONAL_ID
    context.user_data['national_id'] = nid
    await update.message.reply_text(
        "✅ کد ملی ثبت شد.\n\n"
        "📱 شماره موبایل خودت رو وارد کن:\n"
        "(برای هماهنگی دریافت جایزه)"
    )
    return REGISTER_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 11 or not phone.startswith("09"):
        await update.message.reply_text("❌ شماره موبایل باید ۱۱ رقم و با ۰۹ شروع بشه. دوباره وارد کن:")
        return REGISTER_PHONE
    context.user_data['phone'] = phone
    await update.message.reply_text("✅ حالا نام و نام خانوادگی کامل خودت رو وارد کن:")
    return REGISTER_NAME

async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ نام معتبر نیست. دوباره وارد کن:")
        return REGISTER_NAME
    nid = context.user_data['national_id']
    phone = context.user_data['phone']
    success = register_user(update.effective_user.id, nid, phone, name)
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

    elif text == "📜 قوانین":
        await update.message.reply_text(RULES_TEXT, reply_markup=main_keyboard())
        return MAIN_MENU

    elif text == "🏆 امتیازات":
        user_id = update.effective_user.id
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        msg = ""

        # دورهای گروهی
        for rnum, rname in [(1, "دور اول"), (2, "دور دوم"), (3, "دور سوم")]:
            top = get_leaderboard_by_round(rnum)
            my_score = get_user_score_by_round(user_id, rnum)
            if not top and my_score == 0:
                continue
            msg += f"⚽ {rname}:\n"
            if top:
                for i, (name, nid, score) in enumerate(top):
                    msg += f"{medals[i]} {name} ({nid[-4:]}) — {score} امتیاز\n"
            else:
                msg += "هنوز امتیازی ثبت نشده\n"
            if my_score > 0:
                msg += f"\n👤 امتیاز تو: {my_score} امتیاز\n"
            msg += "\n➖➖➖➖➖➖➖➖\n\n"

        # مراحل حذفی (4 تا 8 با هم)
        knockout_top = get_leaderboard_knockout()
        my_knockout = get_user_score_knockout(user_id)
        if knockout_top or my_knockout > 0:
            msg += "🏟 مراحل حذفی:\n"
            if knockout_top:
                for i, (name, nid, score) in enumerate(knockout_top):
                    msg += f"{medals[i]} {name} ({nid[-4:]}) — {score} امتیاز\n"
            else:
                msg += "هنوز امتیازی ثبت نشده\n"
            if my_knockout > 0:
                msg += f"\n👤 امتیاز تو: {my_knockout} امتیاز\n"
            msg += "\n➖➖➖➖➖➖➖➖\n\n"

        top_total = get_leaderboard_total()
        my_total = get_user_total_score(user_id)
        msg += "🏆 امتیاز کل:\n"
        if top_total:
            for i, (name, nid, score) in enumerate(top_total):
                msg += f"{medals[i]} {name} ({nid[-4:]}) — {score} امتیاز\n"
        else:
            msg += "هنوز امتیازی ثبت نشده\n"
        if my_total > 0:
            msg += f"\n👤 امتیاز کل تو: {my_total} امتیاز\n"

        await update.message.reply_text(msg, reply_markup=main_keyboard())
        return MAIN_MENU

    return MAIN_MENU

async def predict_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("منوی اصلی:", reply_markup=main_keyboard())
        return MAIN_MENU

    if text == "مراحل حذفی":
        await update.message.reply_text("کدوم مرحله؟", reply_markup=knockout_keyboard())
        return PREDICT_KNOCKOUT

    if text in ["دور اول", "دور دوم", "دور سوم"]:
        return await load_matches(update, context, ROUND_MAP[text], text)

    await update.message.reply_text("یکی از گزینه‌ها رو انتخاب کن:", reply_markup=round_keyboard())
    return PREDICT_ROUND

async def predict_knockout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        await update.message.reply_text("کدوم دور؟", reply_markup=round_keyboard())
        return PREDICT_ROUND

    knockout_stages = ["یک شانزدهم نهایی", "یک هشتم نهایی", "یک چهارم نهایی", "نیمه نهایی", "فینال و رده‌بندی"]
    if text in knockout_stages:
        return await load_matches(update, context, ROUND_MAP[text], text)

    await update.message.reply_text("یکی از مراحل رو انتخاب کن:", reply_markup=knockout_keyboard())
    return PREDICT_KNOCKOUT

async def load_matches(update, context, round_num, round_name):
    matches = get_matches_by_round(round_num)
    if not matches:
        kb = knockout_keyboard() if round_num >= 4 else round_keyboard()
        await update.message.reply_text("هنوز بازی‌ای برای این مرحله ثبت نشده.", reply_markup=kb)
        return PREDICT_KNOCKOUT if round_num >= 4 else PREDICT_ROUND
    context.user_data['round'] = round_num
    context.user_data['round_name'] = round_name
    context.user_data['matches'] = matches
    await update.message.reply_text(
        f"بازی {round_name} رو انتخاب کن:",
        reply_markup=matches_keyboard(matches, update.effective_user.id)
    )
    return PREDICT_MATCH_SELECT

async def predict_match_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    round_num = context.user_data.get('round', 1)

    if text == "🔙 بازگشت":
        if round_num >= 4:
            await update.message.reply_text("کدوم مرحله؟", reply_markup=knockout_keyboard())
            return PREDICT_KNOCKOUT
        else:
            await update.message.reply_text("کدوم دور؟", reply_markup=round_keyboard())
            return PREDICT_ROUND

    matches = context.user_data.get('matches', [])
    selected = None
    for m in matches:
        mid, team1, team2, date, rnum, g1, g2, locked = m
        if f"{team1} vs {team2}" in text:
            selected = m
            break

    if not selected:
        await update.message.reply_text("بازی رو از لیست انتخاب کن:")
        return PREDICT_MATCH_SELECT

    mid, team1, team2, date, rnum, g1, g2, locked = selected

    if locked or g1 is not None:
        await update.message.reply_text("🔒 پیش‌بینی این بازی بسته شده.")
        return PREDICT_MATCH_SELECT

    context.user_data['current_match'] = selected
    pred = get_prediction(update.effective_user.id, mid)
    status = ""
    if pred:
        status = f"\n📝 پیش‌بینی قبلی تو: {team1} {pred[3]} - {pred[4]} {team2}"

    await update.message.reply_text(
        f"⚽ {team1} vs {team2}\n📅 {date}{status}\n\n"
        f"گل‌های {team1} چنده؟",
        reply_markup=goals_keyboard()
    )
    return PREDICT_GOAL1

async def predict_goal1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        matches = context.user_data.get('matches', [])
        await update.message.reply_text(
            "بازی رو انتخاب کن:",
            reply_markup=matches_keyboard(matches, update.effective_user.id)
        )
        return PREDICT_MATCH_SELECT

    if not text.isdigit() or not (0 <= int(text) <= 10):
        await update.message.reply_text("❌ عدد ۰ تا ۱۰ وارد کن:")
        return PREDICT_GOAL1

    context.user_data['pred_goal1'] = int(text)
    match = context.user_data['current_match']
    team2 = match[2]
    await update.message.reply_text(f"گل‌های {team2} چنده؟", reply_markup=goals_keyboard())
    return PREDICT_GOAL2

async def predict_goal2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 بازگشت":
        match = context.user_data['current_match']
        team1 = match[1]
        await update.message.reply_text(f"گل‌های {team1} چنده؟", reply_markup=goals_keyboard())
        return PREDICT_GOAL1

    if not text.isdigit() or not (0 <= int(text) <= 10):
        await update.message.reply_text("❌ عدد ۰ تا ۱۰ وارد کن:")
        return PREDICT_GOAL2

    g2 = int(text)
    g1 = context.user_data['pred_goal1']
    match = context.user_data['current_match']
    mid, team1, team2 = match[0], match[1], match[2]
    save_prediction(update.effective_user.id, mid, g1, g2)
    matches = get_matches_by_round(context.user_data['round'])
    context.user_data['matches'] = matches
    await update.message.reply_text(
        f"✅ ثبت شد: {team1} {g1} - {g2} {team2}\n\nبازی دیگه‌ای انتخاب کن یا بازگشت بزن:",
        reply_markup=matches_keyboard(matches, update.effective_user.id)
    )
    return PREDICT_MATCH_SELECT

# ===== Admin Commands =====
async def add_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        parts = " ".join(context.args).split("|")
        round_num = int(parts[3].strip())
        add_match_db(parts[0].strip(), parts[1].strip(), parts[2].strip(), round_num)
        round_name = ROUND_NAMES.get(round_num, str(round_num))
        await update.message.reply_text(f"✅ بازی {parts[0].strip()} vs {parts[1].strip()} — {round_name} اضافه شد.")
    except:
        msg = ("فرمت: /addmatch تیم۱|تیم۲|تاریخ|شماره_دور\n\n"
               "شماره دورها:\n"
               "1=دور اول | 2=دور دوم | 3=دور سوم\n"
               "4=یک شانزدهم | 5=یک هشتم | 6=یک چهارم\n"
               "7=نیمه نهایی | 8=فینال و رده‌بندی")
        await update.message.reply_text(msg)

async def set_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        parts = " ".join(context.args).split("|")
        set_result_db(int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip()))
        await update.message.reply_text(f"✅ نتیجه بازی {parts[0].strip()} ثبت شد و امتیازات آپدیت شدن.")
    except:
        await update.message.reply_text("فرمت: /setresult شماره|گل_تیم۱|گل_تیم۲")

async def delete_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        match_id = int(context.args[0])
        m = get_match(match_id)
        if not m:
            await update.message.reply_text("❌ بازی پیدا نشد.")
            return
        delete_match_db(match_id)
        await update.message.reply_text(f"✅ بازی {m[1]} vs {m[2]} حذف شد.")
    except:
        await update.message.reply_text("فرمت: /deletematch شماره_بازی")

async def lock_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        match_id = int(context.args[0])
        m = get_match(match_id)
        if not m:
            await update.message.reply_text("❌ بازی پیدا نشد.")
            return
        lock_match_db(match_id)
        await update.message.reply_text(f"✅ بازی {m[1]} vs {m[2]} قفل شد.")
    except:
        await update.message.reply_text("فرمت: /lockmatch شماره_بازی")

async def unlock_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        match_id = int(context.args[0])
        m = get_match(match_id)
        if not m:
            await update.message.reply_text("❌ بازی پیدا نشد.")
            return
        unlock_match_db(match_id)
        await update.message.reply_text(f"✅ بازی {m[1]} vs {m[2]} آنلاک شد. کاربرا می‌تونن پیش‌بینی کنن.")
    except:
        await update.message.reply_text("فرمت: /unlockmatch شماره_بازی")

async def reset_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⚠️ آیا مطمئنی؟ همه پیش‌بینی‌ها و امتیازات پاک میشن!\n\nبنویس: تایید")
    return RESET_CONFIRM

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "تایید":
        reset_all_db()
        await update.message.reply_text("✅ همه پیش‌بینی‌ها و امتیازات ریست شدن.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("❌ ریست لغو شد.", reply_markup=main_keyboard())
    return MAIN_MENU

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("پیامی که می‌خوای به همه بفرستی رو بنویس:")
    return BROADCAST_MSG

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user_ids = get_all_user_ids()
    success = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 پیام از ادمین:\n\n{msg}")
            success += 1
        except:
            pass
    await update.message.reply_text(f"✅ پیام به {success} نفر ارسال شد.", reply_markup=main_keyboard())
    return MAIN_MENU

async def list_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("worldcup.db")
    c = conn.cursor()
    c.execute("SELECT id, team1, team2, date, round, goal1, goal2, locked FROM matches ORDER BY round, date")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("هیچ بازی‌ای ثبت نشده.")
        return
    msg = "📋 لیست بازی‌ها:\n\n"
    for r in rows:
        mid, t1, t2, date, rnd, g1, g2, locked = r
        result = f"{g1}-{g2}" if g1 is not None else "—"
        lock_icon = "🔒" if locked else "🔓"
        rname = ROUND_NAMES.get(rnd, str(rnd))
        msg += f"#{mid} | {rname} | {t1} vs {t2} | {date} | {result} {lock_icon}\n"
    await update.message.reply_text(msg)

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = get_all_users_full()
    if not users:
        await update.message.reply_text("هنوز کاربری ثبت‌نام نکرده.")
        return
    msg = f"👥 لیست کاربران ({len(users)} نفر):\n\n"
    for i, (uid, nid, phone, name, score) in enumerate(users):
        msg += f"{i+1}. {name}\n🪪 {nid} | 📱 {phone} | 🆔 {uid} | 🏆 {score} امتیاز\n\n"
        if len(msg) > 3500:
            await update.message.reply_text(msg)
            msg = ""
    if msg:
        await update.message.reply_text(msg)

# ===== Main =====
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("reset", reset_start),
            CommandHandler("broadcast", broadcast_start),
        ],
        states={
            REGISTER_NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_national_id)],
            REGISTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
            PREDICT_ROUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_round)],
            PREDICT_KNOCKOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_knockout)],
            PREDICT_MATCH_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_match_select)],
            PREDICT_GOAL1: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_goal1)],
            PREDICT_GOAL2: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_goal2)],
            RESET_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, reset_confirm)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("addmatch", add_match))
    app.add_handler(CommandHandler("setresult", set_result))
    app.add_handler(CommandHandler("deletematch", delete_match))
    app.add_handler(CommandHandler("lockmatch", lock_match))
    app.add_handler(CommandHandler("unlockmatch", unlock_match))
    app.add_handler(CommandHandler("listmatches", list_matches))
    app.add_handler(CommandHandler("users", users_list))

    print("✅ بات شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()
  
