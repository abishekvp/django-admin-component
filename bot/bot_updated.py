import asyncio
from telethon import TelegramClient, events
from datetime import datetime, timedelta
from django.utils.timezone import make_aware
import re, sqlite3, json, requests
from io import BytesIO
from app.models import GroupMessages, DeletedMessages, Updates
from app.constants import *
from asgiref.sync import sync_to_async
from app.log import log

# ---------------- CONFIGURABLE PARAMETERS ---------------- #

# DB_PATH = 'signals.db'
LIVE_PRICE_THRESHOLD = 10
DUPLICATE_TIMEFRAME_MINUTES = 60
LIVE_PRICE_CHECK_INTERVAL = 30
NEAR_HIT_THRESHOLD = 2
AUTO_EXPORT_HOUR = 0
AUTO_EXPORT_WINDOW_MINUTES = 2
SUMMARY_LOOKBACK_HOURS = 24


try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

client = TelegramClient('signal_bot', API_ID, API_HASH, loop=loop)

# ---------------- DATABASE SETUP ---------------- #
# conn = sqlite3.connect(DB_PATH)
# cursor = conn.cursor()
# cursor.execute("""
# CREATE TABLE IF NOT EXISTS messages (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     source_chat_id TEXT,
#     source_chat_username TEXT,
#     source_msg_id INTEGER,
#     source_msg_date TEXT,
#     source_msg_text TEXT,
#     forwarded_msg_id INTEGER,
#     destination_chat_id TEXT,
#     destination_chat_username TEXT,
#     forward_time TEXT,
#     parsed_json TEXT,
#     updates_json TEXT,
#     status TEXT,
#     pair TEXT,
#     direction TEXT,
#     entry_low REAL,
#     entry_high REAL,
#     tp_list TEXT,
#     sl REAL,
#     decision_reason TEXT,
#     live_price REAL,
#     exit_event TEXT
# )
# """)
# cursor.execute("""
# CREATE TABLE IF NOT EXISTS updates (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     message_id INTEGER,
#     event_type TEXT,
#     event_price REAL,
#     event_time TEXT,
#     detected_by TEXT,
#     FOREIGN KEY(message_id) REFERENCES messages(id)
# )
# """)
# conn.commit()
# conn.close()

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
    # conn = sqlite3.connect(DB_PATH)
    # cursor = conn.cursor()
    # cursor.execute("""
    #     INSERT INTO messages (
    #         source_chat_id, source_chat_username, source_msg_id, source_msg_date,
    #         source_msg_text, forwarded_msg_id, destination_chat_id, destination_chat_username,
    #         forward_time, parsed_json, updates_json, status, pair, direction,
    #         entry_low, entry_high, tp_list, sl, decision_reason, live_price, exit_event
    #     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    # """,(event.chat_id,f"@{event.chat.username}" if event.chat.username else "",event.id,event.message.date.isoformat(),event.message.text,forwarded_msg_id,DESTINATION,DESTINATION,datetime.utcnow().isoformat(),json.dumps(parsed),json.dumps([]),status,parsed['pair'],parsed['direction'],parsed['entry_range']['low'],parsed['entry_range']['high'],",".join([str(tp) for tp in parsed['tp_list']]),parsed['sl'],reason,live_price,exit_event))
    GroupMessages.objects.create(
        group_id=str(event.chat_id),
        group_username=f"@{event.chat.username}" if event.chat.username else "",
        message_id=str(event.id),
        message=event.message.text,
        parsed_message=json.dumps(parsed),
        status=status,
        entry_low=str(parsed.get('entry_range', {}).get('low')),
        entry_high=str(parsed.get('entry_range', {}).get('high')),
        tp_list=",".join([str(tp) for tp in parsed.get('tp_list', [])]),
        sl=str(parsed.get('sl')),
        decision_reason=reason,
        live_price=str(live_price),
        exit_event=exit_event
    )
    # conn.commit(); conn.close()

