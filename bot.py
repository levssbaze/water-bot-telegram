import sqlite3
import random
import asyncio
import os
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# =================== НАСТРОЙКИ ===================
TOKEN = "8228969867:AAEBrLBjaxnhZjiEBTCGuqKX3VeOAffAHV4"
GROUP_ID = -1003015346551
ADMIN_ID = 577104457
BOT_USERNAME = "@watereverydaybot"

MOTIVATION = [
    "💧 Вода — это жизнь! Пей и сияй!",
    "🌟 Ты молодец! Ещё стакан — и ты супергерой!",
    "✨ Хорошая гидратация = красивая кожа!",
    "🚀 Продолжай! Ты на правильном пути!",
    "💪 Каждый глоток делает тебя сильнее!",
    "💧 Факт: Вода сжигает 50 ккал/литр!",
    "✨ Факт: Кожа эластичнее на 30%!",
    "🧠 Факт: Память улучшается на 20%!",
    "💤 Факт: Сон лучше на 15%!",
    "❤️ Факт: Сердце работает легче!"
]

GENDER, AGE, WEIGHT, ACTIVITY, CLIMATE, PREGNANCY, CUSTOM_GOAL = range(7)

# =================== БАЗА ДАННЫХ (ПЕРЕСОЗДАЁТСЯ!) ===================
def init_db():
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    
    # УДАЛЯЕМ СТАРУЮ БАЗУ + СОЗДАЁМ НОВУЮ
    c.execute("DROP TABLE IF EXISTS users")
    c.execute("DROP TABLE IF EXISTS daily_stats")
    c.execute("DROP TABLE IF EXISTS marathon_history")
    c.execute("DROP TABLE IF EXISTS messages")
    
    # НОВАЯ БАЗА
    c.execute('''CREATE TABLE users (
        user_id INTEGER PRIMARY KEY,
        gender TEXT,
        age INTEGER,
        weight REAL,
        activity TEXT,
        climate TEXT,
        pregnancy TEXT,
        goal REAL DEFAULT 2.0,
        daily_intake REAL DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_date TEXT,
        subscribed INTEGER DEFAULT 1,
        group_member INTEGER DEFAULT 0,
        marathon_start TEXT,
        marathon_day INTEGER DEFAULT 1
    )''')
    
    c.execute('''CREATE TABLE daily_stats (
        user_id INTEGER,
        date TEXT,
        intake REAL,
        goal REAL,
        achieved INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )''')
    
    c.execute('''CREATE TABLE marathon_history (
        user_id INTEGER,
        start_date TEXT,
        end_date TEXT,
        total_streak INTEGER
    )''')
    
    c.execute('''CREATE TABLE messages (
        streak_day INTEGER PRIMARY KEY,
        message_text TEXT
    )''')
    
    # Дефолтные сообщения
    default_msgs = {
        3: "🎉 3 дня подряд! Ты на волне! 💪",
        7: "🏆 Неделя успеха! Поделись с друзьями! 📣",
        14: "🔥 2 недели! Кожа сияет! ✨",
        21: "🌈 3 недели! Привычка закрепилась! 👏",
        30: "🥳 МАРАФОН ЗАВЁРШЁН! Ты изменил жизнь! 🎉"
    }
    for day, msg in default_msgs.items():
        c.execute("INSERT INTO messages VALUES (?, ?)", (day, msg))
    
    conn.commit()
    conn.close()
    print("✅ БАЗА ДАННЫХ ПЕРЕСОЗДАНА!")

def get_user(user_id):
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if not result:
        conn = sqlite3.connect('water_bot.db')
        c = conn.cursor()
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        return (user_id, None, None, None, None, None, None, 2.0, 0, 0, None, 1, 0, None, 1)
    return result

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    set_parts = ", ".join([f"{k}=?" for k in kwargs.keys()])
    query = f"UPDATE users SET {set_parts} WHERE user_id = ?"
    values = list(kwargs.values()) + [user_id]
    c.execute(query, values)
    conn.commit()
    conn.close()

def save_daily_stats(user_id, intake, goal):
    today = datetime.now().strftime('%Y-%m-%d')
    achieved = 1 if intake >= goal else 0
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO daily_stats VALUES (?, ?, ?, ?, ?)", 
              (user_id, today, intake, goal, achieved))
    conn.commit()
    conn.close()

