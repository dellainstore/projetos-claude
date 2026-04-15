from django.apps import AppConfig


class ConteudoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.conteudo'
    verbose_name = 'Conteúdo do Site'

    def ready(self):
        """Renomeia labels de apps de terceiros no painel Django Admin."""
        from django.apps import apps as django_apps

        # AXES → Segurança (com nomes de modelos em português)
        try:
            axes_cfg = django_apps.get_app_config('axes')
            axes_cfg.verbose_name = 'Segurança'
        except LookupError:
            pass

        try:
            from axes.models import AccessAttempt, AccessFailure, AccessLog
            AccessAttempt._meta.verbose_name = 'Tentativa de acesso bloqueada'
            AccessAttempt._meta.verbose_name_plural = 'Tentativas de acesso bloqueadas'
            AccessFailure._meta.verbose_name = 'Falha de autenticação'
            AccessFailure._meta.verbose_name_plural = 'Falhas de autenticação'
            AccessLog._meta.verbose_name = 'Registro de acesso'
            AccessLog._meta.verbose_name_plural = 'Registros de acesso'
        except Exception:
            pass

        # Renomear "Autenticação e Autorização" (auth) para "Usuários e Grupos"
        try:
            auth_cfg = django_apps.get_app_config('auth')
            auth_cfg.verbose_name = 'Usuários e Grupos'
        except LookupError:
            pass

        # Renomear verbose_name dos modelos auth para português
        try:
            from django.contrib.auth.models import Group, Permission
            Group._meta.verbose_name = 'Grupo de acesso'
            Group._meta.verbose_name_plural = 'Grupos de acesso'
            Permission._meta.verbose_name = 'Permissão'
            Permission._meta.verbose_name_plural = 'Permissões'
        except Exception:
            pass