async def mark_update(msg_id, update_type, price, detected_by, dest_id, fwd_id):
    try:
        message = GroupMessages.objects.get(id=msg_id)
    except GroupMessages.DoesNotExist:
        return

    parsed = json.loads(message.parsed_message)
    updates = list(Updates.objects.filter(message_id=msg_id).values())
    exit_event = message.exit_event or ""

    parsed_hit = {"type": update_type, "price": price, "time": datetime.utcnow().isoformat()}
    closed = exit_event in ["TP", "SL", "BE"]

    # Closure logic
    if update_type.startswith("TP") and not closed:
        Updates.objects.create(message_id=msg_id, event_type=update_type, event_price=price,
                               event_time=datetime.utcnow().isoformat(), detected_by=detected_by)
        message.exit_event = "TP"
    elif update_type == "SL" and not closed and not any(u["event_type"].startswith("TP") for u in updates):
        Updates.objects.create(message_id=msg_id, event_type="SL", event_price=price,
                               event_time=datetime.utcnow().isoformat(), detected_by=detected_by)
        message.exit_event = "SL"
    elif update_type == "BE" and not closed:
        Updates.objects.create(message_id=msg_id, event_type="BE", event_price=price,
                               event_time=datetime.utcnow().isoformat(), detected_by=detected_by)
        message.exit_event = "BE"
    elif update_type.startswith("TP") and closed and exit_event == "TP":
        Updates.objects.create(message_id=msg_id, event_type=update_type, event_price=price,
                               event_time=datetime.utcnow().isoformat(), detected_by=detected_by)

    # Format update message
    tp_hits = Updates.objects.filter(message_id=msg_id, event_type__startswith="TP").count()
    updated_text = f"{'🟢' if parsed['direction']=='BUY' else '🔴'} {parsed['pair']} {parsed['direction']} Signal\n"
    updated_text += f"Entry: {parsed['entry_range']['low']} to {parsed['entry_range']['high']}\n"

    for i, tp in enumerate(parsed['tp_list'][:5], 1):
        hit_marker = "✅" if Updates.objects.filter(message_id=msg_id, event_type=f"TP{i}").exists() else ""
        updated_text += f"TP{i}: {tp} {hit_marker}\n"

    if parsed['sl']:
        sl_hit = "✅" if Updates.objects.filter(message_id=msg_id, event_type="SL").exists() else ""
        updated_text += f"SL: {parsed['sl']} {sl_hit}\n"

    live_price = get_live_gold_price()
    if live_price:
        updated_text += f"📊 Live Price: {live_price}\n"
    updated_text += f"🕒 Last Update: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
    updated_text += f"TP Hits so far: {tp_hits}/{len(parsed['tp_list'])}"
    if message.exit_event:
        updated_text += f"\nSignal Closed by {message.exit_event}"

    if fwd_id and dest_id:
        try:
            await client.edit_message(dest_id, fwd_id, updated_text)
        except Exception as e:
            log(f"[EDIT ERROR] {e}")

    message.parsed_message = json.dumps(parsed)
    message.save()

# # ---------------- SIGNAL PROGRESS CHART ---------------- #
# def generate_signal_progress_chart(message_id):
#     try:
#         message = GroupMessages.objects.get(id=message_id)
#     except GroupMessages.DoesNotExist:
#         return None

#     parsed = json.loads(message.parsed_message)
#     updates = list(Updates.objects.filter(message_id=message_id).values())

#     hit_events = [u for u in updates if u["event_type"].startswith("TP") or u["event_type"] in ["SL", "BE"]]
#     if not hit_events:
#         return None

#     times = [datetime.fromisoformat(u["event_time"]) for u in updates]
#     prices = [float(u["event_price"]) for u in updates]

#     if not times:
#         return None

