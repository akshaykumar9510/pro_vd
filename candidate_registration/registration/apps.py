# registration/apps.py

from django.apps import AppConfig
from registration.utils.utils import create_required_directories
import os

class RegistrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registration'

    def ready(self):
        create_required_directories()
    


asdjhakdfasdf