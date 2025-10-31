import asyncio
from telethon import TelegramClient, events
from datetime import datetime, timedelta
import re, sqlite3, json, requests
from io import BytesIO
import matplotlib.pyplot as plt
import pandas as pd
from app.constants import *

# ---------------- CONFIGURABLE PARAMETERS ---------------- #

DB_PATH = 'signals.db'
LIVE_PRICE_THRESHOLD = 10
DUPLICATE_TIMEFRAME_MINUTES = 60
LIVE_PRICE_CHECK_INTERVAL = 30
NEAR_HIT_THRESHOLD = 2
AUTO_EXPORT_HOUR = 0
AUTO_EXPORT_WINDOW_MINUTES = 2
SUMMARY_LOOKBACK_HOURS = 24

# ---------------- TELEGRAM CLIENT ---------------- #
client = TelegramClient('signal_bot', API_ID, API_HASH)

# ---------------- DATABASE SETUP ---------------- #
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chat_id TEXT,
    source_chat_username TEXT,
    source_msg_id INTEGER,
    source_msg_date TEXT,
    source_msg_text TEXT,
    forwarded_msg_id INTEGER,
    destination_chat_id TEXT,
    destination_chat_username TEXT,
    forward_time TEXT,
    parsed_json TEXT,
    updates_json TEXT,
    status TEXT,
    pair TEXT,
    direction TEXT,
    entry_low REAL,
    entry_high REAL,
    tp_list TEXT,
    sl REAL,
    decision_reason TEXT,
    live_price REAL,
    exit_event TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    event_type TEXT,
    event_price REAL,
    event_time TEXT,
    detected_by TEXT,
    FOREIGN KEY(message_id) REFERENCES messages(id)
)
""")
conn.commit()
conn.close()

# ---------------- HELPER FUNCTIONS ---------------- #
def get_live_gold_price():
    try:
        resp = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F")
        data = resp.json()
        return round(float(data["chart"]["result"][0]["meta"]["regularMarketPrice"]), 2)
    except:
        return None

def ranges_overlap(a_low, a_high, b_low, b_high):
    return max(a_low, b_low) <= min(a_high, b_high)

def parse_signal(text):
    lower = text.lower()
    all_numbers = [float(x) for x in re.findall(r'\d{4,5}(?:\.\d{1,2})?', lower)]
    pair = 'XAUUSD' if any(k in lower for k in ['xauusd', 'gold', 'xau/usd']) else None
    if not pair or not all_numbers:
        return None

    entry_match = re.search(r'(\d{4,5}(?:\.\d{1,2})?)\s*(?:-|/|to)\s*(\d{4,5}(?:\.\d{1,2})?)', lower)
    if entry_match:
        entry_low, entry_high = float(entry_match.group(1)), float(entry_match.group(2))
        entry_value = entry_low
    else:
        entry_low = entry_high = entry_value = all_numbers[0]

    tp_keywords = r'(tp\d*[:\s]|target[:\s]|take profit[:\s]*)'
    tp_split = re.split(tp_keywords, lower)
    tps = []
    if len(tp_split) > 1:
        for part in tp_split[1:]:
            tps += [float(tp) for tp in re.findall(r'\d{4,5}(?:\.\d{1,2})?', part)]
    else:
        tps = all_numbers[1:6]

    direction = None
    if tps:
        direction = "BUY" if tps[0] > entry_value else "SELL"

    used = set([entry_low, entry_high] + tps)
    unused = [num for num in all_numbers if num not in used]
    sl = None
    if unused:
        candidate_sl = float(unused[-1])
        if direction == "BUY" and candidate_sl < entry_value:
            sl = candidate_sl
        elif direction == "SELL" and candidate_sl > entry_value:
            sl = candidate_sl

    return {
        "pair": pair,
        "direction": direction,
        "entry_range": {"low": entry_low, "high": entry_high},
        "tp_list": tps[:5],
        "sl": sl,
        "timestamp": datetime.utcnow().isoformat()
    }

def format_signal(parsed, live_price=None):
    emoji = '🟢' if parsed["direction"] == "BUY" else '🔴'
    msg = f"{emoji} {parsed['pair']} {parsed['direction']} Signal\n"
    msg += f"Entry: {parsed['entry_range']['low']} to {parsed['entry_range']['high']}\n"
    for i, tp in enumerate(parsed['tp_list'][:5], 1):
        msg += f"TP{i}: {tp}\n"
    if parsed['sl']: msg += f"SL: {parsed['sl']}\n"
    if live_price: msg += f"📊 Live Price: {live_price}\n"
    msg += f"🕒 Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    return msg.strip()

def save_message(parsed,event,forwarded_msg_id,live_price,status="active",reason="",exit_event=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (
            source_chat_id, source_chat_username, source_msg_id, source_msg_date,
            source_msg_text, forwarded_msg_id, destination_chat_id, destination_chat_username,
            forward_time, parsed_json, updates_json, status, pair, direction,
            entry_low, entry_high, tp_list, sl, decision_reason, live_price, exit_event
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,(event.chat_id,f"@{event.chat.username}" if event.chat.username else "",event.id,event.message.date.isoformat(),event.message.text,forwarded_msg_id,DESTINATION,DESTINATION,datetime.utcnow().isoformat(),json.dumps(parsed),json.dumps([]),status,parsed['pair'],parsed['direction'],parsed['entry_range']['low'],parsed['entry_range']['high'],",".join([str(tp) for tp in parsed['tp_list']]),parsed['sl'],reason,live_price,exit_event))
    conn.commit(); conn.close()

async def mark_update(msg_id, update_type, price, detected_by, dest_id, fwd_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT parsed_json, updates_json, exit_event FROM messages WHERE id=?", (msg_id,))
    row = cursor.fetchone()
    parsed = json.loads(row[0])
    updates_json = json.loads(row[1]) if row[1] else []
    exit_event = row[2]
    parsed_hit = {"type": update_type, "price": price, "time": datetime.utcnow().isoformat()}
    
    # Only count first TP/SL/BE as official closure, but record all TP hits before closure
    closed = exit_event in ["TP", "SL", "BE"]
    
    if update_type.startswith("TP") and not closed:
        updates_json.append(parsed_hit)
        cursor.execute("UPDATE messages SET exit_event=? WHERE id=?", ("TP", msg_id))
    elif update_type == "SL" and not closed and not any(h['type'].startswith("TP") for h in updates_json):
        updates_json.append(parsed_hit)
        cursor.execute("UPDATE messages SET exit_event=? WHERE id=?", ("SL", msg_id))
    elif update_type == "BE" and not closed:
        updates_json.append(parsed_hit)
        cursor.execute("UPDATE messages SET exit_event=? WHERE id=?", ("BE", msg_id))
    elif update_type.startswith("TP") and closed and exit_event == "TP":
        updates_json.append(parsed_hit)  # For analytics, record multiple TP hits before break-even
    
    # Format update message (shows TP hits and closure event)
    tp_hits = sum(1 for h in updates_json if h["type"].startswith("TP"))
    updated_text = f"{'🟢' if parsed['direction']=='BUY' else '🔴'} {parsed['pair']} {parsed['direction']} Signal\n"
    updated_text += f"Entry: {parsed['entry_range']['low']} to {parsed['entry_range']['high']}\n"
    for i, tp in enumerate(parsed['tp_list'][:5],1):
        hit_marker = "✅" if f"TP{i}" in [h['type'] for h in updates_json] else ""
        updated_text += f"TP{i}: {tp} {hit_marker}\n"
    if parsed['sl']:
        sl_hit = "✅" if "SL" in [h['type'] for h in updates_json] else ""
        updated_text += f"SL: {parsed['sl']} {sl_hit}\n"
    live_price = get_live_gold_price()
    if live_price: updated_text += f"📊 Live Price: {live_price}\n"
    updated_text += f"🕒 Last Update: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
    updated_text += f"TP Hits so far: {tp_hits}/{len(parsed['tp_list'])}"
    if exit_event:
        updated_text += f"\nSignal Closed by {exit_event}"
    if fwd_id and dest_id:
        try: await client.edit_message(dest_id, fwd_id, updated_text)
        except Exception as e: print(f"[EDIT ERROR] {e}")
    cursor.execute("UPDATE messages SET parsed_json=?, updates_json=? WHERE id=?", (json.dumps(parsed), json.dumps(updates_json), msg_id))
    conn.commit(); conn.close()

# ---------------- SIGNAL PROGRESS CHART ---------------- #
def generate_signal_progress_chart(message_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT parsed_json, updates_json FROM messages WHERE id=?", (message_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    parsed = json.loads(row[0])
    updates = json.loads(row[1]) if row[1] else []
    hit_events = [u for u in updates if u["type"].startswith("TP") or u["type"]=="SL" or u["type"]=="BE"]
    if not hit_events:
        conn.close()
        return None
    times = [datetime.fromisoformat(u["event_time"]) for u in updates]
    prices = [u["event_price"] for u in updates]
    if not times:
        conn.close()
        return None
    plt.figure(figsize=(10,6))
    plt.plot(times, prices, label="Live Price", marker='o', color='blue')
    for i, tp in enumerate(parsed.get("tp_list", []),1):
        plt.hlines(tp, times[0], times[-1], colors='green', linestyles='dashed', label=f"TP{i}")
    if parsed.get("sl"):
        plt.hlines(parsed["sl"], times[0], times[-1], colors='red', linestyles='dashed', label="SL")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.title(f"{parsed['pair']} {parsed['direction']} Signal Progress")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    output = BytesIO()
    plt.savefig(output, format='png')
    plt.close()
    output.seek(0)
    conn.close()
    return output

# ---------------- CHANNEL PERFORMANCE CHART ---------------- #
def generate_channel_performance_chart(hours_lookback=24):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timeframe_ago = (datetime.utcnow() - timedelta(hours=hours_lookback)).isoformat()
    cursor.execute("""
        SELECT source_chat_username, updates_json FROM messages WHERE source_msg_date >= ?
    """, (timeframe_ago,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    channel_stats = {}
    for chat_username, updates_json in rows:
        updates = json.loads(updates_json) if updates_json else []
        tp_hits = len([u for u in updates if u["type"].startswith("TP")])
        sl_hits = sum(1 for u in updates if u["type"] == "SL")
        channel_stats[chat_username] = channel_stats.get(chat_username, 0) + tp_hits
    plt.figure(figsize=(10,6))
    channels = list(channel_stats.keys())
    hits = list(channel_stats.values())
    plt.bar(channels, hits, color='teal')
    plt.xlabel("Source Channel")
    plt.ylabel("TP Hits")
    plt.title(f"Channel Performance — Last {hours_lookback} Hours (TP Count)")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    output = BytesIO()
    plt.savefig(output, format='png')
    plt.close()
    output.seek(0)
    return output

def export_to_excel():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM messages", conn)
    conn.close()
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output

# ---------------- MAIN FUNCTION ---------------- #
async def main():
    await client.start(phone=PHONE)
    print("Bot running...")

    @client.on(events.NewMessage)
    async def handler(event):
        chat = await event.get_chat()
        username = chat.username or ""
        if username.lower() not in [s.replace('@','').lower() for s in SOURCES]:
            return
        parsed = parse_signal(event.message.text)
        if not parsed: return
        live_price = get_live_gold_price()
        entry_low, entry_high = parsed["entry_range"]["low"], parsed["entry_range"]["high"]
        if live_price is not None and not (entry_low-LIVE_PRICE_THRESHOLD <= live_price <= entry_high+LIVE_PRICE_THRESHOLD):
            save_message(parsed,event,None,live_price,"skipped","price out of range")
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        timeframe_ago = (datetime.utcnow() - timedelta(minutes=DUPLICATE_TIMEFRAME_MINUTES)).isoformat()
        cursor.execute("SELECT direction,entry_low,entry_high,source_chat_username FROM messages WHERE status='active' AND source_msg_date >= ?",(timeframe_ago,))
        recent_signals = cursor.fetchall()
        conn.close()
        duplicate_found=False; conflict_found=False
        for dir_existing, low_existing, high_existing, src_existing in recent_signals:
            if ranges_overlap(entry_low,entry_high,low_existing,high_existing):
                if dir_existing == parsed["direction"]:
                    duplicate_found=True; break
                else:
                    conflict_found=True; conflict_info=f"Conflict with {src_existing} ({dir_existing})"; break
        if duplicate_found:
            save_message(parsed,event,None,live_price,"skipped","duplicate"); return
        if conflict_found:
            save_message(parsed,event,None,live_price,"skipped","conflict")
            for admin in ADMINS:
                await client.send_message(admin,f"⚠ Conflicting signal from {event.chat.username} ({parsed['direction']}) for range {entry_low}-{entry_high}.\n{conflict_info}")
            return
        formatted_msg=format_signal(parsed,live_price)
        sent=await client.send_message(DESTINATION,formatted_msg)
        save_message(parsed,event,sent.id,live_price)

    @client.on(events.MessageDeleted)
    async def deleted_handler(event):
        deleted_ids=event.deleted_ids
        if not deleted_ids: return
        conn=sqlite3.connect(DB_PATH); cursor=conn.cursor()
        cursor.execute(f"SELECT id, forwarded_msg_id, destination_chat_id FROM messages WHERE source_msg_id IN ({','.join('?'*len(deleted_ids))}) AND status='active'",deleted_ids)
        rows=cursor.fetchall()
        for msg_id,fwd_id,dest_id in rows:
            try:
                await client.delete_messages(dest_id,fwd_id)
                cursor.execute("UPDATE messages SET status='deleted' WHERE id=?",(msg_id,))
                print(f"[DELETED] Forwarded message {fwd_id} removed, saved in DB")
            except Exception as e: print(f"[DELETE ERROR] {e}")
        conn.commit(); conn.close()

    async def live_price_monitor_task():
        while True:
            price=get_live_gold_price()
            if not price: await asyncio.sleep(LIVE_PRICE_CHECK_INTERVAL); continue
            conn=sqlite3.connect(DB_PATH); cursor=conn.cursor()
            cursor.execute("SELECT id, parsed_json, forwarded_msg_id, destination_chat_id, updates_json, exit_event FROM messages WHERE status IN ('active','deleted')")
            rows=cursor.fetchall(); conn.close()
            for mid, parsed_json, fwd_id, dest_id, updates_json_str, exit_event in rows:
                parsed=json.loads(parsed_json)
                direction=parsed.get("direction")
                tps=parsed.get("tp_list",[])
                sl=parsed.get("sl")
                entry_low=parsed["entry_range"]["low"]; entry_high=parsed["entry_range"]["high"]
                updates_json = json.loads(updates_json_str) if updates_json_str else []
                # Closure event detection
                closed = exit_event in ["TP", "SL", "BE"]
                # Monitor signals only if not closed
                if not closed:
                    # TP hit detection
                    for i,tp in enumerate(tps,1):
                        if tp-NEAR_HIT_THRESHOLD <= price <= tp+NEAR_HIT_THRESHOLD:
                            await mark_update(mid,f"TP{i}",price,"price_monitor",dest_id,fwd_id)
                    # SL hit detection (only before first TP is hit)
                    if sl and not any(h['type'].startswith('TP') for h in updates_json):
                        if ((direction=="BUY" and sl-NEAR_HIT_THRESHOLD <= price <= sl+NEAR_HIT_THRESHOLD) or
                            (direction=="SELL" and sl-NEAR_HIT_THRESHOLD <= price <= sl+NEAR_HIT_THRESHOLD)):
                            await mark_update(mid,"SL",price,"price_monitor",dest_id,fwd_id)
                    # Break-even detection (price returns to Entry after TP hit)
                    if any(h['type'].startswith('TP') for h in updates_json):
                        if entry_low-NEAR_HIT_THRESHOLD <= price <= entry_high+NEAR_HIT_THRESHOLD:
                            await mark_update(mid,"BE",price,"price_monitor",dest_id,fwd_id)
            await asyncio.sleep(LIVE_PRICE_CHECK_INTERVAL)

    async def auto_export_task():
        while True:
            now=datetime.utcnow()
            if now.hour==AUTO_EXPORT_HOUR and now.minute<AUTO_EXPORT_WINDOW_MINUTES:
                try:
                    summary_text="Daily Summary Report"
                    excel_file=export_to_excel()
                    conn=sqlite3.connect(DB_PATH); cursor=conn.cursor()
                    timeframe_ago=(datetime.utcnow()-timedelta(hours=SUMMARY_LOOKBACK_HOURS)).isoformat()
                    cursor.execute("SELECT id FROM messages WHERE source_msg_date>=?",(timeframe_ago,))
                    signal_ids=[row[0] for row in cursor.fetchall()]; conn.close()
                    charts=[]
                    for msg_id in signal_ids:
                        chart_file=generate_signal_progress_chart(msg_id)
                        if chart_file: charts.append((msg_id,chart_file))
                    channel_chart_file=generate_channel_performance_chart()
                    for admin in ADMINS:
                        await client.send_file(admin,excel_file,caption=f"📊 Daily Report — {now.strftime('%Y-%m-%d')}\n\n{summary_text}")
                        for msg_id,chart_file in charts:
                            await client.send_file(admin,chart_file,caption=f"📈 Signal Progress Chart — Message ID {msg_id}")
                        if channel_chart_file:
                            await client.send_file(admin,channel_chart_file,caption=f"📈 Channel Performance Summary — Last {SUMMARY_LOOKBACK_HOURS} Hours")
                    print(f"[AUTO-EXPORT] Sent daily report with charts at {now}")
                except Exception as e: print(f"[AUTO-EXPORT ERROR] {e}")
                await asyncio.sleep(60*65)
            else:
                await asyncio.sleep(30)

    @client.on(events.NewMessage)
    async def manual_export_handler(event):
        admin_ids=[]
        for admin in ADMINS:
            try: entity=await client.get_entity(admin); admin_ids.append(entity.id)
            except: pass
        if event.chat_id not in admin_ids: return
        if event.raw_text.lower() in ['/export','/report']:
            await event.respond("📊 Generating report with charts, please wait...")
            try:
                summary_text="Manual Summary Report"
                excel_file=export_to_excel()
                conn=sqlite3.connect(DB_PATH); cursor=conn.cursor()
                timeframe_ago=(datetime.utcnow()-timedelta(hours=SUMMARY_LOOKBACK_HOURS)).isoformat()
                cursor.execute("SELECT id FROM messages WHERE source_msg_date>=?",(timeframe_ago,))
                signal_ids=[row[0] for row in cursor.fetchall()]; conn.close()
                charts=[]
                for msg_id in signal_ids:
                    chart_file=generate_signal_progress_chart(msg_id)
                    if chart_file: charts.append((msg_id,chart_file))
                channel_chart_file=generate_channel_performance_chart()
                await client.send_file(event.chat_id,excel_file,caption=f"📊 Manual Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n{summary_text}")
                for msg_id,chart_file in charts:
                    await client.send_file(event.chat_id,chart_file,caption=f"📈 Signal Progress Chart — Message ID {msg_id}")
                if channel_chart_file:
                    await client.send_file(event.chat_id,channel_chart_file,caption=f"📈 Channel Performance Summary — Last {SUMMARY_LOOKBACK_HOURS} Hours")
                await event.respond("✅ Report and charts sent successfully.")
            except Exception as e:
                await event.respond(f"❌ Failed to generate report: {e}")

    asyncio.create_task(live_price_monitor_task())
    asyncio.create_task(auto_export_task())
    await client.run_until_disconnected()

# ---------------- RUN BOT ---------------- #
def run_bot():
    asyncio.run(main())