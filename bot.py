import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.environ.get("BOT_TOKEN", "")
COINGECKO = "https://api.coingecko.com/api/v3"
ALERTS = {}

def get_price(coin_id):
    try:
        r = requests.get(f"{COINGECKO}/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true"}, timeout=10)
        return r.json().get(coin_id)
    except:
        return None

def search_coin(query):
    try:
        r = requests.get(f"{COINGECKO}/search", params={"query": query}, timeout=10)
        return r.json().get("coins", [])[:5]
    except:
        return []

def get_top10():
    try:
        r = requests.get(f"{COINGECKO}/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc",
                    "per_page": 10, "page": 1}, timeout=10)
        return r.json()
    except:
        return []

def get_coin_info(coin_id):
    try:
        r = requests.get(f"{COINGECKO}/coins/{coin_id}",
            params={"localization": False, "sparkline": False}, timeout=10)
        return r.json()
    except:
        return None

def fmt_price(v):
    if not v: return "N/A"
    return f"${v:,.2f}" if v >= 1 else f"${v:.6f}"

def fmt_change(v):
    if v is None: return "N/A"
    a = "up" if v >= 0 else "dn"
    s = "+" if v >= 0 else ""
    e = "📈" if v >= 0 else "📉"
    return f"{e} {s}{v:.2f}%"

def fmt_big(v):
    if not v: return "N/A"
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"

async def check_alerts(context):
    for chat_id, alerts in list(ALERTS.items()):
        remaining = []
        for a in alerts:
            data = get_price(a["coin_id"])
            if data:
                price = data.get("usd", 0)
                hit = (a["direction"] == "above" and price >= a["target"]) or \
                      (a["direction"] == "below" and price <= a["target"])
                if hit:
                    await context.bot.send_message(chat_id,
                        f"🔔 *Алерт!* {a['coin_id'].upper()} = {fmt_price(price)}",
                        parse_mode="Markdown")
                else:
                    remaining.append(a)
        ALERTS[chat_id] = remaining

async def start(update, ctx):
    await update.message.reply_text(
        "👋 *Крипто-бот*\n\n"
        "/price btc — цена\n/search doge — поиск\n"
        "/analysis eth — анализ\n/top10 — топ 10\n"
        "/alert btc 90000 — алерт\n/alerts — мои алерты\n\n"
        "Или просто напиши название монеты!", parse_mode="Markdown")

async def price_cmd(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Пример: `/price btc`", parse_mode="Markdown")
        return
    query = " ".join(ctx.args).lower()
    msg = await update.message.reply_text("⏳ Загружаю...")
    data = get_price(query)
    coin_id = query
    if not data:
        results = search_coin(query)
        if not results:
            await msg.edit_text("❌ Монета не найдена.")
            return
        coin_id = results[0]["id"]
        data = get_price(coin_id)
    if not data:
        await msg.edit_text("❌ Ошибка получения данных.")
        return
    text = (f"💰 *{coin_id.upper()}*\n\n"
            f"Цена: `{fmt_price(data.get('usd'))}`\n"
            f"24h: {fmt_change(data.get('usd_24h_change'))}\n"
            f"Капитализация: `{fmt_big(data.get('usd_market_cap'))}`\n"
            f"Объём: `{fmt_big(data.get('usd_24h_vol'))}`")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Анализ", callback_data=f"analysis:{coin_id}"),
        InlineKeyboardButton("🔔 Алерт", callback_data=f"setalert:{coin_id}:{data.get('usd',0):.2f}")
    ]])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def search_cmd(update, ctx):if not ctx.args:
        await update.message.reply_text("Пример: `/search doge`", parse_mode="Markdown")
        return
    query = " ".join(ctx.args)
    msg = await update.message.reply_text("🔍 Ищу...")
    results = search_coin(query)
    if not results:
        await msg.edit_text("❌ Ничего не найдено.")
        return
    buttons = [[InlineKeyboardButton(
        f"{c.get('symbol','').upper()} — {c.get('name','')}",
        callback_data=f"price:{c['id']}")] for c in results]
    await msg.edit_text(f"🔍 *{query}*:", parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(buttons))

