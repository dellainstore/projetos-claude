import re
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import Cliente, Endereco
from apps.core_utils.sanitize import sanitize_name, sanitize_phone, sanitize_text, validate_cpf


class LoginForm(forms.Form):
    identificador = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={
            'placeholder': 'E-mail ou CPF',
            'autocomplete': 'username',
            'class': 'conta-input',
            'autofocus': True,
        }),
        error_messages={'required': 'Informe seu e-mail ou CPF.'},
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
        identificador = (self.cleaned_data.get('identificador') or '').strip().lower()
        senha = self.cleaned_data.get('senha', '')
        if identificador and senha:
            self.usuario = authenticate(self.request, username=identificador, password=senha)
            if self.usuario is None:
                raise forms.ValidationError('E-mail/CPF ou senha incorretos.')
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
    # CPF declarado explicitamente para sobrescrever max_length=11 do model
    # (Django usa field.max_length para renderizar o atributo maxlength no HTML,
    # ignorando o maxlength colocado em Meta.widgets)
    cpf = forms.CharField(
        required=True,
        max_length=14,
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00',
            'inputmode': 'numeric',
            'class': 'conta-input',
            'id': 'id_cadastro_cpf',
        }),
        error_messages={'required': 'Informe seu CPF.'},
    )

    class Meta:
        model = Cliente
        fields = ['nome', 'email', 'cpf', 'telefone', 'data_nascimento', 'genero']
        widgets = {
            'nome':     forms.TextInput(attrs={'placeholder': 'Nome completo', 'autocomplete': 'name', 'class': 'conta-input'}),
            'email':    forms.EmailInput(attrs={'placeholder': 'E-mail', 'autocomplete': 'email', 'class': 'conta-input'}),
            'telefone': forms.TextInput(attrs={'placeholder': '(11) 99999-9999', 'inputmode': 'tel', 'class': 'conta-input'}),
            'data_nascimento': forms.DateInput(attrs={'class': 'conta-input', 'type': 'date'}),
            'genero': forms.Select(attrs={'class': 'conta-input conta-select'}),
        }
        error_messages = {
            'nome':  {'required': 'Informe seu nome completo.'},
            'email': {'required': 'Informe seu e-mail.', 'unique': 'Já existe uma conta com este e-mail.'},
            'telefone': {'required': 'Informe seu telefone.'},
            'data_nascimento': {'required': 'Informe sua data de nascimento.'},
            'genero': {'required': 'Selecione seu gênero.'},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['telefone'].required = True
        self.fields['data_nascimento'].required = False
        self.fields['genero'].required = False

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
        partes = self.cleaned_data.get('nome', '').split()
        user.nome = partes[0] if partes else ''
        user.sobrenome = ' '.join(partes[1:]) if len(partes) > 1 else ''
        user.set_password(self.cleaned_data['senha'])
        if commit:
            user.save()
        return user


class EditarPerfilForm(forms.ModelForm):
    nome_completo = forms.CharField(
        label='Nome completo',
        widget=forms.TextInput(attrs={'class': 'conta-input', 'autocomplete': 'name'}),
        error_messages={'required': 'Informe seu nome completo.'},
    )
    data_nascimento = forms.DateField(
        label='Data de nascimento',
        required=True,
        input_formats=['%d/%m/%Y'],
        widget=forms.DateInput(
            attrs={
                'class': 'conta-input',
                'placeholder': 'DD/MM/AAAA',
                'inputmode': 'numeric',
                'maxlength': '10',
                'autocomplete': 'bday',
            },
            format='%d/%m/%Y',
        ),
        error_messages={
            'required': 'Informe sua data de nascimento.',
            'invalid': 'Data invalida. Use o formato DD/MM/AAAA.',
        },
    )

    class Meta:
        model = Cliente
        fields = ['telefone', 'data_nascimento', 'genero']
        widgets = {
            'telefone': forms.TextInput(attrs={'class': 'conta-input', 'inputmode': 'tel', 'placeholder': '(11) 9 9999-9999'}),
            'genero':   forms.Select(attrs={'class': 'conta-input conta-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nome_completo'].initial = self.instance.get_full_name()
        self.initial['telefone'] = self.instance.get_telefone_formatado()
        self.fields['telefone'].required = True
        self.fields['genero'].required = True
        self.fields['telefone'].error_messages['required'] = 'Informe seu telefone.'
        self.fields['genero'].error_messages['required'] = 'Selecione seu genero.'

    def clean_nome_completo(self):
        nome_completo = sanitize_name(self.cleaned_data.get('nome_completo', ''))
        if not nome_completo:
            raise forms.ValidationError('Informe seu nome completo.')
        return nome_completo

    def clean_telefone(self):
        return sanitize_phone(self.cleaned_data.get('telefone', ''))

    def save(self, commit=True):
        user = super().save(commit=False)
        partes = self.cleaned_data.get('nome_completo', '').split()
        user.nome = partes[0] if partes else ''
        user.sobrenome = ' '.join(partes[1:]) if len(partes) > 1 else ''
        if commit:
            user.save()
        return user


class EnderecoForm(forms.ModelForm):
    # CEP declarado explicitamente para sobrescrever max_length=8 do model
    # (Django usaria maxlength="8" via Meta.widgets, mas o formato 00000-000 tem 9 chars)
    cep = forms.CharField(
        max_length=9,
        widget=forms.TextInput(attrs={
            'class': 'conta-input',
            'placeholder': '00000-000',
            'inputmode': 'numeric',
            'id': 'id_end_cep',
        }),
        error_messages={'required': 'Informe o CEP.'},
    )

    class Meta:
        model = Endereco
        fields = ['apelido', 'tipo', 'cep', 'logradouro', 'numero', 'complemento',
                  'bairro', 'cidade', 'estado', 'principal']
        widgets = {
            'apelido':     forms.TextInput(attrs={'class': 'conta-input', 'placeholder': 'Ex: Casa, Trabalho'}),
            'tipo':        forms.Select(attrs={'class': 'conta-input conta-select'}),
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


class AtivacaoForm(forms.Form):
    """Formulário usado por clientes importados para confirmar e-mail e criar senha."""
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Seu e-mail cadastrado',
            'autocomplete': 'email',
            'class': 'conta-input',
            'autofocus': True,
        }),
        error_messages={'required': 'Informe seu e-mail.'},
    )
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
