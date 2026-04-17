from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from .models import Cliente, Endereco, Wishlist

# Remove "Grupos" da seção Autenticação e Autorização padrão do Django
# e move para cá com nome em português
admin.site.unregister(Group)

@admin.register(Group)
class GrupoAdmin(GroupAdmin):
    pass


class EnderecoInline(admin.TabularInline):
    model = Endereco
    extra = 0
    fields = ('apelido', 'tipo', 'logradouro', 'numero', 'bairro', 'cidade', 'estado', 'cep', 'principal')
    readonly_fields = ('criado_em',)


@admin.register(Cliente)
class ClienteAdmin(UserAdmin):
    list_display = ('email', 'nome', 'sobrenome', 'telefone', 'is_active', 'recebe_newsletter', 'criado_em', 'acoes_linha')
    list_display_links = ('email',)
    list_filter = ('is_active', 'is_staff', 'recebe_newsletter', 'genero')
    search_fields = ('email', 'nome', 'sobrenome', 'cpf', 'telefone')
    ordering = ('-criado_em',)
    date_hierarchy = 'criado_em'

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:usuarios_cliente_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_cliente_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este cliente?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'

    fieldsets = (
        ('Acesso', {'fields': ('email', 'password')}),
        ('Dados pessoais', {'fields': ('nome', 'sobrenome', 'cpf', 'telefone', 'data_nascimento', 'genero')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Preferências', {'fields': ('recebe_newsletter',)}),
        ('Datas', {'fields': ('criado_em', 'atualizado_em'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nome', 'sobrenome', 'password1', 'password2'),
        }),
    )
    readonly_fields = ('criado_em', 'atualizado_em')

    inlines = [EnderecoInline]

    def total_pedidos(self, obj):
        return obj.pedidos.count()
    total_pedidos.short_description = 'Pedidos'


@admin.register(Endereco)
class EnderecoAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'apelido', 'logradouro', 'numero', 'cidade', 'estado', 'principal', 'acoes_linha')
    list_display_links = ('cliente',)
    list_filter = ('estado', 'principal', 'tipo')
    search_fields = ('cliente__email', 'cliente__nome', 'logradouro', 'bairro', 'cidade', 'cep')
    ordering = ('-principal', '-criado_em')
    raw_id_fields = ('cliente',)

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:usuarios_endereco_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_endereco_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este endereço?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'produto', 'adicionado_em', 'acoes_linha')
    list_display_links = ('cliente',)
    search_fields = ('cliente__email', 'produto__nome')
    ordering = ('-adicionado_em',)
    raw_id_fields = ('cliente', 'produto')

    class Media:
        js = ('admin/js/admin_linhas.js',)

    def get_actions(self, request):
        actions = super().get_actions(request)
        return {k: v for k, v in actions.items() if k == 'delete_selected'}

    def acoes_linha(self, obj):
        from django.urls import reverse
        edit_url   = reverse('admin:usuarios_wishlist_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_wishlist_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" title="Editar" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#c9a96e;color:#fff;border-radius:4px;'
            'text-decoration:none;margin-right:4px;font-size:14px;">✎</a>'
            '<a href="{}" title="Excluir" style="display:inline-flex;align-items:center;justify-content:center;'
            'width:28px;height:28px;background:#e74c3c;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:14px;" onclick="return confirm(\'Excluir este item?\')">✕</a>',
            edit_url, delete_url,
        )
    acoes_linha.short_description = 'Ações'
