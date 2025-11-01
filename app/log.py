from app.models import Log
from app.constants import *
from asgiref.sync import sync_to_async

def log(message, log_level=DEBUG):
    Log.objects.create(
        log_message=message,
        log_level=log_level
    )

async def alog(message, log_level=DEBUG):
    await sync_to_async(Log.objects.create)(
        log_message=message,
        log_level=log_level
    )
