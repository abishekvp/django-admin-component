import asyncio
from asgiref.sync import sync_to_async
from app.models import Log
from app.constants import *

@sync_to_async
def _save_log(message, level=DEBUG):
    Log.objects.create(log_message=message, log_level=level)

def log(message, level=DEBUG):
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(_save_log(message, level))
    except RuntimeError:
        Log.objects.create(log_message=message, log_level=level)