#     plt.figure(figsize=(10, 6))
#     plt.plot(times, prices, label="Live Price", marker='o')
#     for i, tp in enumerate(parsed.get("tp_list", []), 1):
#         plt.hlines(tp, times[0], times[-1], colors='green', linestyles='dashed', label=f"TP{i}")
#     if parsed.get("sl"):
#         plt.hlines(parsed["sl"], times[0], times[-1], colors='red', linestyles='dashed', label="SL")
#     plt.xlabel("Time")
#     plt.ylabel("Price")
#     plt.title(f"{parsed['pair']} {parsed['direction']} Signal Progress")
#     plt.legend()
#     plt.grid(True)
#     plt.tight_layout()
#     output = BytesIO()
#     plt.savefig(output, format='png')
#     plt.close()
#     output.seek(0)
#     return output

# ---------------- CHANNEL PERFORMANCE CHART ---------------- #
def generate_channel_performance_chart(hours_lookback=24):
    since_time = datetime.utcnow() - timedelta(hours=hours_lookback)
    messages = GroupMessages.objects.filter(timestamp__gte=since_time)
    channel_stats = {}

    for msg in messages:
        updates = Updates.objects.filter(message_id=msg.id)
        tp_hits = updates.filter(event_type__startswith="TP").count()
        channel_stats[msg.group_username] = channel_stats.get(msg.group_username, 0) + tp_hits

    if not channel_stats:
        return None

    plt.figure(figsize=(10, 6))
    plt.bar(channel_stats.keys(), channel_stats.values())
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
    qs = GroupMessages.objects.all().values()
    df = pd.DataFrame(qs)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output

@sync_to_async
def get_recent_signals(timeframe_ago):
    # ORM equivalent of: SELECT direction, entry_low, entry_high, source_chat_username FROM messages WHERE status='active' AND source_msg_date >= ?
    return list(
        GroupMessages.objects.filter(
            status='active',
            timestamp__gte=timeframe_ago
        ).values_list('parsed_message', 'entry_low', 'entry_high', 'group_username')
    )

@sync_to_async
def save_message(parsed, event, sent_id, live_price, status='active', reason=''):
    GroupMessages.objects.create(
        group_id=str(event.chat_id),
        group_username=event.chat.username or "",
        message_id=str(event.id),
        message=event.message.text,
        parsed_message=str(parsed),
        status=status,
        entry_low=str(parsed["entry_range"]["low"]),
        entry_high=str(parsed["entry_range"]["high"]),
        tp_list=str(parsed.get("tp_list", [])),
        sl=str(parsed.get("sl", "")),
        decision_reason=reason,
        live_price=str(live_price),
        exit_event='',
    )

