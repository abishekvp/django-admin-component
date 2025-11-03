from telethon import TelegramClient, events
from datetime import datetime, timedelta
from django.utils.timezone import make_aware
import re, json, requests, time
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


client = None

def ensure_client():
    log("Ensuring Telegram client...")
    global client
    if client is None:
        client = TelegramClient('signal_bot', API_ID, API_HASH)
    return client

def get_client():
    return client

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

def mark_update(msg_id, update_type, price, detected_by, dest_id, fwd_id):
    try:
        message = GroupMessages.objects.get(id=msg_id)
    except GroupMessages.DoesNotExist:
        return

    parsed = json.loads(message.parsed_message)
    updates = list(Updates.objects.filter(message_id=msg_id).values())
    exit_event = message.exit_event or ""

    parsed_hit = {"type": update_type, "price": price, "time": datetime.utcnow().isoformat()}
    closed = exit_event in ["TP", "SL", "BE"]

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
            client.edit_message(dest_id, fwd_id, updated_text)
        except Exception as e:
            log(f"[EDIT ERROR] {e}")

    message.parsed_message = json.dumps(parsed)
    message.save()

# def export_to_excel():
#     import pandas as pd
#     qs = GroupMessages.objects.all().values()
#     df = pd.DataFrame(qs)
#     output = BytesIO()
#     df.to_excel(output, index=False)
#     output.seek(0)
#     return output

@sync_to_async
def get_recent_signals(timeframe_ago):
    return list(
        GroupMessages.objects.filter(
            status='active',
            timestamp__gte=timeframe_ago
        ).values_list('parsed_message', 'entry_low', 'entry_high', 'group_username')
    )

@sync_to_async
def save_message(parsed, event, sent_id, live_price, status='active', reason=''):
    log(f"[SAVE] Saving message from {event.chat.username} with status {status} due to {reason}")
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


async def main():
    log("[BOT] Starting Telegram client...")
    ensure_client()
    log("[BOT] Telegram client ensured.")
    await client.start(phone=PHONE)
    log("[BOT] Telegram client started.")
    
    @client.on(events.NewMessage)
    async def handler(event):
        log("[BOT] New message received.")
        chat = await event.get_chat()
        username = chat.username or ""
        if username.lower() not in [s.replace('@', '').lower() for s in SOURCES]:
            return

        parsed = parse_signal(event.message.text)
        if not parsed:
            return

        live_price = get_live_gold_price()
        entry_low, entry_high = parsed["entry_range"]["low"], parsed["entry_range"]["high"]

        if live_price is not None and not (entry_low - LIVE_PRICE_THRESHOLD <= live_price <= entry_high + LIVE_PRICE_THRESHOLD):
            await save_message(parsed, event, None, live_price, "skipped", "price out of range")  # ✅
            return

        timeframe_ago = make_aware(datetime.utcnow() - timedelta(minutes=DUPLICATE_TIMEFRAME_MINUTES))
        recent_signals = await get_recent_signals(timeframe_ago)  # ✅

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
            log(f"[DUPLICATE] Found duplicate signal from {event.chat.username} ({parsed['direction']}) for range {entry_low}-{entry_high}.")
            await save_message(parsed, event, None, live_price, "skipped", "duplicate")  # ✅
            return

        if conflict_found:
            await save_message(parsed, event, None, live_price, "skipped", "conflict")  # ✅
            for admin in ADMINS:
                await client.send_message(
                    admin,
                    f"⚠ Conflicting signal from {event.chat.username} ({parsed['direction']}) for range {entry_low}-{entry_high}.\n{conflict_info}"
                )
            return

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
                client.delete_messages(msg.group_id, msg.message_id)
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

    await client.run_until_disconnected()
