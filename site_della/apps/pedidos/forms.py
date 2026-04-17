import re
from django import forms
from apps.core_utils.sanitize import sanitize_text, sanitize_phone, validate_cpf


class CheckoutForm(forms.Form):
    """Formulário único do checkout: dados pessoais + endereço de entrega."""

    # ── Dados pessoais ────────────────────────────────────────────────────────
    nome_completo = forms.CharField(
        max_length=240,
        widget=forms.TextInput(attrs={
            'placeholder': 'Nome completo',
            'autocomplete': 'name',
            'class': 'checkout-input',
        }),
        error_messages={'required': 'Informe seu nome completo.'},
    )
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': 'E-mail',
            'autocomplete': 'email',
            'class': 'checkout-input',
        }),
        error_messages={'required': 'Informe seu e-mail.'},
    )
    cpf = forms.CharField(
        max_length=14,
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'class': 'checkout-input',
            'id': 'id_cpf',
        }),
        error_messages={'required': 'Informe seu CPF.'},
    )
    telefone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '(11) 99999-9999',
            'autocomplete': 'tel',
            'inputmode': 'tel',
            'class': 'checkout-input',
        }),
    )

    # ── Endereço de entrega ───────────────────────────────────────────────────
    cep = forms.CharField(
        max_length=9,
        widget=forms.TextInput(attrs={
            'placeholder': '00000-000',
            'autocomplete': 'postal-code',
            'inputmode': 'numeric',
            'class': 'checkout-input',
            'id': 'id_cep',
        }),
        error_messages={'required': 'Informe o CEP.'},
    )
    logradouro = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'placeholder': 'Rua / Avenida',
            'autocomplete': 'street-address',
            'class': 'checkout-input',
            'id': 'id_logradouro',
        }),
        error_messages={'required': 'Informe o logradouro.'},
    )
    numero_entrega = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': 'Número',
            'autocomplete': 'off',
            'class': 'checkout-input',
        }),
        error_messages={'required': 'Informe o número.'},
    )
    complemento = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Complemento (opcional)',
            'autocomplete': 'off',
            'class': 'checkout-input',
        }),
    )
    bairro = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Bairro',
            'class': 'checkout-input',
            'id': 'id_bairro',
        }),
        error_messages={'required': 'Informe o bairro.'},
    )
    cidade = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Cidade',
            'class': 'checkout-input',
            'id': 'id_cidade',
        }),
        error_messages={'required': 'Informe a cidade.'},
    )
    estado = forms.CharField(
        max_length=2,
        widget=forms.TextInput(attrs={
            'placeholder': 'UF',
            'maxlength': '2',
            'style': 'text-transform:uppercase',
            'class': 'checkout-input',
            'id': 'id_estado',
        }),
        error_messages={'required': 'Informe o estado.'},
    )

    # ── Entrega ───────────────────────────────────────────────────────────────
    opcao_frete = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_opcao_frete'}),
    )
    servico_frete_nome = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_servico_frete_nome'}),
    )
    valor_frete = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.HiddenInput(attrs={'id': 'id_valor_frete'}),
    )
    prazo_frete = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_prazo_frete'}),
    )

    # ── Pagamento ─────────────────────────────────────────────────────────────
    forma_pagamento = forms.ChoiceField(
        choices=[
            ('pix',            'Pix'),
            ('cartao_credito', 'Cartão de Crédito'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'pagamento-radio'}),
        initial='pix',
        error_messages={'required': 'Selecione a forma de pagamento.'},
    )
    parcelas = forms.ChoiceField(
        choices=[(i, f'{i}x') for i in range(1, 13)],
        required=False,
        initial='1',
        widget=forms.Select(attrs={'class': 'checkout-input checkout-select', 'id': 'id_parcelas'}),
    )

    # ── Cupom / Vendedor ──────────────────────────────────────────────────────
    cupom_codigo = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Código do cupom (opcional)',
            'autocomplete': 'off',
            'class': 'checkout-input checkout-input--cupom',
            'id': 'id_cupom_codigo',
            'style': 'text-transform:uppercase',
        }),
    )
    codigo_vendedor_codigo = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Código do vendedor (opcional)',
            'autocomplete': 'off',
            'class': 'checkout-input checkout-input--vendedor',
            'id': 'id_codigo_vendedor_codigo',
            'style': 'text-transform:uppercase',
        }),
    )

    # ── Observação ────────────────────────────────────────────────────────────
    observacao = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Observações sobre o pedido (opcional)',
            'rows': 3,
            'class': 'checkout-input checkout-textarea',
        }),
    )

    def clean_cpf(self):
        cpf_raw = self.cleaned_data.get('cpf', '')
        try:
            return validate_cpf(cpf_raw)
        except Exception:
            raise forms.ValidationError('CPF inválido.')

    def clean_cep(self):
        cep = re.sub(r'\D', '', self.cleaned_data.get('cep', ''))
        if len(cep) != 8:
            raise forms.ValidationError('CEP inválido.')
        return cep

    def clean_nome_completo(self):
        return sanitize_text(self.cleaned_data.get('nome_completo', ''), max_length=240)

    def clean_complemento(self):
        return sanitize_text(self.cleaned_data.get('complemento', ''), max_length=100)

    def clean_observacao(self):
        return sanitize_text(self.cleaned_data.get('observacao', ''), max_length=300)

    def clean_telefone(self):
        return sanitize_phone(self.cleaned_data.get('telefone', ''))

    def clean_estado(self):
        return self.cleaned_data.get('estado', '').upper()[:2]
