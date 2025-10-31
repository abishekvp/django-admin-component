from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(GroupMessages)
admin.site.register(DeletedMessages)
admin.site.register(Updates)
admin.site.register(Log)