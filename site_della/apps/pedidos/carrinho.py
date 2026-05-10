from decimal import Decimal
from django.conf import settings


CHAVE_SESSAO = 'carrinho_della'


def calcular_qtd_disponivel(variacao, qtd_desejada, qtd_no_carrinho=0):
    """Retorna a quantidade que pode ser adicionada/definida no carrinho.

    Para pronta_entrega limita ao estoque restante (estoque - qtd_no_carrinho).
    Para sob_demanda não há limite de estoque, retorna qtd_desejada.
    qtd_no_carrinho deve ser 0 ao atualizar (quantidade absoluta) e a
    quantidade atual quando somando ao que já está no carrinho.
    """
    if not variacao.pronta_entrega:
        return qtd_desejada
    disponivel = max(0, variacao.estoque - qtd_no_carrinho)
    return min(qtd_desejada, disponivel)


def _desc_variacao(variacao):
    """Retorna descrição curta da variação: 'PRETO / Tam. P'"""
    if not variacao:
        return ''
    partes = []
    if variacao.cor_id:
        partes.append(variacao.cor.nome.title())
    if variacao.tamanho_id:
        partes.append(f'Tam. {variacao.tamanho.nome}')
    if variacao.sob_demanda:
        prazo = variacao.prazo_total_adicional_dias
        partes.append(f'Sob demanda (+{prazo} dia{"s" if prazo != 1 else ""} úteis)')
    else:
        partes.append('Pronta entrega')
    return ' / '.join(partes)


class Carrinho:
    """
    Carrinho de compras baseado em sessão.
    Estrutura da sessão:
    {
        '<produto_id>_<variacao_id>': {
            'produto_id': int,
            'variacao_id': int or None,
            'nome': str,
            'preco': str (Decimal serializado),
            'quantidade': int,
            'imagem': str (url),
        },
        ...
    }
    """

    def __init__(self, request):
        self.session = request.session
        carrinho = self.session.get(CHAVE_SESSAO)
        if not carrinho:
            carrinho = self.session[CHAVE_SESSAO] = {}
        self.carrinho = carrinho

    def _chave(self, produto_id, variacao_id=None):
        return f'{produto_id}_{variacao_id or "0"}'

    def adicionar(self, produto, variacao=None, quantidade=1):
        from apps.produtos.models import Produto
        chave = self._chave(produto.id, variacao.id if variacao else None)

        if chave not in self.carrinho:
            imagem = ''
            if variacao and variacao.cor_id:
                try:
                    from apps.produtos.models import ProdutoCorFoto
                    cor_foto = ProdutoCorFoto.objects.get(produto=produto, cor_id=variacao.cor_id)
                    imagem = cor_foto.imagem.imagem.url
                except Exception:
                    pass
            if not imagem and produto.imagem_principal:
                try:
                    imagem = produto.imagem_principal.imagem.url
                except Exception:
                    pass

            self.carrinho[chave] = {
                'produto_id': produto.id,
                'variacao_id': variacao.id if variacao else None,
                'nome': produto.nome,
                'variacao_desc': _desc_variacao(variacao),
                'preco': str(variacao.preco_atual if variacao else produto.preco_atual),
                'peso': produto.peso,
                'quantidade': 0,
                'imagem': imagem,
            }

        self.carrinho[chave]['quantidade'] += quantidade
        self.salvar()

    def remover(self, chave):
        if chave in self.carrinho:
            del self.carrinho[chave]
            self.salvar()

    def atualizar(self, chave, quantidade):
        if chave in self.carrinho and quantidade > 0:
            self.carrinho[chave]['quantidade'] = quantidade
            self.salvar()

    def salvar(self):
        self.session.modified = True

    def limpar(self):
        del self.session[CHAVE_SESSAO]
        self.session.modified = True

    def get_total(self):
        return sum(
            Decimal(item['preco']) * item['quantidade']
            for item in self.carrinho.values()
        )

    def __len__(self):
        return sum(item['quantidade'] for item in self.carrinho.values())

    def __iter__(self):
        for chave, item in self.carrinho.items():
            item_copy = item.copy()
            item_copy['chave'] = chave
            item_copy['preco_decimal'] = Decimal(item['preco'])
            item_copy['subtotal'] = item_copy['preco_decimal'] * item_copy['quantidade']
            yield item_copy
