from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name="index"),
    path('dashboard', views.dashboard, name="dashboard"),

    # Components
    path('index', views.index, name="index"),
    path('cp_datetime', views.cp_datetime, name="cp_datetime"),
    path('cp_bstoggle', views.cp_bstoggle, name="cp_bstoggle"),
    path('ui_typography', views.ui_typography, name="ui_typography"),
    path('ui_colors', views.ui_colors, name="ui_colors"),
    path('ui_fontawesome', views.ui_fontawesome, name="ui_fontawesome"),
    path('ui_themify', views.ui_themify, name="ui_themify"),
    path('ui_buttons', views.ui_buttons, name="ui_buttons"),
    path('ui_cards', views.ui_cards, name="ui_cards"),
    path('ui_modals', views.ui_modals, name="ui_modals"),
    path('ui_toastr', views.ui_toastr, name="ui_toastr"),
    path('tb_basic', views.tb_basic, name="tb_basic"),
    path('tb_datatables', views.tb_datatables, name="tb_datatables"),
    path('fm_control', views.fm_control, name="fm_control"),
    path('fm_ckeditor_classic', views.fm_ckeditor_classic, name="fm_ckeditor_classic"),
    path('fm_ckeditor_balloon', views.fm_ckeditor_balloon, name="fm_ckeditor_balloon"),
    path('fm_ckeditor_block', views.fm_ckeditor_block, name="fm_ckeditor_block"),
    path('fm_ckeditor_inline', views.fm_ckeditor_inline, name="fm_ckeditor_inline"),
    path('fm_ckeditor_document', views.fm_ckeditor_document, name="fm_ckeditor_document"),
    path('ch_apexcharts', views.ch_apexcharts, name="ch_apexcharts"),
    path('pg_login', views.pg_login, name="pg_login"),
    path('documentation', views.documentation, name="documentation"),
]