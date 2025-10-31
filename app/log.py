from app.models import Log
from app.constants import *

def log(message, log_level=DEBUG):
    Log.objects.create(
        log_message=message,
        log_level=log_level
    )
