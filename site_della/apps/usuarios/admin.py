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
    list_display = ('email', 'nome', 'sobrenome', 'telefone', 'is_active', 'recebe_newsletter', 'criado_em')
    list_filter = ('is_active', 'is_staff', 'recebe_newsletter', 'genero')
    search_fields = ('email', 'nome', 'sobrenome', 'cpf', 'telefone')
    ordering = ('-criado_em',)
    date_hierarchy = 'criado_em'

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
    list_display = ('cliente', 'apelido', 'logradouro', 'numero', 'cidade', 'estado', 'principal')
    list_filter = ('estado', 'principal', 'tipo')
    search_fields = ('cliente__email', 'cliente__nome', 'logradouro', 'bairro', 'cidade', 'cep')
    ordering = ('-principal', '-criado_em')
    raw_id_fields = ('cliente',)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'produto', 'adicionado_em')
    search_fields = ('cliente__email', 'produto__nome')
    ordering = ('-adicionado_em',)
    raw_id_fields = ('cliente', 'produto')
