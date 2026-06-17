import threading
from django.utils.html import mark_safe

_request_local = threading.local()


class DellaAdminMixin:
    """Mixin que verifica permissões ao renderizar botões de ação na listagem."""

    def changelist_view(self, request, extra_context=None):
        _request_local.current = request
        return super().changelist_view(request, extra_context)

    def _render_acoes(self, obj, edit_url, delete_url,
                      edit_label='✎ Editar', delete_label='✕ Excluir',
                      delete_confirm='Confirma exclusão?'):
        request = getattr(_request_local, 'current', None)
        can_change = not request or self.has_change_permission(request, obj)
        can_delete = not request or self.has_delete_permission(request, obj)

        parts = []
        if can_change:
            parts.append(
                f'<a href="{edit_url}" class="della-btn-edit">{edit_label}</a>'
            )
        if can_delete:
            parts.append(
                f'<a href="{delete_url}" class="della-btn-delete"'
                f' data-confirm="{delete_confirm}">{delete_label}</a>'
            )
        elif request:
            parts.append(
                f'<span class="della-btn-no-perm"'
                f' title="Sem permissão para excluir">{delete_label}</span>'
            )
        return mark_safe(''.join(parts))
