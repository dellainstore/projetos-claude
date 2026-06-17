from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse
from apps.core_utils.admin_mixin import DellaAdminMixin
from .models import Cliente, Endereco, Wishlist


class ClienteAdminForm(forms.ModelForm):
    nome_completo = forms.CharField(label='Nome completo', max_length=200, widget=forms.TextInput(attrs={'style': 'width: 100%'}))

    class Meta:
        model = Cliente
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['nome_completo'].initial = f'{self.instance.nome} {self.instance.sobrenome}'.strip()

    def save(self, commit=True):
        partes = self.cleaned_data.get('nome_completo', '').strip().split(' ', 1)
        self.instance.nome = partes[0]
        self.instance.sobrenome = partes[1] if len(partes) > 1 else ''
        return super().save(commit)


class ClienteAdminAddForm(forms.ModelForm):
    nome_completo = forms.CharField(label='Nome completo', max_length=200, widget=forms.TextInput(attrs={'style': 'width: 100%'}))
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput)

    class Meta:
        model = Cliente
        fields = ['email', 'nome_completo', 'password1', 'password2']

    def clean(self):
        cd = super().clean()
        if cd.get('password1') and cd.get('password2') and cd['password1'] != cd['password2']:
            self.add_error('password2', 'As senhas nao coincidem.')
        return cd

    def save(self, commit=True):
        user = super().save(commit=False)
        partes = self.cleaned_data.get('nome_completo', '').strip().split(' ', 1)
        user.nome = partes[0]
        user.sobrenome = partes[1] if len(partes) > 1 else ''
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user

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
class ClienteAdmin(DellaAdminMixin, UserAdmin):
    form = ClienteAdminForm
    add_form = ClienteAdminAddForm
    list_display = ('email', 'nome_completo_fmt', 'telefone', 'is_active', 'recebe_newsletter', 'criado_em', 'acoes_linha')
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
        edit_url   = reverse('admin:usuarios_cliente_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_cliente_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este cliente?')
    acoes_linha.short_description = 'Ações'

    def nome_completo_fmt(self, obj):
        return f'{obj.nome} {obj.sobrenome}'.strip() or '—'
    nome_completo_fmt.short_description = 'Nome completo'

    fieldsets = (
        ('Acesso', {'fields': ('email', 'senha_display')}),
        ('Dados pessoais', {'fields': ('nome_completo', 'cpf', 'telefone', 'data_nascimento', 'genero')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Preferências', {'fields': ('recebe_newsletter',)}),
        ('Datas', {'fields': ('criado_em', 'atualizado_em'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nome_completo', 'password1', 'password2'),
        }),
    )
    readonly_fields = ('criado_em', 'atualizado_em', 'senha_display')
    filter_horizontal = ('groups', 'user_permissions')

    def senha_display(self, obj):
        if obj.pk:
            url = reverse('admin:auth_user_password_change', args=[obj.pk])
            return format_html(
                '<a href="{}" class="della-btn-edit" style="font-size:13px;">🔑 Alterar senha</a>',
                url,
            )
        return '—'
    senha_display.short_description = 'Senha'

    inlines = [EnderecoInline]

    def total_pedidos(self, obj):
        return obj.pedidos.count()
    total_pedidos.short_description = 'Pedidos'


@admin.register(Endereco)
class EnderecoAdmin(DellaAdminMixin, admin.ModelAdmin):
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
        edit_url   = reverse('admin:usuarios_endereco_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_endereco_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este endereço?')
    acoes_linha.short_description = 'Ações'


@admin.register(Wishlist)
class WishlistAdmin(DellaAdminMixin, admin.ModelAdmin):
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
        edit_url   = reverse('admin:usuarios_wishlist_change', args=[obj.pk])
        delete_url = reverse('admin:usuarios_wishlist_delete', args=[obj.pk])
        return self._render_acoes(obj, edit_url, delete_url, delete_confirm='Excluir este item?')
    acoes_linha.short_description = 'Ações'