def add_intake(user_id, amount):
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user[10] == today:
        new_intake = user[8] + amount
    else:
        new_intake = amount
    update_user(user_id, daily_intake=new_intake, last_date=today)
    save_daily_stats(user_id, new_intake, user[7])
    return new_intake

def get_streak_message(streak_day):
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT message_text FROM messages WHERE streak_day = ?", (streak_day,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else f"🎉 Стрик {streak_day} дней!"

def get_week_stats(user_id):
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT date, intake FROM daily_stats WHERE user_id = ? AND date >= ? ORDER BY date", 
              (user_id, week_ago.strftime('%Y-%m-%d')))
    stats = c.fetchall()
    conn.close()
    return stats

# =================== РАСЧЁТ ЦЕЛИ ===================
def calculate_goal(gender, age, weight, activity, climate, pregnancy):
    if age < 1: return 0.8
    elif age <= 3: return 1.3
    elif age <= 8: return 1.7
    elif age <= 13: return 2.4 if gender == 'male' else 2.1
    elif age <= 18: return 3.3 if gender == 'male' else 2.3
    else:
        base = (weight * (35 if gender == 'male' else 30)) / 1000
        if age > 65: base *= 0.9
        if activity == 'средняя': base += 0.5
        elif activity == 'высокая': base += 1.2
        if climate == 'умеренный': base += 0.2
        elif climate == 'жаркий': base += 0.75
        if pregnancy == 'беременность': base += 0.3
        elif pregnancy == 'кормление': base += 0.85
    return round(base, 1)

# =================== МЕНЮ ===================
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("💧 Выпил воду", callback_data="log_water")],
        [InlineKeyboardButton("📈 Статистика", callback_data="show_stats")],
        [InlineKeyboardButton("👥 Группа", url="https://t.me/+Ic9SbOrxNWQzNmIy")]
    ]
    return InlineKeyboardMarkup(keyboard)

