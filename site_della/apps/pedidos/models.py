import uuid
import secrets
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core_utils.sanitize import sanitize_name, sanitize_text, sanitize_address, sanitize_phone


def gerar_codigo_vendedor():
    """Mantido para compatibilidade com migrations antigas."""
    chars = string.ascii_uppercase + string.digits
    while True:
        codigo = ''.join(secrets.choice(chars) for _ in range(8))
        if not CodigoVendedor.objects.filter(codigo=codigo).exists():
            return codigo


def gerar_numero_pedido():
    """Gera número sequencial: YYYY-0001, YYYY-0002, ..."""
    ano = timezone.now().year
    prefix = f'{ano}-'
    numeros_ano = Pedido.objects.filter(numero__startswith=prefix).values_list('numero', flat=True)
    nums_usados = set()
    for n in numeros_ano:
        try:
            parte = n[len(prefix):]
            if parte.isdigit():
                nums_usados.add(int(parte))
        except (IndexError, ValueError):
            pass
    seq = 1
    while seq in nums_usados:
        seq += 1
    return f'{ano}-{seq:04d}'


class CarrinhoAbandonado(models.Model):
    """
    Snapshot do carrinho de um cliente (logado ou guest) que nao finalizou a compra.
    Gerado/atualizado cada vez que um item e adicionado ao carrinho (logados)
    ou quando o guest informa o e-mail no checkout (guests).
    """
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='carrinhos_abandonados', verbose_name='Cliente',
        null=True, blank=True,
    )
    email    = models.EmailField('E-mail', max_length=254)
    nome     = models.CharField('Nome', max_length=240, blank=True)
    telefone = models.CharField('Telefone', max_length=20, blank=True)
    itens_json = models.JSONField('Itens do carrinho')
    total = models.DecimalField('Total', max_digits=10, decimal_places=2, default=0)

    email_enviado    = models.BooleanField('E-mail enviado', default=False)
    email_enviado_em = models.DateTimeField('E-mail enviado em', null=True, blank=True)
    recuperado       = models.BooleanField('Recuperado (compra feita)', default=False)
    token            = models.UUIDField('Token de recuperacao', default=uuid.uuid4, editable=False, unique=True)

    criado_em     = models.DateTimeField('Criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name        = 'Carrinho Abandonado'
        verbose_name_plural = 'Carrinhos Abandonados'
        ordering            = ['-atualizado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['cliente'],
                condition=models.Q(cliente__isnull=False),
                name='pedidos_carrinhoabandonado_cliente_unique',
            )
        ]

    def __str__(self):
        return f'{self.email} — R$ {self.total} ({self.atualizado_em.strftime("%d/%m/%Y %H:%M")})'

    @property
    def itens(self):
        return self.itens_json or []

    @property
    def quantidade_itens(self):
        return sum(item.get('quantidade', 1) for item in self.itens)


def gerar_codigo_cupom_emitido():
    """Gera código único no formato DELLA-XXXXXX (6 caracteres alfanuméricos)."""
    chars = string.ascii_uppercase + string.digits
    while True:
        sufixo = ''.join(secrets.choice(chars) for _ in range(6))
        codigo = f'DELLA-{sufixo}'
        if not CupomEmitido.objects.filter(codigo=codigo).exists() and \
           not Cupom.objects.filter(codigo__iexact=codigo).exists():
            return codigo


