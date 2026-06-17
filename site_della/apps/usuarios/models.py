from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.core.exceptions import ValidationError
import re
from apps.core_utils.sanitize import sanitize_name, sanitize_phone, validate_cpf


class ClienteManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('E-mail é obrigatório.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class Cliente(AbstractBaseUser, PermissionsMixin):
    """
    Usuário customizado — login por e-mail, sem username.
    Todos os campos de texto passam por sanitização no clean().
    """
    email = models.EmailField('E-mail', unique=True, max_length=254)
    nome = models.CharField('Nome', max_length=120)
    sobrenome = models.CharField('Sobrenome', max_length=120)
    cpf = models.CharField('CPF', max_length=11, blank=True, db_index=True)
    telefone = models.CharField('Telefone', max_length=20, blank=True)
    data_nascimento = models.DateField('Data de nascimento', null=True, blank=True)
    genero = models.CharField(
        'Gênero', max_length=1,
        choices=[('F', 'Feminino'), ('M', 'Masculino'), ('O', 'Outro'), ('N', 'Prefiro não informar')],
        blank=True
    )
    is_active = models.BooleanField('Ativo', default=True)
    is_staff = models.BooleanField('Admin', default=False)
    precisa_ativar = models.BooleanField('Precisa ativar conta', default=False)
    recebe_newsletter = models.BooleanField('Newsletter', default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = ClienteManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nome', 'sobrenome']

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.nome} {self.sobrenome} <{self.email}>'

    def get_full_name(self):
        return f'{self.nome} {self.sobrenome}'.strip()

    def get_short_name(self):
        return self.nome

    def get_telefone_formatado(self):
        digitos = re.sub(r'\D', '', self.telefone or '')[:11]
        if len(digitos) == 11:
            return f'({digitos[:2]}) {digitos[2]} {digitos[3:7]}-{digitos[7:]}'
        if len(digitos) == 10:
            return f'({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}'
        return self.telefone

    def campos_pendentes_cadastro(self):
        pendentes = []
        if not self.telefone:
            pendentes.append('telefone')
        if not self.data_nascimento:
            pendentes.append('data de nascimento')
        if not self.genero:
            pendentes.append('gênero')
        return pendentes

    def clean(self):
        self.nome = sanitize_name(self.nome)
        self.sobrenome = sanitize_name(self.sobrenome)
        self.telefone = sanitize_phone(self.telefone)
        if self.cpf:
            self.cpf = validate_cpf(self.cpf)
        if not self.nome:
            raise ValidationError({'nome': 'Nome inválido.'})


class Endereco(models.Model):
    TIPOS = [('residencial', 'Residencial'), ('comercial', 'Comercial'), ('outro', 'Outro')]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='enderecos')
    apelido = models.CharField('Apelido', max_length=50, default='Casa')
    tipo = models.CharField('Tipo', max_length=12, choices=TIPOS, default='residencial')
    cep = models.CharField('CEP', max_length=8)
    logradouro = models.CharField('Rua/Av.', max_length=200)
    numero = models.CharField('Número', max_length=20)
    complemento = models.CharField('Complemento', max_length=100, blank=True)
    bairro = models.CharField('Bairro', max_length=100)
    cidade = models.CharField('Cidade', max_length=100)
    estado = models.CharField('Estado', max_length=2)
    principal = models.BooleanField('Endereço principal', default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Endereço'
        verbose_name_plural = 'Endereços'
        ordering = ['-principal', '-criado_em']

    def __str__(self):
        return f'{self.logradouro}, {self.numero} — {self.cidade}/{self.estado}'

    def clean(self):
        from apps.core_utils.sanitize import sanitize_address, sanitize_cep, sanitize_text
        self.cep = sanitize_cep(self.cep)
        self.logradouro = sanitize_address(self.logradouro)
        self.numero = sanitize_text(self.numero, max_length=20)
        self.complemento = sanitize_text(self.complemento, max_length=100)
        self.bairro = sanitize_text(self.bairro, max_length=100)
        self.cidade = sanitize_text(self.cidade, max_length=100)
        self.apelido = sanitize_text(self.apelido, max_length=50)
        if self.principal and self.cliente_id:
            Endereco.objects.filter(
                cliente=self.cliente, principal=True
            ).exclude(pk=self.pk).update(principal=False)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_cep_formatado(self):
        return f'{self.cep[:5]}-{self.cep[5:]}'


class Wishlist(models.Model):
    """Produtos salvos na lista de desejos do cliente."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='wishlist_set')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.CASCADE, related_name='wishlist_set')
    adicionado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lista de desejos (produto salvo)'
        verbose_name_plural = 'Listas de desejos (produtos salvos)'
        unique_together = [['cliente', 'produto']]
        ordering = ['-adicionado_em']

    def __str__(self):
        return f'{self.cliente.email} ♥ {self.produto.nome}'


class AdminVerificacao(models.Model):
    """Rastreia a última verificação de e-mail do usuário admin (válida por 30 dias)."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_verificacao',
    )
    ultima_verificacao = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Verificação admin'
        verbose_name_plural = 'Verificações admin'

    def __str__(self):
        return f'{self.user.email} — {self.ultima_verificacao}'

    def verificado_recentemente(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.ultima_verificacao:
            return False
        return (timezone.now() - self.ultima_verificacao) < timedelta(days=30)


class AdminCodigo(models.Model):
    """Código OTP de 6 dígitos enviado por e-mail para verificação admin."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_codigos',
    )
    codigo = models.CharField(max_length=6)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    usado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Código de verificação admin'
        verbose_name_plural = 'Códigos de verificação admin'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.user.email} — {self.codigo}'