# =================== ОПРОС ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("👨 Мужчина", callback_data="male")],
        [InlineKeyboardButton("👩 Женщина", callback_data="female")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💧 Привет! Я @watereverydaybot\n\nВыбери пол:", reply_markup=reply_markup)
    return GENDER

async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    update_user(query.from_user.id, gender=query.data)
    await query.edit_message_text("📏 Введи возраст (лет):")
    return AGE

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int(update.message.text)
        update_user(update.effective_user.id, age=age)
        await update.message.reply_text("⚖️ Введи вес (кг):")
        return WEIGHT
    except:
        await update.message.reply_text("❌ Введи число. Возраст:")
        return AGE

async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float(update.message.text)
        update_user(update.effective_user.id, weight=weight)
        keyboard = [
            [InlineKeyboardButton("Низкая (офис)", callback_data="низкая")],
            [InlineKeyboardButton("Средняя (ходьба)", callback_data="средняя")],
            [InlineKeyboardButton("Высокая (спорт)", callback_data="высокая")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🏃 Физическая активность:", reply_markup=reply_markup)
        return ACTIVITY
    except:
        await update.message.reply_text("❌ Введи число. Вес (кг):")
        return WEIGHT

async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    update_user(query.from_user.id, activity=query.data)
    keyboard = [
        [InlineKeyboardButton("Холодный (<15°)", callback_data="холодный")],
        [InlineKeyboardButton("Умеренный (15-25°)", callback_data="умеренный")],
        [InlineKeyboardButton("Жаркий (>25°)", callback_data="жаркий")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🌡️ Климат:", reply_markup=reply_markup)
    return CLIMATE

async def climate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    update_user(query.from_user.id, climate=query.data)
    user = get_user(query.from_user.id)
    if user[1] == 'female':
        keyboard = [
            [InlineKeyboardButton("Нет", callback_data="нет")],
            [InlineKeyboardButton("Беременность", callback_data="беременность")],
            [InlineKeyboardButton("Кормление", callback_data="кормление")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🤰 Беременность/кормление?", reply_markup=reply_markup)
        return PREGNANCY
    return await propose_goal(query, context)

async def pregnancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    update_user(query.from_user.id, pregnancy=query.data)
    return await propose_goal(query, context)

async def propose_goal(update, context):
    user = get_user(update.callback_query.from_user.id)
    goal = calculate_goal(user[1], user[2], user[3], user[4], user[5], user[6])
    update_user(user[0], goal=goal)
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data="accept_goal")],
        [InlineKeyboardButton("📝 Своя цель", callback_data="custom_goal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(f"📊 Рекомендация: **{goal} л/день**\n\nПринять?", reply_markup=reply_markup, parse_mode='Markdown')
    return CUSTOM_GOAL

async def accept_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Цель установлена! Начинаем марафон! 💧", reply_markup=get_main_menu())
    return ConversationHandler.END

async def custom_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Введи свою цель в литрах (2.5):")
    return CUSTOM_GOAL

async def set_custom_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        goal = float(update.message.text)
        update_user(update.effective_user.id, goal=goal)
        await update.message.reply_text(f"✅ Цель: **{goal} л**! Марафон начат! 💧", reply_markup=get_main_menu(), parse_mode='Markdown')
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи число (например: 2.5)")
        return CUSTOM_GOAL

# =================== КОМАНДЫ ===================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    progress = min(int((user[8] / user[7]) * 10), 10)
    bar = "🔵" * progress + "⚪" * (10 - progress)
    
    # Календарь
    today = datetime.now()
    calendar_text = ""
    for i in range(5):
        date = today - timedelta(days=4-i)
        date_str = date.strftime('%d.%m')
        conn = sqlite3.connect('water_bot.db')
        c = conn.cursor()
        c.execute("SELECT intake FROM daily_stats WHERE user_id = ? AND date = ?", 
                  (user[0], date.strftime('%Y-%m-%d')))
        result = c.fetchone()
        conn.close()
        intake = result[0] if result else 0
        day_progress = min(int((intake / user[7]) * 6), 6)
        day_bar = "🔵" * day_progress + "⚪" * (6 - day_progress)
        status = "✅" if intake >= user[7] else ""
        calendar_text += f"💧 {date_str}: {day_bar} {status}\n"
    
    text = f"""📊 **{BOT_USERNAME} — СТАТИСТИКА**

💧 Сегодня: {bar} (**{user[8]:.1f}/{user[7]:.1f} л**)
📅 Стрик: **{user[9]} дней**

**КАЛЕНДАРЬ (5 дней):**
{calendar_text}

{random.choice(MOTIVATION)}"""
    
    await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode='Markdown')

async def log_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("200 мл", callback_data="add_0.2"), InlineKeyboardButton("300 мл", callback_data="add_0.3")],
        [InlineKeyboardButton("500 мл", callback_data="add_0.5"), InlineKeyboardButton("Другое", callback_data="custom_intake")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💧 Выпил воду:", reply_markup=reply_markup)

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%Y-%m-%d')
    update_user(update.effective_user.id, daily_intake=0, streak=0, last_date=today)
    await update.message.reply_text("✅ **Статистика сброшена!** Чистый старт! 💧", reply_markup=get_main_menu(), parse_mode='Markdown')

async def new_marathon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%Y-%m-%d')
    update_user(update.effective_user.id, 
                daily_intake=0, streak=0, last_date=today, 
                marathon_start=today, marathon_day=1)
    await update.message.reply_text("🏁 **30-ДНЕВНЫЙ МАРАФОН НАЧАТ!**\n**День 1/30**", reply_markup=get_main_menu(), parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""📖 **{BOT_USERNAME} — ПОМОЩЬ**

/start — Опрос цели
/log — Ввод воды
/stats — Статистика
/reset_stats — Сброс  
/new_marathon — Новый марафон
/unsubscribe — Выкл. напоминания

👥 Группа: t.me/+Ic9SbOrxNWQzNmIy"""
    await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode='Markdown')

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user(update.effective_user.id, subscribed=0)
    await update.message.reply_text("✅ Напоминания отключены", reply_markup=get_main_menu())

# =================== КНОПКИ ===================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if query.data == "log_water":
        keyboard = [
            [InlineKeyboardButton("200 мл", callback_data="add_0.2"), InlineKeyboardButton("300 мл", callback_data="add_0.3")],
            [InlineKeyboardButton("500 мл", callback_data="add_0.5"), InlineKeyboardButton("Другое", callback_data="custom_intake")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("💧 Выбери объём:", reply_markup=reply_markup)
    elif query.data.startswith("add_"):
        amount = float(query.data.split("_")[1])
        new_intake = add_intake(user_id, amount)
        progress = min(int((new_intake / user[7]) * 100), 100)
        if new_intake >= user[7]:
            await query.edit_message_text(f"🎉 **ЦЕЛЬ ДОСТИГНУТА!** {progress}% 🌟", reply_markup=get_main_menu(), parse_mode='Markdown')
        else:
            await query.edit_message_text(f"✅ **+{amount*1000} мл** | **{progress}%**", reply_markup=get_main_menu(), parse_mode='Markdown')
    elif query.data == "show_stats":
        await stats(query.message, context)
    elif query.data == "accept_goal":
        await accept_goal(update, context)
    elif query.data == "custom_goal":
        await custom_goal(update, context)
    elif query.data == "custom_intake":
        await query.message.reply_text("📝 Введи объём в мл (250):")

async def handle_custom_intake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text) / 1000
        new_intake = add_intake(update.effective_user.id, amount)
        user = get_user(update.effective_user.id)
        progress = min(int((new_intake / user[7]) * 100), 100)
        await update.message.reply_text(f"✅ **+{update.message.text} мл** | **{progress}%**", reply_markup=get_main_menu(), parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Введи число в мл (250)")

# =================== АДМИН ===================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: 
        await update.message.reply_text("📤 /broadcast ТЕКСТ")
        return
    message = " ".join(context.args)
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE subscribed = 1")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    success = 0
    for user_id in users:
        try:
            await context.bot.send_message(user_id, f"💧 @{BOT_USERNAME}\n\n{message}")
            success += 1
        except: continue
    await context.bot.send_message(GROUP_ID, f"💧 @{BOT_USERNAME}\n\n{message}")
    await update.message.reply_text(f"📤 Рассылка: **{success}/{len(users)}**")

# =================== НАПОМИНАНИЯ ===================
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE subscribed = 1")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    for user_id in users:
        try:
            keyboard = [
                [InlineKeyboardButton("200 мл", callback_data="add_0.2"), InlineKeyboardButton("300 мл", callback_data="add_0.3")],
                [InlineKeyboardButton("500 мл", callback_data="add_0.5")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                user_id, 
                f"💧 @{BOT_USERNAME}\n\n**Время пить воду!**\n{random.choice(MOTIVATION)}",
                reply_markup=reply_markup, parse_mode='Markdown'
            )
        except: continue

async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('water_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, daily_intake, goal, streak FROM users")
    users = c.fetchall()
    today = datetime.now().strftime('%Y-%m-%d')
    for user_id, intake, goal, streak in users:
        save_daily_stats(user_id, intake, goal)
        if intake >= goal:
            streak += 1
        else:
            streak = 0
        c.execute("UPDATE users SET daily_intake=0, streak=?, last_date=? WHERE user_id=?", 
                 (streak, today, user_id))
    conn.commit()
    conn.close()

# =================== ЗАПУСК ===================
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GENDER: [CallbackQueryHandler(gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            ACTIVITY: [CallbackQueryHandler(activity)],
            CLIMATE: [CallbackQueryHandler(climate)],
            PREGNANCY: [CallbackQueryHandler(pregnancy)],
            CUSTOM_GOAL: [
                CallbackQueryHandler(button_callback, pattern="^(accept_goal|custom_goal)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_custom_goal)
            ]
        },
        fallbacks=[],
        per_message=False
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("log", log_water))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reset_stats", reset_stats))
    app.add_handler(CommandHandler("new_marathon", new_marathon))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_intake))
    
    app.job_queue.run_repeating(send_reminder, interval=7200, first=60)
    app.job_queue.run_daily(daily_reset, time=time(0, 0))
    
    print("🤖 @watereverydaybot ЗАПУЩЕН! ✅ 20 ФИЧ!")
    app.run_polling()

if __name__ == '__main__':
    main()