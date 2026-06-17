"""
Auditoria de cadastro dos produtos do site D'ELLA.

Verifica:
  1. Descrição vazia, só com o nome ou começando com o nome repetido
  2. Composição vazia
  3. SEO Google incompleto (título, descrição ou keywords em branco)
  4. Variações de cor sem foto vinculada
  5. Cores que aparecem em variação mas só têm 1 foto cadastrada
  6. Imagens que não estão em WebP (após a conversão recente)

Rodar via:
    ./venv/bin/python manage.py shell --settings=core.settings.production < scripts/auditoria_produtos.py
"""
import os
import re
from collections import defaultdict

from apps.produtos.models import Produto, ProdutoImagem, CorPadrao


def _limpa(texto):
    texto = re.sub(r'<[^>]+>', '', texto or '').strip()
    texto = re.sub(r'&nbsp;', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


produtos = list(Produto.objects.all().order_by('nome').prefetch_related(
    'variacoes__cor', 'imagens__cor',
))
total = len(produtos)

# 1. Descrição
desc_vazia, desc_so_nome, desc_repete_nome = [], [], []
for p in produtos:
    texto = _limpa(p.descricao)
    nome = p.nome.strip().upper()
    txt_up = texto.upper()

    if not texto:
        desc_vazia.append(p)
    elif txt_up == nome or txt_up.replace(' ', '') == nome.replace(' ', '') or len(texto) <= len(p.nome) + 10:
        desc_so_nome.append((p, texto))
    elif txt_up.startswith(nome) or txt_up[:len(nome) + 5].replace(' ', '').startswith(nome.replace(' ', '')):
        desc_repete_nome.append((p, texto[:80]))

# 2. Composição
sem_composicao = [p for p in produtos if not _limpa(p.composicao)]

# 3. SEO incompleto
sem_seo = [
    p for p in produtos
    if not (p.seo_titulo or '').strip()
    or not (p.seo_descricao or '').strip()
    or not (p.seo_keywords or '').strip()
]

# 4. Variações de cor sem foto vinculada
sem_foto_por_cor = []
for p in produtos:
    cores_var = {v.cor_id for v in p.variacoes.all() if v.cor_id}
    cores_foto = {img.cor_id for img in p.imagens.all() if img.cor_id}
    faltando = cores_var - cores_foto
    if faltando:
        nomes = list(
            CorPadrao.objects.filter(pk__in=faltando).order_by('nome').values_list('nome', flat=True)
        )
        sem_foto_por_cor.append((p, nomes))

# 5. Cores com apenas 1 foto vinculada
cores_uma_foto = []
for p in produtos:
    contagem = defaultdict(int)
    cor_por_id = {}
    for img in p.imagens.all():
        if img.cor_id:
            contagem[img.cor_id] += 1
            cor_por_id[img.cor_id] = img.cor.nome if img.cor else f'#{img.cor_id}'
    cores_var = {v.cor_id for v in p.variacoes.all() if v.cor_id}
    cores_solo = [cor_por_id[cid] for cid, n in contagem.items() if n == 1 and cid in cores_var]
    if cores_solo:
        cores_uma_foto.append((p, sorted(cores_solo)))

# 6. Imagens não-webp
nao_webp = []
for p in produtos:
    formatos_ruins = set()
    for img in p.imagens.all():
        nome_arq = (img.imagem.name or '').lower()
        ext = os.path.splitext(nome_arq)[1].lstrip('.')
        if ext and ext != 'webp':
            formatos_ruins.add(ext)
    if formatos_ruins:
        nao_webp.append((p, sorted(formatos_ruins)))

# 7. Variacoes sem ID Bling ou SKU, separadas por produto ativo/inativo
sem_bling_ativos = []
sem_bling_inativos = []
for p in produtos:
    faltas_por_variacao = []
    for v in p.variacoes.all():
        if not v.ativa:
            continue
        sem_bling_id = not (v.bling_variacao_id or '').strip()
        sem_sku = not (v.sku_variacao or '').strip()
        if sem_bling_id or sem_sku:
            cor = v.cor.nome if v.cor_id else '-'
            tam = v.tamanho.nome if v.tamanho_id else '-'
            faltando = []
            if sem_bling_id:
                faltando.append('ID Bling')
            if sem_sku:
                faltando.append('SKU')
            faltas_por_variacao.append(f'{cor}/{tam} ({", ".join(faltando)})')
    if faltas_por_variacao:
        item = (p, faltas_por_variacao)
        if p.ativo:
            sem_bling_ativos.append(item)
        else:
            sem_bling_inativos.append(item)


def bloco(titulo, itens, render):
    print(f'\n{"=" * 70}')
    print(f'  {titulo}  →  {len(itens)} produto(s)')
    print('=' * 70)
    if not itens:
        print('  OK — nada a corrigir.')
        return
    for item in itens:
        render(item)


print(f'\nAUDITORIA SITE D\'ELLA — total cadastrado: {total} produtos')

bloco('1. DESCRIÇÃO VAZIA', desc_vazia, lambda p: print(f'  [{p.pk}] {p.nome}'))
bloco('1b. DESCRIÇÃO = SÓ O NOME / MUITO CURTA', desc_so_nome,
      lambda it: print(f'  [{it[0].pk}] {it[0].nome}  →  "{it[1]}"'))
bloco('1c. DESCRIÇÃO COMEÇA COM O NOME REPETIDO', desc_repete_nome,
      lambda it: print(f'  [{it[0].pk}] {it[0].nome}  →  "{it[1]}..."'))

bloco('2. SEM COMPOSIÇÃO', sem_composicao, lambda p: print(f'  [{p.pk}] {p.nome}'))

bloco('3. SEO GOOGLE INCOMPLETO', sem_seo, lambda p: print(
    f'  [{p.pk}] {p.nome}  →  '
    f'título:{"✗" if not (p.seo_titulo or "").strip() else "✓"} '
    f'descrição:{"✗" if not (p.seo_descricao or "").strip() else "✓"} '
    f'keywords:{"✗" if not (p.seo_keywords or "").strip() else "✓"}'
))

bloco('4. VARIAÇÃO DE COR SEM FOTO VINCULADA', sem_foto_por_cor, lambda it: print(
    f'  [{it[0].pk}] {it[0].nome}\n         Cores sem foto: {", ".join(it[1])}'
))

bloco('5. COR DE VARIAÇÃO COM APENAS 1 FOTO', cores_uma_foto, lambda it: print(
    f'  [{it[0].pk}] {it[0].nome}\n         Cores com só 1 foto: {", ".join(it[1])}'
))

bloco('6. IMAGENS FORA DO FORMATO WEBP', nao_webp, lambda it: print(
    f'  [{it[0].pk}] {it[0].nome}  →  formatos encontrados: {", ".join(it[1])}'
))

def render_bling(it):
    p, variacoes = it
    print(f'  [{p.pk}] {p.nome}  ({len(variacoes)} variacao(oes))')
    for v in variacoes:
        print(f'         {v}')

bloco('7a. VARIACOES ATIVAS SEM ID BLING OU SKU (produto ATIVO)', sem_bling_ativos, render_bling)
bloco('7b. VARIACOES ATIVAS SEM ID BLING OU SKU (produto INATIVO)', sem_bling_inativos, render_bling)

print(f'\n{"=" * 70}')
print('  RESUMO')
print('=' * 70)
print(f'  Descrição vazia ....................... {len(desc_vazia)}')
print(f'  Descrição só com o nome ............... {len(desc_so_nome)}')
print(f'  Descrição com nome repetido no início.. {len(desc_repete_nome)}')
print(f'  Sem composição ........................ {len(sem_composicao)}')
print(f'  SEO incompleto ........................ {len(sem_seo)}')
print(f'  Cor de variação sem foto .............. {len(sem_foto_por_cor)}')
print(f'  Cor de variação com só 1 foto ......... {len(cores_uma_foto)}')
print(f'  Produtos com imagem não-webp .......... {len(nao_webp)}')
print(f'  Variacoes sem ID Bling/SKU (ativo) .... {len(sem_bling_ativos)}')
print(f'  Variacoes sem ID Bling/SKU (inativo) .. {len(sem_bling_inativos)}')
