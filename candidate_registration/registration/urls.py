from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register', views.register, name='register'),
    path('save_video', views.save_video, name='save_video'),
    path('confirmation/<str:user_id>', views.confirmation, name='confirmation'),
    path('monitor/<str:user_id>', views.monitor, name='monitor'),
    path('exam/<str:user_id>', views.exam, name='exam'),
    path('monitor_frame', views.monitor_frame, name='monitor_frame'),
    path('log_tab_switch', views.log_tab_switch, name='log_tab_switch'),
    path('log_mouse_movement', views.log_mouse_movement, name='log_mouse_movement'),
    path('detect_screen_capture', views.detect_screen_capture, name='detect_screen_capture'),
    path('log_copy_paste', views.log_copy_paste, name='log_copy_paste'),
    path('processing_status', views.processing_status, name='processing_status'),
    path('skip_processing', views.skip_processing, name='skip_processing'),
]
