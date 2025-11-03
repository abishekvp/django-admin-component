from django.db import models

class GroupMessages(models.Model):
    group_id = models.CharField(max_length=64)
    group_username = models.CharField(max_length=255)
    message_id = models.CharField(max_length=64)
    message = models.TextField()
    parsed_message = models.TextField()
    status = models.CharField(max_length=50)
    entry_low = models.CharField(max_length=32)
    entry_high = models.CharField(max_length=32)
    tp_list = models.TextField()
    sl = models.CharField(max_length=32)
    decision_reason = models.TextField()
    live_price = models.CharField(max_length=32)
    exit_event = models.CharField(max_length=32)
    timestamp = models.DateTimeField(auto_now_add=True)

class DeletedMessages(models.Model):
    group_id = models.CharField(max_length=64)
    group_username = models.CharField(max_length=255)
    message_id = models.CharField(max_length=64)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

class Updates(models.Model):
    message_id = models.IntegerField()
    event_type = models.CharField(max_length=64)
    event_price = models.CharField(max_length=32)
    event_time = models.CharField(max_length=32)
    detected_by = models.CharField(max_length=64)

class Log(models.Model):
    log_message = models.TextField()
    log_level = models.CharField(max_length=32)
    timestamp = models.DateTimeField(auto_now=True)
