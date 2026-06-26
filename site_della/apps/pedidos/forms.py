import re
from django import forms
from apps.core_utils.sanitize import sanitize_name, sanitize_text, sanitize_phone, validate_cpf


class CheckoutForm(forms.Form):

    # ── Contato ───────────────────────────────────────────────────────────────
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'email',
            'class': 'co-input',
            'id': 'id_email',
        }),
        error_messages={'required': 'Informe seu e-mail.'},
    )
    newsletter_optin = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'id': 'id_newsletter_optin'}),
    )

    # ── Entrega: dados pessoais ───────────────────────────────────────────────
    nome_completo = forms.CharField(
        max_length=240,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'name',
            'class': 'co-input',
            'id': 'id_nome_completo',
        }),
        error_messages={'required': 'Informe seu nome completo.'},
    )
    telefone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'tel',
            'inputmode': 'tel',
            'class': 'co-input',
            'id': 'id_telefone',
        }),
    )

    # ── Endereco de entrega ───────────────────────────────────────────────────
    cep = forms.CharField(
        max_length=9,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'postal-code',
            'inputmode': 'numeric',
            'class': 'co-input',
            'id': 'id_cep',
        }),
        error_messages={'required': 'Informe o CEP.'},
    )
    logradouro = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'street-address',
            'class': 'co-input',
            'id': 'id_logradouro',
        }),
        error_messages={'required': 'Informe o logradouro.'},
    )
    numero_entrega = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'off',
            'class': 'co-input',
            'id': 'id_numero_entrega',
        }),
        error_messages={'required': 'Informe o numero.'},
    )
    complemento = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Apartamento, bloco etc.',
            'autocomplete': 'off',
            'class': 'co-input',
            'id': 'id_complemento',
        }),
    )
    bairro = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'class': 'co-input',
            'id': 'id_bairro',
        }),
        error_messages={'required': 'Informe o bairro.'},
    )
    cidade = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'class': 'co-input',
            'id': 'id_cidade',
        }),
        error_messages={'required': 'Informe a cidade.'},
    )
    estado = forms.CharField(
        max_length=2,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'maxlength': '2',
            'style': 'text-transform:uppercase',
            'class': 'co-input',
            'id': 'id_estado',
        }),
        error_messages={'required': 'Informe o estado.'},
    )

    # ── Entrega (frete) ───────────────────────────────────────────────────────
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
            ('cartao_credito', 'Cartao de Credito'),
            ('pix',            'Pix'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'sr-only'}),
        initial='cartao_credito',
        error_messages={'required': 'Selecione a forma de pagamento.'},
    )
    parcelas = forms.ChoiceField(
        choices=[(i, f'{i}x') for i in range(1, 6)],
        required=False,
        initial='1',
        widget=forms.Select(attrs={'class': 'co-input co-select', 'id': 'id_parcelas'}),
    )

    # ── Informacoes adicionais (CPF/CNPJ) ────────────────────────────────────
    cpf = forms.CharField(
        max_length=18,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'class': 'co-input',
            'id': 'id_cpf',
        }),
        error_messages={'required': 'Informe seu CPF ou CNPJ.'},
    )

    # ── Cupom / Vendedor ──────────────────────────────────────────────────────
    cupom_codigo = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Codigo do cupom (opcional)',
            'autocomplete': 'off',
            'class': 'checkout-input checkout-input--cupom',
            'id': 'id_cupom_codigo',
        }),
    )
    codigo_vendedor_codigo = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Codigo do vendedor (opcional)',
            'autocomplete': 'off',
            'class': 'checkout-input checkout-input--vendedor',
            'id': 'id_codigo_vendedor_codigo',
        }),
    )

    # ── Observacao ────────────────────────────────────────────────────────────
    observacao = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Observacoes sobre o pedido (opcional)',
            'rows': 3,
            'class': 'checkout-input checkout-textarea',
        }),
    )

    def clean_cpf(self):
        raw = self.cleaned_data.get('cpf', '')
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 11:
            try:
                return validate_cpf(raw)
            except Exception:
                raise forms.ValidationError('CPF invalido.')
        elif len(digits) == 14:
            return digits
        raise forms.ValidationError('CPF/CNPJ invalido.')

    def clean_cep(self):
        cep = re.sub(r'\D', '', self.cleaned_data.get('cep', ''))
        if len(cep) != 8:
            raise forms.ValidationError('CEP invalido.')
        return cep

    def clean_nome_completo(self):
        return sanitize_name(self.cleaned_data.get('nome_completo', ''), max_length=240)

    def clean_complemento(self):
        return sanitize_text(self.cleaned_data.get('complemento', ''), max_length=100)

    def clean_observacao(self):
        return sanitize_text(self.cleaned_data.get('observacao', ''), max_length=300)

    def clean_telefone(self):
        return sanitize_phone(self.cleaned_data.get('telefone', ''))

    def clean_estado(self):
        return self.cleaned_data.get('estado', '').upper()[:2]
