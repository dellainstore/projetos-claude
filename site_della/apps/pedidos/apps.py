from django.apps import AppConfig


class PedidosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pedidos'
    verbose_name = 'Pedidos'

    def ready(self):
        from . import signals  # noqa: F401
