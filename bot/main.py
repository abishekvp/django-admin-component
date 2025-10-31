from telethon import TelegramClient, events
from datetime import datetime
import re

API_ID = 29246258
API_HASH = '40134ea5aefc8b36d1a7412d97b20664'
PHONE = '+917200263991'

SOURCES = [
    '@tradewithAsif07',
    '@Ahamekhan7863',
    '@FxGold_Royal_99',
    '@GoldSignalsfxtm1',
    '@PRIME_GOLD_SIGNAL',
    '@Meerbhai1953_2653',
    '@GOLDVIPSIGNALS768',
    '@testing_source'
]

DESTINATION = '@Fxaialgotraders'

client = TelegramClient('signal_bot', API_ID, API_HASH)
client.start(phone=PHONE)



def custom_signal_formatter(text):
    # Lowercase for easier matching
    lower = text.lower()
    
    # Trading Pair
    if 'xauusd' in lower or 'gold' in lower or 'xau/usd' in lower:
        pair = 'XAUUSD'
    else:
        pair = 'GOLD'  # Fallback or you can skip

    # Action
    action_match = re.search(r'\b(buy|sell)\b', lower)
    action = action_match.group(1).upper() if action_match else 'SIGNAL'

    # Entry price (any number with 4+ digits or decimals)
    entry_match = re.search(r'(entry[:\s]*|@|buy|sell)?\s*(\d{4,5}(?:\.\d{1,2})?)', lower)
    entry = entry_match.group(2) if entry_match else 'N/A'

    # Take Profits (TP)
    tp_matches = re.findall(r'(tp\d*[:\s]*|target[:\s]*|take profit[:\s]*)?(\d{4,5}(?:\.\d{1,2})?)', lower)
    tps = [m[1] for m in tp_matches]
    # Filter out entry and SL from tps
    tps = [tp for tp in tps if tp != entry]

    # Stop Loss (SL)
    sl_match = re.search(r'(sl|stop loss)[:\s]*(\d{4,5}(?:\.\d{1,2})?)', lower)
    sl = sl_match.group(2) if sl_match else 'N/A'

    # Fill missing values for formatting
    tp1 = tps[0] if len(tps) > 0 else 'N/A'
    tp2 = tps[1] if len(tps) > 1 else 'N/A'
    tp3 = tps[2] if len(tps) > 2 else 'N/A'

    emoji = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '⚡️'

    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    # Output format (edit for your style)
    output = f"""
        {emoji} {pair} {action} Signal
    """
    if entry != 'N/A':
        output += f"    Entry: {entry}\n"
    if tp1 != 'N/A':
        output += f"    TP1: {tp1}\n"
    if tp2 != 'N/A':
        output += f"    TP2: {tp2}\n"
    if tp3 != 'N/A':
        output += f"    TP3: {tp3}\n"
    if sl != 'N/A':
        output += f"    SL: {sl}\n"
    output += f"    Time: {timestamp}\n"
    return output.strip()


async def main():
    await client.start(phone=PHONE)
    print("Bot is running...")
    @client.on(events.NewMessage)
    async def handler(event):
        chat = await event.get_chat()

        if chat.username in [s.replace('@', '') for s in SOURCES] or chat.id in SOURCES:

            sent = await client.send_message(DESTINATION, custom_signal_formatter(event.message.text))

    @client.on(events.MessageDeleted())
    async def deleted_handler(event):
        pass

    await client.run_until_disconnected()

client.loop.run_until_complete(main())
