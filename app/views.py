from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse


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
