"""Distribuicao geografica dos visitantes do site.

Cidade e estado sao resolvidos no site_della no momento da visita, a partir do
IP e da base GeoLite2, e so o resultado e gravado: o IP nunca e persistido (ver
apps/analytics/services.py::_resolver_geo no site_della).

O painel conta VISITANTES, nao paginas vistas. Uma unica cliente pode gerar
dezenas de paginas numa sessao (o recorde observado foi 75), o que faria uma
pessoa muito engajada pesar como dezenas de visitantes de anuncio e distorcer
qualquer comparacao entre cidades.
"""

from django.db.models import Count

from apps.analytics.trafego import UF_BRASIL

# Nome por extenso, para a tela nao mostrar so a sigla.
NOMES_UF = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas',
    'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal',
    'ES': 'Espírito Santo', 'GO': 'Goiás', 'MA': 'Maranhão',
    'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais',
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco',
    'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima',
    'SC': 'Santa Catarina', 'SP': 'São Paulo', 'SE': 'Sergipe',
    'TO': 'Tocantins',
}

# Mapa em blocos: cada estado ocupa uma celula de mesmo tamanho, posicionada
# de forma aproximada a geografia real (linha, coluna numa grade 7x8).
#
# A escolha por blocos iguais, em vez do contorno real do Brasil, e
# deliberada: num mapa geografico a area do estado domina a leitura, e o
# Amazonas com 3 visitas ocupa 15x mais tela que o Distrito Federal com 43.
# Como aqui a pergunta e "de onde vem minha cliente", e nao "que area o estado
# cobre", o bloco de tamanho fixo compara valores com honestidade. Tambem cabe
# em tela de celular sem precisar de zoom, que e obrigatorio neste projeto.
GRADE_UF = {
    'RR': (1, 3), 'AP': (1, 5),
    'AM': (2, 3), 'PA': (2, 4), 'MA': (2, 5), 'CE': (2, 6), 'RN': (2, 7),
    'AC': (3, 1), 'RO': (3, 2), 'TO': (3, 4), 'PI': (3, 5), 'PB': (3, 6), 'PE': (3, 7),
    'MT': (4, 3), 'GO': (4, 4), 'BA': (4, 5), 'AL': (4, 6), 'SE': (4, 7),
    'MS': (5, 3), 'DF': (5, 4), 'MG': (5, 5), 'ES': (5, 6),
    'SP': (6, 4), 'RJ': (6, 5),
    'PR': (7, 3), 'SC': (7, 4), 'RS': (7, 5),
}


def visitantes_por_estado(sessoes_qs):
    """Lista de estados com contagem de visitantes, pronta para o mapa.

    Recebe um queryset de SessaoSite ja filtrado por periodo e por trafego
    real. Devolve os 27 estados (inclusive os zerados, que o mapa desenha em
    cinza) com a intensidade relativa usada na cor.
    """
    brutos = dict(
        sessoes_qs
        .filter(estado__in=UF_BRASIL)
        .values_list('estado')
        .annotate(t=Count('id'))
        .values_list('estado', 't')
    )
    maior = max(brutos.values()) if brutos else 0

    estados = []
    for uf, (linha, coluna) in GRADE_UF.items():
        total = brutos.get(uf, 0)
        estados.append({
            'uf': uf,
            'nome': NOMES_UF[uf],
            'total': total,
            # 0 a 4: faixa de cor. Escala por raiz para o segundo colocado nao
            # sumir quando Sao Paulo concentra a maior parte do volume.
            'nivel': 0 if not total or not maior else min(4, int((total / maior) ** 0.5 * 4) + 1),
            'linha': linha,
            'coluna': coluna,
        })
    return sorted(estados, key=lambda e: -e['total'])


def top_cidades(sessoes_qs, limite=12):
    """Cidades com mais visitantes, com a barra relativa ja calculada."""
    linhas = list(
        sessoes_qs
        .filter(estado__in=UF_BRASIL)
        .exclude(cidade='')
        .values('cidade', 'estado')
        .annotate(total=Count('id'))
        .order_by('-total')[:limite]
    )
    maior = linhas[0]['total'] if linhas else 0
    for linha in linhas:
        linha['pct_barra'] = round(linha['total'] / maior * 100) if maior else 0
    return linhas


def resumo_dispositivo(sessoes_qs):
    """Celular, computador e tablet, com percentual."""
    rotulos = {'mobile': 'Celular', 'desktop': 'Computador', 'tablet': 'Tablet'}
    brutos = dict(
        sessoes_qs.values_list('dispositivo').annotate(t=Count('id')).values_list('dispositivo', 't')
    )
    total = sum(brutos.values()) or 1
    return [
        {'rotulo': rotulos.get(chave, chave or 'Outro'), 'total': valor,
         'pct': round(valor / total * 100)}
        for chave, valor in sorted(brutos.items(), key=lambda x: -x[1])
        if valor
    ]
