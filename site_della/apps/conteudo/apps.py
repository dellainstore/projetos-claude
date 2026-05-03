from django.apps import AppConfig


class ConteudoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.conteudo'
    verbose_name = 'Conteúdo do Site'

    def ready(self):
        """Renomeia labels de apps de terceiros no painel Django Admin."""
        from django.apps import apps as django_apps
        from django.contrib import admin as django_admin

        # AXES → Segurança (com nomes de modelos em português)
        try:
            axes_cfg = django_apps.get_app_config('axes')
            axes_cfg.verbose_name = 'Segurança'
        except LookupError:
            pass

        try:
            from axes.models import AccessAttempt
            AccessAttempt._meta.verbose_name = 'Tentativa de acesso bloqueada'
            AccessAttempt._meta.verbose_name_plural = 'Tentativas de acesso bloqueadas'
        except Exception:
            pass

        try:
            from axes.models import AccessLog
            AccessLog._meta.verbose_name = 'Histórico de logins'
            AccessLog._meta.verbose_name_plural = 'Histórico de logins'
        except Exception:
            pass

        try:
            from axes.models import AccessFailureLog
            AccessFailureLog._meta.verbose_name = 'Tentativa com senha errada'
            AccessFailureLog._meta.verbose_name_plural = 'Tentativas com senha errada'
        except Exception:
            pass

        try:
            from axes.models import AccessFailure
            AccessFailure._meta.verbose_name = 'Tentativa com senha errada'
            AccessFailure._meta.verbose_name_plural = 'Tentativas com senha errada'
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

        if getattr(django_admin.AdminSite, '_della_custom_app_list', False):
            return

        original_get_app_list = django_admin.AdminSite.get_app_list

        def _sort_models(models, desired_order):
            order_map = {name: idx for idx, name in enumerate(desired_order)}
            return sorted(
                models,
                key=lambda model: (
                    order_map.get(model.get('object_name'), 999),
                    model.get('name', ''),
                ),
            )

        def custom_get_app_list(self, request, app_label=None):
            app_list = original_get_app_list(self, request, app_label)
            app_map = {app['app_label']: app for app in app_list}

            pedidos_app = app_map.get('pedidos')
            pagamentos_app = app_map.pop('pagamentos', None)
            if pedidos_app and pagamentos_app:
                pedidos_app['models'].extend(pagamentos_app.get('models', []))
                pedidos_app['models'] = _sort_models(
                    pedidos_app['models'],
                    ['Pedido', 'Pagamento', 'Cupom', 'CodigoVendedor'],
                )

            usuarios_app = app_map.get('usuarios')
            auth_app = app_map.pop('auth', None)
            if usuarios_app and auth_app:
                grupos = [
                    model for model in auth_app.get('models', [])
                    if model.get('object_name') == 'Group'
                ]
                usuarios_app['models'].extend(grupos)
                usuarios_app['models'] = _sort_models(
                    usuarios_app['models'],
                    ['Cliente', 'Endereco', 'Wishlist', 'Group'],
                )

            if 'axes' in app_map:
                app_map['axes']['models'] = _sort_models(
                    app_map['axes'].get('models', []),
                    ['AccessAttempt', 'AccessLog', 'AccessFailureLog', 'AccessFailure'],
                )

            desired_app_order = {
                'conteudo': 0,
                'produtos': 1,
                'pedidos': 2,
                'usuarios': 3,
                'bling': 4,
                'axes': 5,
            }

            return sorted(
                app_map.values(),
                key=lambda app: (
                    desired_app_order.get(app['app_label'], 999),
                    app.get('name', ''),
                ),
            )

        django_admin.AdminSite.get_app_list = custom_get_app_list
        django_admin.AdminSite._della_custom_app_list = True
