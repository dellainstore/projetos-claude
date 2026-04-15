import re
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import Cliente, Endereco
from apps.core_utils.sanitize import sanitize_name, sanitize_phone, sanitize_text, validate_cpf


class LoginForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Seu e-mail',
            'autocomplete': 'email',
            'class': 'conta-input',
            'autofocus': True,
        }),
        error_messages={'required': 'Informe seu e-mail.'},
    )
    senha = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Sua senha',
            'autocomplete': 'current-password',
            'class': 'conta-input',
        }),
        error_messages={'required': 'Informe sua senha.'},
    )
    lembrar = forms.BooleanField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.usuario = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email', '').lower()
        senha = self.cleaned_data.get('senha', '')
        if email and senha:
            self.usuario = authenticate(self.request, username=email, password=senha)
            if self.usuario is None:
                raise forms.ValidationError('E-mail ou senha incorretos.')
            if not self.usuario.is_active:
                raise forms.ValidationError('Esta conta está desativada.')
        return self.cleaned_data

    def get_usuario(self):
        return self.usuario


class CadastroForm(forms.ModelForm):
    senha = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Crie uma senha (mínimo 8 caracteres)',
            'autocomplete': 'new-password',
            'class': 'conta-input',
        }),
        error_messages={'required': 'Crie uma senha.'},
    )
    confirmar_senha = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Repita a senha',
            'autocomplete': 'new-password',
            'class': 'conta-input',
        }),
        error_messages={'required': 'Confirme sua senha.'},
    )
    aceitar_termos = forms.BooleanField(
        error_messages={'required': 'Você precisa aceitar os termos para continuar.'},
    )

    class Meta:
        model = Cliente
        fields = ['nome', 'sobrenome', 'email', 'cpf', 'telefone']
        widgets = {
            'nome':      forms.TextInput(attrs={'placeholder': 'Nome', 'autocomplete': 'given-name', 'class': 'conta-input'}),
            'sobrenome': forms.TextInput(attrs={'placeholder': 'Sobrenome', 'autocomplete': 'family-name', 'class': 'conta-input'}),
            'email':     forms.EmailInput(attrs={'placeholder': 'E-mail', 'autocomplete': 'email', 'class': 'conta-input'}),
            'cpf':       forms.TextInput(attrs={'placeholder': '000.000.000-00', 'inputmode': 'numeric', 'class': 'conta-input', 'id': 'id_cadastro_cpf'}),
            'telefone':  forms.TextInput(attrs={'placeholder': '(11) 99999-9999', 'inputmode': 'tel', 'class': 'conta-input'}),
        }
        error_messages = {
            'nome':  {'required': 'Informe seu nome.'},
            'email': {'required': 'Informe seu e-mail.', 'unique': 'Já existe uma conta com este e-mail.'},
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf', '')
        if cpf:
            try:
                return validate_cpf(cpf)
            except Exception:
                raise forms.ValidationError('CPF inválido.')
        return cpf

    def clean_nome(self):
        return sanitize_name(self.cleaned_data.get('nome', ''))

    def clean_sobrenome(self):
        return sanitize_name(self.cleaned_data.get('sobrenome', ''))

    def clean_telefone(self):
        return sanitize_phone(self.cleaned_data.get('telefone', ''))

    def clean_email(self):
        return self.cleaned_data.get('email', '').lower()

    def clean_senha(self):
        senha = self.cleaned_data.get('senha', '')
        try:
            validate_password(senha)
        except Exception as e:
            raise forms.ValidationError(list(e.messages))
        return senha

    def clean(self):
        cd = super().clean()
        if cd.get('senha') and cd.get('confirmar_senha'):
            if cd['senha'] != cd['confirmar_senha']:
                self.add_error('confirmar_senha', 'As senhas não coincidem.')
        return cd

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['senha'])
        if commit:
            user.save()
        return user


class EditarPerfilForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'sobrenome', 'telefone', 'data_nascimento', 'genero']
        widgets = {
            'nome':            forms.TextInput(attrs={'class': 'conta-input', 'autocomplete': 'given-name'}),
            'sobrenome':       forms.TextInput(attrs={'class': 'conta-input', 'autocomplete': 'family-name'}),
            'telefone':        forms.TextInput(attrs={'class': 'conta-input', 'inputmode': 'tel', 'placeholder': '(11) 99999-9999'}),
            'data_nascimento': forms.DateInput(attrs={'class': 'conta-input', 'type': 'date'}, format='%Y-%m-%d'),
            'genero':          forms.Select(attrs={'class': 'conta-input conta-select'}),
        }

    def clean_nome(self):
        return sanitize_name(self.cleaned_data.get('nome', ''))

    def clean_sobrenome(self):
        return sanitize_name(self.cleaned_data.get('sobrenome', ''))

    def clean_telefone(self):
        return sanitize_phone(self.cleaned_data.get('telefone', ''))


class EnderecoForm(forms.ModelForm):
    class Meta:
        model = Endereco
        fields = ['apelido', 'tipo', 'cep', 'logradouro', 'numero', 'complemento',
                  'bairro', 'cidade', 'estado', 'principal']
        widgets = {
            'apelido':     forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Ex: Casa, Trabalho'}),
            'tipo':        forms.Select(attrs={'class': 'conta-input conta-select'}),
            'cep':         forms.TextInput(attrs={'class': 'conta-input', 'placeholder': '00000-000', 'inputmode': 'numeric', 'id': 'id_end_cep', 'maxlength': '9'}),
            'logradouro':  forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Rua / Avenida', 'id': 'id_end_logradouro'}),
            'numero':      forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Número'}),
            'complemento': forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Apto, bloco, etc.'}),
            'bairro':      forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Bairro', 'id': 'id_end_bairro'}),
            'cidade':      forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Cidade', 'id': 'id_end_cidade'}),
            'estado':      forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'UF', 'maxlength': '2', 'style': 'text-transform:uppercase', 'id': 'id_end_estado'}),
            'principal':   forms.CheckboxInput(attrs={'class': 'conta-checkbox'}),
        }

    def clean_cep(self):
        cep = re.sub(r'\D', '', self.cleaned_data.get('cep', ''))
        if len(cep) != 8:
            raise forms.ValidationError('CEP inválido.')
        return cep

    def clean_estado(self):
        return self.cleaned_data.get('estado', '').upper()[:2]


class RecuperarSenhaForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Seu e-mail cadastrado',
            'class': 'conta-input',
            'autofocus': True,
        }),
        error_messages={'required': 'Informe seu e-mail.'},
    )

    def clean_email(self):
        return self.cleaned_data.get('email', '').lower()


class NovaSenhaForm(forms.Form):
    senha = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Nova senha (mínimo 8 caracteres)',
            'autocomplete': 'new-password',
            'class': 'conta-input',
        }),
        error_messages={'required': 'Informe a nova senha.'},
    )
    confirmar_senha = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Repita a nova senha',
            'autocomplete': 'new-password',
            'class': 'conta-input',
        }),
        error_messages={'required': 'Confirme a nova senha.'},
    )

    def clean_senha(self):
        senha = self.cleaned_data.get('senha', '')
        try:
            validate_password(senha)
        except Exception as e:
            raise forms.ValidationError(list(e.messages))
        return senha

    def clean(self):
        cd = super().clean()
        if cd.get('senha') and cd.get('confirmar_senha'):
            if cd['senha'] != cd['confirmar_senha']:
                self.add_error('confirmar_senha', 'As senhas não coincidem.')
        return cd
