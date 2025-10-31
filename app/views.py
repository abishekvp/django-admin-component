from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from bot import bot_updated
import asyncio
import threading
from app.models import Log
from app.constants import DEBUG, ERROR, INFO
from app.log import log, alog
from bot.bot_onprem import run_bot as onprem_run

bot_thread = None
bot_stop_event = threading.Event()

def run_bot_thread(stop_event):
    """Run the asyncio bot loop safely inside a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot(stop_event))
    loop.close()


async def run_bot(stop_event):
    """Run the async bot logic."""
    # Run the bot's async main logic (your existing code)
    asyncio.create_task(bot_updated.main())

    # Keep checking for stop signal
    while not stop_event.is_set():
        await asyncio.sleep(1)

    await alog("[BOT] Stop signal received. Disconnecting...")
    client = bot_updated.get_client()
    if client:
        await client.disconnect()
    await alog("[BOT] Disconnected cleanly.")


def start_bot_thread():
    """Start the Telegram bot in a background thread."""
    global bot_thread, bot_stop_event

    if bot_thread and bot_thread.is_alive():
        log("[BOT] Already running.")
        return False

    bot_stop_event.clear()
    bot_thread = threading.Thread(
        target=run_bot_thread,
        args=(bot_stop_event,),
        daemon=True
    )
    bot_thread.start()
    log("[BOT] Started successfully.")
    return True


def stop_bot_thread():
    """Stop the Telegram bot gracefully."""
    global bot_thread, bot_stop_event

    if not bot_thread or not bot_thread.is_alive():
        log("[BOT] Not running.")
        return False

    bot_stop_event.set()
    bot_thread.join(timeout=5)
    log("[BOT] Stopped successfully.")
    return True

def start_bot(request):
    # started = start_bot_thread()
    onprem_run()
    # return JsonResponse({
    #     "message": "Bot started successfully" if started else "Bot already running",
    #     "status": 200 if started else 409
    # })


def stop_bot(request):
    stopped = stop_bot_thread()
    return JsonResponse({
        "message": "Bot stopped" if stopped else "Bot not running",
        "status": 200 if stopped else 404
    })

@login_required(login_url='signin')
def dashboard(request):
    return render(request, 'dashboard.html')

# Components
def index(request):
    return render(request, 'index.html')

def cp_datetime(request):
    return render(request, 'cp_datetime.html')

def cp_bstoggle(request):
    return render(request, 'cp_bstoggle.html')

def ui_typography(request):
    return render(request, 'ui_typography.html')

def ui_colors(request):
    return render(request, 'ui_colors.html')

def ui_fontawesome(request):
    return render(request, 'ui_fontawesome.html')

def ui_themify(request):
    return render(request, 'ui_themify.html')

def ui_buttons(request):
    return render(request, 'ui_buttons.html')

def ui_cards(request):
    return render(request, 'ui_cards.html')

def ui_modals(request):
    return render(request, 'ui_modals.html')

def ui_toastr(request):
    return render(request, 'ui_toastr.html')

def tb_basic(request):
    return render(request, 'tb_basic.html')

def tb_datatables(request):
    return render(request, 'tb_datatables.html')

def fm_control(request):
    return render(request, 'fm_control.html')

def fm_ckeditor_classic(request):
    return render(request, 'fm_ckeditor_classic.html')

def fm_ckeditor_balloon(request):
    return render(request, 'fm_ckeditor_balloon.html')

def fm_ckeditor_block(request):
    return render(request, 'fm_ckeditor_block.html')

def fm_ckeditor_inline(request):
    return render(request, 'fm_ckeditor_inline.html')

def fm_ckeditor_document(request):
    return render(request, 'fm_ckeditor_document.html')

def ch_apexcharts(request):
    return render(request, 'ch_apexcharts.html')

def pg_login(request):
    return render(request, 'pg_login.html')

def documentation(request):
    return render(request, 'documentation.html')