async def analysis_cmd(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Пример: `/analysis btc`", parse_mode="Markdown")
        return
    msg = await update.message.reply_text("📊 Анализирую...")
    await send_analysis(msg, ctx.args[0].lower(), edit=True)

async def send_analysis(msg, coin_id, edit=False):
    info = get_coin_info(coin_id)
    if not info or "market_data" not in info:
        t = "❌ Не удалось получить данные."
        if edit: await msg.edit_text(t)
        else: await msg.reply_text(t)
        return
    md = info["market_data"]
    p = md["current_price"].get("usd")
    h24 = md.get("price_change_percentage_24h")
    h7 = md.get("price_change_percentage_7d")
    h30 = md.get("price_change_percentage_30d")
    ath = md["ath"].get("usd")
    atl = md["atl"].get("usd")
    hi = md["high_24h"].get("usd")
    lo = md["low_24h"].get("usd")
    sig = "📈 Бычий тренд" if (h24 or 0) > 3 else "📉 Медвежий тренд" if (h24 or 0) < -3 else "😐 Нейтрально"
    text = (f"📊 *{coin_id.upper()}*\n\n"
            f"Цена: `{fmt_price(p)}`\n"
            f"24h: {fmt_change(h24)}\n7д: {fmt_change(h7)}\n30д: {fmt_change(h30)}\n\n"
            f"Макс 24h: `{fmt_price(hi)}`\nМин 24h: `{fmt_price(lo)}`\n\n"
            f"ATH: `{fmt_price(ath)}`\nATL: `{fmt_price(atl)}`\n\n"
            f"Сигнал: {sig}")
    if edit: await msg.edit_text(text, parse_mode="Markdown")
    else: await msg.reply_text(text, parse_mode="Markdown")

async def top10_cmd(update, ctx):
    msg = await update.message.reply_text("🏆 Загружаю...")
    coins = get_top10()
    if not coins:
        await msg.edit_text("❌ Ошибка.")
        return
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = ["🏆 *Топ-10*\n"]
    for i, c in enumerate(coins):
        ch = c.get("price_change_percentage_24h") or 0
        lines.append(f"{medals[i]} *{c['symbol'].upper()}* {fmt_price(c['current_price'])} {'📈' if ch>=0 else '📉'}{ch:+.1f}%")
    buttons = [[InlineKeyboardButton(c['symbol'].upper(), callback_data=f"price:{c['id']}") for c in coins[i:i+5]] for i in range(0,10,5)]
    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def alert_cmd(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("Пример: `/alert btc 90000`", parse_mode="Markdown")
        return
    coin_id = ctx.args[0].lower()
    try: target = float(ctx.args[1].replace(",",""))
    except: await update.message.reply_text("❌ Неверная цена."); return
    data = get_price(coin_id)
    if not data:
        r = search_coin(coin_id)
        if r: coin_id = r[0]["id"]; data = get_price(coin_id)
    if not data: await update.message.reply_text("❌ Монета не найдена."); return
    cur = data.get("usd", 0)
    direction = "above" if target > cur else "below"
    cid = update.effective_chat.id
    if cid not in ALERTS: ALERTS[cid] = []
    ALERTS[cid].append({"coin_id": coin_id, "target": target, "direction": direction})
    word = "вырастет до" if direction == "above" else "упадёт до"
    await update.message.reply_text(
        f"🔔 Алерт установлен!\n{coin_id.upper()} {word} `{fmt_price(target)}`\nСейчас: `{fmt_price(cur)}`",
        parse_mode="Markdown")

async def my_alerts_cmd(update, ctx):
    cid = update.effective_chat.id
    alerts = ALERTS.get(cid, [])
    if not alerts:
        await update.message.reply_text("Нет алертов.Пример: `/alert btc 90000`", parse_mode="Markdown")
        return
    lines = ["📋 *Алерты:*\n"]
    for a in alerts:
        lines.append(f"• {a['coin_id'].upper()} {'↑' if a['direction']=='above' else '↓'} `{fmt_price(a['target'])}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def text_handler(update, ctx):
    query = update.message.text.strip().lower()
    if len(query) < 2: return
    results = search_coin(query)
    if not results: return
    top = results[0]
    if top["name"].lower() == query or top["symbol"].lower() == query:
        data = get_price(top["id"])
        if data:
            text = (f"💰 *{top['id'].upper()}*\n"
                    f"Цена: `{fmt_price(data.get('usd'))}`\n"
                    f"24h: {fmt_change(data.get('usd_24h_change'))}")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Анализ", callback_data=f"analysis:{top['id']}"),
            ]])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        buttons = [[InlineKeyboardButton(f"{c['symbol'].upper()} — {c['name']}",
            callback_data=f"price:{c['id']}")] for c in results]
        await update.message.reply_text(f"🔍 *{query}*:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons))

async def callback_handler(update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("price:"):
        coin_id = data.split(":")[1]
        d = get_price(coin_id)
        if d:
            text = (f"💰 *{coin_id.upper()}*\n"
                    f"Цена: `{fmt_price(d.get('usd'))}`\n"
                    f"24h: {fmt_change(d.get('usd_24h_change'))}\n"
                    f"Капитализация: `{fmt_big(d.get('usd_market_cap'))}`")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Анализ", callback_data=f"analysis:{coin_id}"),
                InlineKeyboardButton("🔔 Алерт", callback_data=f"setalert:{coin_id}:{d.get('usd',0):.2f}")
            ]])
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    elif data.startswith("analysis:"):
        coin_id = data.split(":")[1]
        await q.edit_message_text("📊 Анализирую...")
        await send_analysis(q.message, coin_id, edit=True)
    elif data.startswith("setalert:"):
        parts = data.split(":")
        coin_id, cur = parts[1], float(parts[2])
        await q.edit_message_text(
            f"Установи алерт командой:\n`/alert {coin_id} ЦЕНА`\n\n"
            f"Например:\n`/alert {coin_id} {cur*1.05:.0f}` (+5%)\n"
            f"`/alert {coin_id} {cur*0.95:.0f}` (-5%)",
            parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("analysis", analysis_cmd))
    app.add_handler(CommandHandler("top10", top10_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", my_alerts_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.job_queue.run_repeating(check_alerts, interval=60, first=10)
    print("Bot started!")
    app.run_polling(drop_pending_updates=True)

if name == "__main__":
    main()