class Cupom(models.Model):
    TIPO_CHOICES = [
        ('percentual', 'Percentual (%)'),
        ('fixo',       'Valor fixo (R$)'),
    ]

    ORIGEM_CHOICES = [
        ('manual',           'Manual (criado pelo admin)'),
        ('newsletter',       'Newsletter (gerado ao se inscrever)'),
        ('primeira_compra',  'Primeira compra'),
        ('aniversario',      'Aniversario'),
        ('carrinho_popup',   'Carrinho (popup de saida)'),
    ]

    codigo = models.CharField('Código', max_length=50, unique=True,
                              help_text='Para cupons manuais: código que o cliente digita no checkout. Ex: DELLA10. Para cupons-template (origem ≠ manual), serve apenas de referência interna.')
    tipo   = models.CharField('Tipo de desconto', max_length=10, choices=TIPO_CHOICES, default='percentual')
    valor  = models.DecimalField('Valor do desconto', max_digits=10, decimal_places=2,
                                  help_text='Percentual (ex: 10 = 10%) ou valor fixo em reais (ex: 30.00)')

    origem = models.CharField(
        'Origem', max_length=20, choices=ORIGEM_CHOICES, default='manual',
        help_text='Manual = cupons criados aqui no admin. Os demais são templates usados para gerar cupons únicos automaticamente para cada cliente (ex: newsletter).',
    )

    quantidade_total = models.PositiveIntegerField(
        'Quantidade total disponível', null=True, blank=True,
        help_text='Deixe em branco para uso ilimitado',
    )
    vezes_usado = models.PositiveIntegerField('Vezes usado', default=0, editable=False)

    um_por_cliente = models.BooleanField(
        'Apenas 1 uso por cliente', default=True,
        help_text='Se marcado, o mesmo CPF só pode usar este cupom uma vez',
    )

    valido_de  = models.DateField('Válido a partir de', null=True, blank=True)
    valido_ate = models.DateField('Válido até', null=True, blank=True)
    dias_validade_pos_emissao = models.PositiveSmallIntegerField(
        'Dias de validade após emissão', null=True, blank=True,
        help_text='Para templates de cupons emitidos individualmente (ex: newsletter): a validade é calculada por emissão. Quando preenchido, ignora "Válido a partir de" / "Válido até".',
    )

    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Cupom'
        verbose_name_plural = 'Cupons'
        ordering = ['-id']

    def __str__(self):
        return self.codigo

    def esta_valido(self, cpf=None):
        """Retorna (ok: bool, motivo: str)."""
        if not self.ativo:
            return False, 'Cupom inativo.'
        hoje = timezone.now().date()
        if self.valido_de and hoje < self.valido_de:
            return False, 'Cupom ainda não está vigente.'
        if self.valido_ate and hoje > self.valido_ate:
            return False, 'Cupom expirado.'
        if self.quantidade_total is not None and self.vezes_usado >= self.quantidade_total:
            return False, 'Cupom esgotado.'
        if cpf and self.um_por_cliente:
            if Pedido.objects.filter(cpf=cpf, cupom=self).exclude(status='cancelado').exists():
                return False, 'Você já utilizou este cupom.'
        return True, ''

    def calcular_desconto(self, subtotal):
        """Retorna o valor de desconto a ser aplicado sobre o subtotal."""
        from decimal import Decimal
        if self.tipo == 'percentual':
            return (Decimal(str(self.valor)) / 100 * subtotal).quantize(Decimal('0.01'))
        return min(Decimal(str(self.valor)), subtotal)


class CupomEmitido(models.Model):
    """
    Instância única de cupom emitido para um cliente específico (newsletter,
    primeira compra, aniversário, etc.). O `cupom_template` aponta para o Cupom
    que define tipo/valor/origem; cada CupomEmitido tem código único e expira
    em `expira_em` (calculado a partir de `template.dias_validade_pos_emissao`).
    """
    cupom_template = models.ForeignKey(
        'Cupom', on_delete=models.PROTECT, related_name='emitidos',
        verbose_name='Cupom template',
    )
    codigo = models.CharField('Código', max_length=20, unique=True, default=gerar_codigo_cupom_emitido,
                              help_text='Código único entregue à cliente. Formato DELLA-XXXXXX.')
    email = models.EmailField('E-mail', max_length=254, db_index=True)
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cupons_emitidos', verbose_name='Cliente',
    )

    emitido_em = models.DateTimeField('Emitido em', auto_now_add=True)
    expira_em  = models.DateTimeField('Expira em', null=True, blank=True)

    usado_em = models.DateTimeField('Usado em', null=True, blank=True)
    pedido = models.ForeignKey(
        'Pedido', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cupons_emitidos_usados', verbose_name='Pedido',
    )

    class Meta:
        verbose_name = 'Cupom emitido'
        verbose_name_plural = 'Cupons emitidos (automáticos)'
        ordering = ['-emitido_em']

    def __str__(self):
        return f'{self.codigo} ({self.email})'

    def save(self, *args, **kwargs):
        from datetime import timedelta
        if not self.expira_em and self.cupom_template_id:
            dias = self.cupom_template.dias_validade_pos_emissao
            if dias:
                base = self.emitido_em or timezone.now()
                self.expira_em = base + timedelta(days=int(dias))
        super().save(*args, **kwargs)

    @property
    def esta_expirado(self):
        return bool(self.expira_em and timezone.now() > self.expira_em)

    @property
    def esta_usado(self):
        return self.usado_em is not None

    @property
    def status(self):
        if self.esta_usado:
            return 'usado'
        if self.esta_expirado:
            return 'expirado'
        return 'valido'

    def esta_valido(self, cpf=None, cliente=None):
        """Retorna (ok: bool, motivo: str). Valida regras específicas do cupom emitido."""
        tpl = self.cupom_template
        if not tpl.ativo:
            return False, 'Cupom inativo.'
        if self.esta_usado:
            return False, 'Este cupom já foi utilizado.'
        if self.esta_expirado:
            return False, 'Cupom expirado.'

        # Vínculo por cliente: se o cupom foi emitido para uma conta específica
        # (cliente_id preenchido na emissão), apenas essa conta pode usar.
        if self.cliente_id:
            if cliente is None:
                return False, 'Este cupom está vinculado a uma conta. Faça login para utilizar.'
            if cliente.pk != self.cliente_id:
                return False, 'Este cupom é exclusivo de outra conta.'

        # Regra de não-cumulatividade por CPF.
        # Aniversário é recorrente (1 por ano calendário); demais origens valem só 1 vez na vida.
        if cpf:
            qs = (Pedido.objects
                  .filter(cpf=cpf, cupom__origem=tpl.origem)
                  .exclude(status='cancelado'))
            if tpl.origem == 'aniversario':
                qs = qs.filter(criado_em__year=timezone.now().year)
                if qs.exists():
                    return False, 'Você já utilizou um cupom de aniversário neste ano.'
            else:
                if qs.exists():
                    return False, f'Você já utilizou um cupom de {tpl.get_origem_display().lower()}.'
        return True, ''