# ---------------- MAIN FUNCTION ---------------- #
async def main():
    await client.start(phone=PHONE)

    @client.on(events.NewMessage)
    async def handler(event):
        chat = await event.get_chat()
        username = chat.username or ""
        if username.lower() not in [s.replace('@', '').lower() for s in SOURCES]:
            return

        parsed = parse_signal(event.message.text)
        if not parsed:
            return

        live_price = get_live_gold_price()
        entry_low, entry_high = parsed["entry_range"]["low"], parsed["entry_range"]["high"]

        # --- Skip if live price outside threshold ---
        if live_price is not None and not (entry_low - LIVE_PRICE_THRESHOLD <= live_price <= entry_high + LIVE_PRICE_THRESHOLD):
            await save_message(parsed, event, None, live_price, "skipped", "price out of range")
            return

        # --- Get recent signals using ORM ---
        timeframe_ago = make_aware(datetime.utcnow() - timedelta(minutes=DUPLICATE_TIMEFRAME_MINUTES))
        recent_signals = await get_recent_signals(timeframe_ago)

        duplicate_found = False
        conflict_found = False
        conflict_info = ""

        for dir_existing, low_existing, high_existing, src_existing in recent_signals:
            dir_existing_value = eval(dir_existing).get("direction") if isinstance(dir_existing, str) else dir_existing.get("direction")
            if ranges_overlap(entry_low, entry_high, float(low_existing), float(high_existing)):
                if dir_existing_value == parsed["direction"]:
                    duplicate_found = True
                    break
                else:
                    conflict_found = True
                    conflict_info = f"Conflict with {src_existing} ({dir_existing_value})"
                    break

        if duplicate_found:
            await save_message(parsed, event, None, live_price, "skipped", "duplicate")
            return

        if conflict_found:
            await save_message(parsed, event, None, live_price, "skipped", "conflict")
            for admin in ADMINS:
                await client.send_message(
                    admin,
                    f"⚠ Conflicting signal from {event.chat.username} ({parsed['direction']}) for range {entry_low}-{entry_high}.\n{conflict_info}"
                )
            return

        # --- Send message and save record ---
        formatted_msg = format_signal(parsed, live_price)
        sent = await client.send_message(DESTINATION, formatted_msg)
        await save_message(parsed, event, sent.id, live_price)

    @client.on(events.MessageDeleted)
    async def deleted_handler(event):
        deleted_ids = event.deleted_ids
        if not deleted_ids:
            return

        messages = GroupMessages.objects.filter(message_id__in=deleted_ids, status='active')
        for msg in messages:
            try:
                await client.delete_messages(msg.group_id, msg.message_id)
                msg.status = 'deleted'
                msg.save()
                DeletedMessages.objects.create(
                    group_id=msg.group_id,
                    group_username=msg.group_username,
                    message_id=msg.message_id,
                    message=msg.message
                )
                log(f"[DELETED] Forwarded message {msg.message_id} removed, saved in DB")
            except Exception as e:
                log(f"[DELETE ERROR] {e}")

    async def live_price_monitor_task():
        while True:
            price = get_live_gold_price()
            if not price:
                await asyncio.sleep(LIVE_PRICE_CHECK_INTERVAL)
                continue

            # Fetch active + deleted signals
            messages = list(GroupMessages.objects.filter(status__in=["active", "deleted"]))

            for msg in messages:
                try:
                    direction = json.loads(msg.parsed_message).get("direction")
                    tps = json.loads(msg.tp_list) if msg.tp_list else []
                    sl = float(msg.sl) if msg.sl else None
                    entry_low = float(msg.entry_low)
                    entry_high = float(msg.entry_high)
                    updates = list(Updates.objects.filter(message_id=msg.id).values())

                    closed = msg.exit_event in ["TP", "SL", "BE"]

                    if not closed:
                        # TP hit detection
                        for i, tp in enumerate(tps, 1):
                            tp = float(tp)
                            if tp - NEAR_HIT_THRESHOLD <= price <= tp + NEAR_HIT_THRESHOLD:
                                await mark_update(msg.id, f"TP{i}", price, "price_monitor")

                        # SL hit detection (only before TP)
                        if sl and not any(u["event_type"].startswith("TP") for u in updates):
                            if ((direction == "BUY" and sl - NEAR_HIT_THRESHOLD <= price <= sl + NEAR_HIT_THRESHOLD) or
                                (direction == "SELL" and sl - NEAR_HIT_THRESHOLD <= price <= sl + NEAR_HIT_THRESHOLD)):
                                await mark_update(msg.id, "SL", price, "price_monitor")

                        # Break-even (after TP hit, returns to entry range)
                        if any(u["event_type"].startswith("TP") for u in updates):
                            if entry_low - NEAR_HIT_THRESHOLD <= price <= entry_high + NEAR_HIT_THRESHOLD:
                                await mark_update(msg.id, "BE", price, "price_monitor")

                except Exception as e:
                    log(f"[LIVE-MONITOR ERROR] {e}")

            await asyncio.sleep(LIVE_PRICE_CHECK_INTERVAL)

    # async def auto_export_task():
    #     """Automatically export daily reports and charts."""
    #     while True:
    #         now = datetime.utcnow()
    #         if now.hour == AUTO_EXPORT_HOUR and now.minute < AUTO_EXPORT_WINDOW_MINUTES:
    #             try:
    #                 summary_text = "Daily Summary Report"
    #                 excel_file = export_to_excel()

    #                 timeframe_ago = datetime.utcnow() - timedelta(hours=SUMMARY_LOOKBACK_HOURS)
    #                 signal_ids = list(
    #                     GroupMessages.objects.filter(timestamp__gte=timeframe_ago).values_list("id", flat=True)
    #                 )

    #                 charts = []
    #                 for msg_id in signal_ids:
    #                     chart_file = generate_signal_progress_chart(msg_id)
    #                     if chart_file:
    #                         charts.append((msg_id, chart_file))

    #                 channel_chart_file = generate_channel_performance_chart()

    #                 for admin in ADMINS:
    #                     await client.send_file(
    #                         admin,
    #                         excel_file,
    #                         caption=f"📊 Daily Report — {now.strftime('%Y-%m-%d')}\n\n{summary_text}"
    #                     )
    #                     for msg_id, chart_file in charts:
    #                         await client.send_file(
    #                             admin,
    #                             chart_file,
    #                             caption=f"📈 Signal Progress Chart — Message ID {msg_id}"
    #                         )
    #                     if channel_chart_file:
    #                         await client.send_file(
    #                             admin,
    #                             channel_chart_file,
    #                             caption=f"📈 Channel Performance Summary — Last {SUMMARY_LOOKBACK_HOURS} Hours"
    #                         )

    #                 log(f"[AUTO-EXPORT] Sent daily report with charts at {now}")
    #             except Exception as e:
    #                 log(f"[AUTO-EXPORT ERROR] {e}")
    #             await asyncio.sleep(60 * 65)
    #         else:
    #             await asyncio.sleep(30)

    # @client.on(events.NewMessage)
    # async def manual_export_handler(event):
    #     """Admin command handler for manual report generation."""
    #     admin_ids = []
    #     for admin in ADMINS:
    #         try:
    #             entity = await client.get_entity(admin)
    #             admin_ids.append(entity.id)
    #         except:
    #             pass

    #     if event.chat_id not in admin_ids:
    #         return

    #     if event.raw_text.lower() in ["/export", "/report"]:
    #         await event.respond("📊 Generating report with charts, please wait...")
    #         try:
    #             summary_text = "Manual Summary Report"
    #             excel_file = export_to_excel()

    #             timeframe_ago = datetime.utcnow() - timedelta(hours=SUMMARY_LOOKBACK_HOURS)
    #             signal_ids = list(
    #                 GroupMessages.objects.filter(timestamp__gte=timeframe_ago).values_list("id", flat=True)
    #             )

    #             charts = []
    #             for msg_id in signal_ids:
    #                 chart_file = generate_signal_progress_chart(msg_id)
    #                 if chart_file:
    #                     charts.append((msg_id, chart_file))

    #             channel_chart_file = generate_channel_performance_chart()

    #             await client.send_file(
    #                 event.chat_id,
    #                 excel_file,
    #                 caption=f"📊 Manual Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n{summary_text}"
    #             )
    #             for msg_id, chart_file in charts:
    #                 await client.send_file(
    #                     event.chat_id,
    #                     chart_file,
    #                     caption=f"📈 Signal Progress Chart — Message ID {msg_id}"
    #                 )
    #             if channel_chart_file:
    #                 await client.send_file(
    #                     event.chat_id,
    #                     channel_chart_file,
    #                     caption=f"📈 Channel Performance Summary — Last {SUMMARY_LOOKBACK_HOURS} Hours"
    #                 )

    #             await event.respond("✅ Report and charts sent successfully.")
    #         except Exception as e:
    #             await event.respond(f"❌ Failed to generate report: {e}")

    asyncio.create_task(live_price_monitor_task())
    # asyncio.create_task(auto_export_task())
    await client.run_until_disconnected()
