from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from .audit import connect_signals
        connect_signals()
        from .identity import connect_name_signals
        connect_name_signals()