class CodigoVendedor(models.Model):
    codigo = models.CharField('Código / Nome', max_length=50, unique=True,
                              help_text='Nome ou palavra-chave que identifica o vendedor. Ex: TINA')
    nome   = models.CharField('Nome completo', max_length=120)
    ativo  = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Código de vendedor'
        verbose_name_plural = 'Códigos de vendedor'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.codigo})'


class Pedido(models.Model):

    STATUS = [
        ('aguardando_pagamento', 'Aguardando Pagamento'),
        ('pagamento_confirmado', 'Pagamento Confirmado'),
        ('em_separacao',        'Em Separação'),
        ('pronto_retirada',     'Pronto para Retirada'),
        ('enviado',             'Enviado'),
        ('entregue',            'Entregue'),
        ('cancelado',           'Cancelado'),
        ('estornado',           'Estornado'),
    ]

    FORMAS_PAGAMENTO = [
        ('cartao_credito', 'Cartão de Crédito'),
        ('pix',            'Pix'),
        ('boleto',         'Boleto'),
    ]

    GATEWAYS = [
        ('pagseguro', 'PagSeguro'),
    ]

    numero = models.CharField('Número', max_length=20, unique=True, default=gerar_numero_pedido, db_index=True)
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name='pedidos', null=True, blank=True)

    # Dados do comprador (copiados no momento do pedido — não mudar se cliente editar perfil)
    nome_completo = models.CharField('Nome completo', max_length=240)
    email = models.EmailField('E-mail', max_length=254)
    cpf = models.CharField('CPF', max_length=11)
    telefone = models.CharField('Telefone', max_length=20, blank=True)

    # Endereço de entrega (copiado no momento do pedido)
    cep_entrega = models.CharField('CEP', max_length=8)
    logradouro = models.CharField('Logradouro', max_length=200)
    numero_entrega = models.CharField('Número', max_length=20)
    complemento = models.CharField('Complemento', max_length=100, blank=True)
    bairro = models.CharField('Bairro', max_length=100)
    cidade = models.CharField('Cidade', max_length=100)
    estado = models.CharField('Estado', max_length=2)

    # Cupom / vendedor
    cupom = models.ForeignKey(
        'Cupom', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos',
        verbose_name='Cupom',
    )
    cupom_codigo = models.CharField('Código do cupom', max_length=50, blank=True,
                                     help_text='Copiado no momento da compra')
    codigo_vendedor = models.ForeignKey(
        'CodigoVendedor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos', verbose_name='Código do vendedor',
    )
    codigo_vendedor_str = models.CharField('Código do vendedor', max_length=20, blank=True,
                                            help_text='Copiado no momento da compra')

    # Valores
    subtotal = models.DecimalField('Subtotal', max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField('Desconto', max_digits=10, decimal_places=2, default=0)
    frete = models.DecimalField('Frete', max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField('Total', max_digits=10, decimal_places=2, default=0)

    # Pagamento
    status = models.CharField('Status', max_length=30, choices=STATUS, default='aguardando_pagamento', db_index=True)
    forma_pagamento = models.CharField('Forma de pagamento', max_length=20, choices=FORMAS_PAGAMENTO, blank=True)
    gateway = models.CharField('Gateway', max_length=15, choices=GATEWAYS, blank=True)
    gateway_id = models.CharField('ID no gateway', max_length=100, blank=True)
    parcelas = models.PositiveSmallIntegerField('Parcelas', default=1)

    # Rastreamento (snapshot do consentimento no checkout, para disparo server-side
    # do purchase quando o pagamento confirma fora do browser, ex: PIX via webhook)
    consentimento_marketing = models.BooleanField('Consentiu marketing (Meta)', default=False)
    consentimento_analytics = models.BooleanField('Consentiu analise (GA4)', default=False)
    ga_client_id = models.CharField('GA4 client_id (_ga)', max_length=50, blank=True)

    # Atribuicao de campanha (snapshots do checkout — para analise de ROI por campanha)
    utm_source   = models.CharField('UTM Source',   max_length=200, blank=True)
    utm_medium   = models.CharField('UTM Medium',   max_length=200, blank=True)
    utm_campaign = models.CharField('UTM Campaign', max_length=200, blank=True)
    utm_content  = models.CharField('UTM Content',  max_length=200, blank=True)
    utm_term     = models.CharField('UTM Term',     max_length=200, blank=True)
    utm_id       = models.CharField('UTM ID',       max_length=200, blank=True)
    gclid        = models.CharField('Google Click ID (gclid)', max_length=300, blank=True)
    fbclid       = models.CharField('Meta Click ID (fbclid)',  max_length=300, blank=True)

    ga_session_id = models.CharField('GA4 session_id', max_length=50, blank=True,
                                     help_text='ID da sessao GA4 (cookie _ga_<stream>) capturado no checkout. '
                                               'Necessario para o Measurement Protocol atribuir o purchase '
                                               'a uma sessao e ao canal de origem correto.')

    # Flag de idempotencia: garante que o CAPI purchase nao seja enviado duas vezes
    # (uma pelo checkout e outra pelo webhook para cartao aprovado imediatamente)
    capi_purchase_enviado = models.BooleanField('CAPI purchase enviado', default=False)

    # Entrega
    retirada_loja = models.BooleanField('Retirar na loja', default=False)
    codigo_rastreio = models.CharField('Código de rastreio', max_length=50, blank=True)
    transportadora = models.CharField('Transportadora', max_length=80, blank=True)
    # Serviço Melhor Envio escolhido no checkout — usado para montar
    # transporte.volumes no payload do Bling (modalidade PAC=1 / SEDEX=2)
    frete_servico_id = models.CharField('ID serviço frete', max_length=20, blank=True)
    frete_prazo_dias = models.PositiveSmallIntegerField('Prazo frete (dias)', null=True, blank=True)

    # Integração Bling
    bling_pedido_id = models.CharField('ID pedido Bling', max_length=50, blank=True)
    bling_nfe_id = models.CharField('ID NF-e Bling', max_length=50, blank=True)
    nfe_chave = models.CharField('Chave NF-e', max_length=50, blank=True)

    # Integração Melhor Envio (preenchido pelo webhook quando a etiqueta é postada)
    me_order_id = models.CharField('ID pedido Melhor Envio', max_length=100, blank=True)

    # Rastreio Correios — controle de e-mails já enviados
    correios_email_saiu_entrega = models.BooleanField('E-mail "saiu p/ entrega" enviado', default=False)
    correios_entregue_em = models.DateTimeField(
        'Correios: entrega detectada em', null=True, blank=True,
        help_text='Preenchido quando o rastreio confirma entrega. Status muda p/ entregue 7 dias depois.',
    )
    avaliacao_email_enviado_em = models.DateTimeField('E-mail de avaliação enviado em', null=True, blank=True)

    observacao_cliente = models.TextField('Observação do cliente', max_length=300, blank=True)
    observacao_interna = models.TextField('Observação interna', max_length=500, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'Pedido {self.numero} — {self.nome_completo}'

    def clean(self):
        # Sanitiza campos que o cliente pode ter preenchido
        self.nome_completo = sanitize_name(self.nome_completo, max_length=240)
        self.logradouro = sanitize_address(self.logradouro)
        self.numero_entrega = sanitize_text(self.numero_entrega, max_length=20)
        self.complemento = sanitize_text(self.complemento, max_length=100)
        self.bairro = sanitize_text(self.bairro, max_length=100)
        self.cidade = sanitize_text(self.cidade, max_length=100)
        self.telefone = sanitize_phone(self.telefone)
        self.observacao_cliente = sanitize_text(self.observacao_cliente, max_length=300)

    @property
    def pode_cancelar(self):
        return self.status in ('aguardando_pagamento',)

    # ── Display e timeline pro cliente ───────────────────────────────────────
    STATUS_PUBLICO = {
        'aguardando_pagamento': 'Aguardando pagamento',
        'pagamento_confirmado': 'Em separação',
        'em_separacao':         'Em separação',
        'pronto_retirada':      'Pronto para retirada',
        'enviado':              'Enviado',
        'entregue':             'Entregue',
        'cancelado':            'Cancelado',
        'estornado':            'Estornado',
    }

    @property
    def status_publico(self):
        """Display amigável do status pro cliente (mais simples que o interno)."""
        return self.STATUS_PUBLICO.get(self.status, self.get_status_display())

    def _data_primeira_transicao_para(self, status):
        h = self.historico.filter(status_novo=status).order_by('criado_em').first()
        return h.criado_em if h else None

    @property
    def data_pago(self):
        return self._data_primeira_transicao_para('pagamento_confirmado')

    @property
    def data_envio(self):
        return self._data_primeira_transicao_para('enviado')

    @property
    def data_entrega(self):
        return self._data_primeira_transicao_para('entregue')

    @property
    def data_cancelamento(self):
        return self._data_primeira_transicao_para('cancelado')

    @property
    def pode_confirmar_entrega(self):
        """
        Mostra secao de confirmacao de entrega no painel da cliente:
        - Status enviado: cliente ainda nao recebeu (Correios nao confirmou) — pode confirmar.
        - Status entregue + ate 7 dias: janela de confirmacao explicita (desaparece por si so).
        """
        if self.status == 'enviado':
            return True
        if self.status == 'entregue':
            data = self.data_entregue
            if data:
                from django.utils import timezone
                return (timezone.now() - data).days <= 7
        return False

    @property
    def link_rastreio(self):
        """URL para rastreamento via linkcorreios.com.br."""
        if not self.codigo_rastreio:
            return ''
        return f'https://www.linkcorreios.com.br/?id={self.codigo_rastreio}'

    @property
    def avaliacao(self):
        try:
            return self.avaliacao_compra
        except Exception:
            return None

    @property
    def pode_avaliar(self):
        return self.status == 'entregue' and self.avaliacao is None

    def calcular_total(self):
        self.total = self.subtotal - self.desconto + self.frete
        return self.total


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT)
    variacao = models.ForeignKey('produtos.Variacao', on_delete=models.PROTECT, null=True, blank=True)

    # Dados copiados no momento da compra (produto pode mudar de preço depois)
    nome_produto = models.CharField('Produto', max_length=200)
    sku = models.CharField('SKU', max_length=80, blank=True)
    variacao_desc = models.CharField('Variação', max_length=100, blank=True)
    preco_unitario = models.DecimalField('Preço unitário', max_digits=10, decimal_places=2)
    quantidade = models.PositiveIntegerField('Quantidade', default=1)
    subtotal = models.DecimalField('Subtotal', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Item do pedido'
        verbose_name_plural = 'Itens do pedido'

    def __str__(self):
        return f'{self.quantidade}x {self.nome_produto}'

    @property
    def imagem_cor(self):
        """Primeira imagem da cor da variação comprada; fallback para imagem principal do produto."""
        if self.variacao_id and self.variacao.cor_id:
            imagens = self.produto.imagens_da_cor(self.variacao.cor_id)
            if imagens:
                return imagens[0]
        return self.produto.imagem_principal

    def save(self, *args, **kwargs):
        self.subtotal = self.preco_unitario * self.quantidade
        super().save(*args, **kwargs)


class HistoricoPedido(models.Model):
    """Log de todas as mudanças de status do pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='historico')
    status_anterior = models.CharField(max_length=30, blank=True)
    status_novo = models.CharField(max_length=30)
    observacao = models.CharField(max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico do pedido'
        verbose_name_plural = 'Histórico dos pedidos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.pedido.numero}: {self.status_anterior} → {self.status_novo}'


class RastreioEvento(models.Model):
    """
    Eventos recebidos via webhook do Melhor Envio.
    Usados para log e para rastrear eventos que chegaram sem match de pedido.
    """
    pedido     = models.ForeignKey(Pedido, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='rastreio_eventos')
    me_order_id = models.CharField('ID ME', max_length=100, db_index=True)
    evento      = models.CharField('Evento', max_length=50)
    tracking    = models.CharField('Código rastreio', max_length=50, blank=True)
    dados_raw   = models.JSONField('Payload raw')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Evento de Rastreio (ME)'
        verbose_name_plural = 'Eventos de Rastreio (ME)'
        ordering            = ['-criado_em']

    def __str__(self):
        pedido_str = f' | pedido {self.pedido.numero}' if self.pedido_id else ''
        return f'{self.evento} — {self.me_order_id}{pedido_str}'
