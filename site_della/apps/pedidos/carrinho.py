from decimal import Decimal
from django.conf import settings


CHAVE_SESSAO = 'carrinho_della'


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
            if produto.imagem_principal:
                try:
                    imagem = produto.imagem_principal.imagem.url
                except Exception:
                    pass

            self.carrinho[chave] = {
                'produto_id': produto.id,
                'variacao_id': variacao.id if variacao else None,
                'nome': produto.nome,
                'variacao_desc': str(variacao) if variacao else '',
                'preco': str(produto.preco_atual),
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
