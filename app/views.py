from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from bot import bot_updated
import asyncio
import threading
from app.models import Log, Source, Configuration
from app.constants import DEBUG, ERROR, INFO
from app.log import log

bot_thread = None
bot_stop_event = threading.Event()

async def run_bot(stop_event):
    """Run bot logic asynchronously in a persistent loop."""
    client = bot_updated.get_client()

    try:
        await bot_updated.main()  # Run your async bot entry point
    except asyncio.CancelledError:
        log("[BOT] Cancelled.")
    except Exception as e:
        log(f"[BOT ERROR] {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
        log("[BOT] Disconnected cleanly.")


def run_bot_thread(stop_event):
    """Thread-safe entry point for asyncio bot."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot(stop_event))
    except Exception as e:
        log(f"[THREAD ERROR] {e}")
    finally:
        loop.close()


def start_bot_thread():
    """Start bot in background thread with isolated event loop."""
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
    """Gracefully stop bot."""
    global bot_thread, bot_stop_event

    if not bot_thread or not bot_thread.is_alive():
        log("[BOT] Not running.")
        return False

    bot_stop_event.set()
    bot_thread.join(timeout=5)
    log("[BOT] Stopped successfully.")
    return True


# --- Django views ---
def restart_bot(request):
    message = ""
    stop = start_bot_thread()
    if not stop:
        message += "Bot failed to stop. "
    start = start_bot_thread()
    return JsonResponse({
        "message": message + "Bot started successfully" if start else "Bot already running",
        "status": 200 if start else 409
    })

def start_bot(request):
    started = start_bot_thread()
    return JsonResponse({
        "message": "Bot started successfully" if started else "Bot already running",
        "status": 200 if started else 409
    })


def stop_bot(request):
    stopped = stop_bot_thread()
    return JsonResponse({
        "message": "Bot stopped" if stopped else "Bot not running",
        "status": 200 if stopped else 404
    })

@login_required(login_url='signin')
def dashboard(request):
    data = {
        'sources': Source.objects.all(),
        'confs': Configuration.objects.all()
    }
    return render(request, 'dashboard.html', data)

def logs(request):
    logs = Log.objects.all()
    i = len(logs) - 1
    sorted_logs = []
    while i >= 0:
        sorted_logs.append(logs[i])
        i -= 1
    return render(request, 'logs.html', {'logs': sorted_logs})

# Source Management

@login_required(login_url='signin')
def add_source(request):
    if request.method == "POST":
        source_username = "@" + str(request.POST.get('source-name')).strip()
        source_title = request.POST.get('source-title')
        Source.objects.create(username=source_username, title=source_title, is_active=True)
    return redirect('dashboard')


@login_required(login_url='signin')
def disable_source(request, source_id):
    try:
        source = Source.objects.get(id=source_id)
        source.is_active = False
        source.save()
        log(f"[source] Disabled source {source.username} (ID: {source_id})", INFO)
    except Source.DoesNotExist:
        log(f"[source ERROR] source with ID {source_id} does not exist", ERROR)
    return redirect('dashboard')

@login_required(login_url='signin')
def enable_source(request, source_id):
    try:
        source = Source.objects.get(id=source_id)
        source.is_active = True
        source.save()
        log(f"[source] Enabled source {source.username} (ID: {source_id})", INFO)
    except Source.DoesNotExist:
        log(f"[source ERROR] source with ID {source_id} does not exist", ERROR)
    return redirect('dashboard')

@login_required(login_url='signin')
def delete_source(request, source_id):
    try:
        source = Source.objects.get(id=source_id)
        source_username = source.username
        source.delete()
        log(f"[source] Deleted source {source_username} (ID: {source_id})", INFO)
    except Source.DoesNotExist:
        log(f"[source ERROR] source with ID {source_id} does not exist", ERROR)
    return redirect('dashboard')


# Configuration Management

@login_required(login_url='signin')
def add_conf(request):
    if request.method == "POST":
        conf_key = request.POST.get('conf-key')
        conf_value = request.POST.get('conf-value')
        Configuration.objects.create(key=conf_key, value=conf_value, is_active=True)
    return redirect('dashboard')


@login_required(login_url='signin')
def disable_conf(request, conf_id):
    try:
        conf = Configuration.objects.get(id=conf_id)
        conf.is_active = False
        conf.save()
        log(f"[conf] Disabled conf {conf.key} (ID: {conf_id})", INFO)
    except Configuration.DoesNotExist:
        log(f"[conf ERROR] conf with ID {conf_id} does not exist", ERROR)
    return redirect('dashboard')

@login_required(login_url='signin')
def enable_conf(request, conf_id):
    try:
        conf = Configuration.objects.get(id=conf_id)
        conf.is_active = True
        conf.save()
        log(f"[conf] Enabled conf {conf.key} (ID: {conf_id})", INFO)
    except Configuration.DoesNotExist:
        log(f"[conf ERROR] conf with ID {conf_id} does not exist", ERROR)
    return redirect('dashboard')

@login_required(login_url='signin')
def delete_conf(request, conf_id):
    try:
        conf = Configuration.objects.get(id=conf_id)
        conf_key = conf.key
        conf.delete()
        log(f"[conf] Deleted conf {conf_key} (ID: {conf_id})", INFO)
    except Configuration.DoesNotExist:
        log(f"[conf ERROR] conf with ID {conf_id} does not exist", ERROR)
    return redirect('dashboard')

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
