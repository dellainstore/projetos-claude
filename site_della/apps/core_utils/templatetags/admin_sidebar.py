from copy import deepcopy

from django import template


register = template.Library()


def _sort_models(models, desired_order):
    order_map = {name: idx for idx, name in enumerate(desired_order)}
    return sorted(
        models,
        key=lambda model: (
            order_map.get(model.get('object_name'), 999),
            model.get('name', ''),
        ),
    )


@register.simple_tag
def build_admin_sidebar(app_list):
    app_map = {
        app['app_label']: deepcopy(app)
        for app in (app_list or [])
    }

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
