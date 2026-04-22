"""
Management command: verificar_cache

Valida a integridade do cache do site e remove entradas corrompidas ou
com dados obsoletos (ex: objetos deletados que ainda estão no cache).

Uso:
    python manage.py verificar_cache                  # verifica e corrige
    python manage.py verificar_cache --so-relatorio   # apenas reporta, sem alterar

Recomendado no cron a cada 6 horas:
    0 */6 * * * .../venv/bin/python .../manage.py verificar_cache --settings=core.settings.production
"""

import logging
from django.core.management.base import BaseCommand
from django.core.cache import cache

logger = logging.getLogger('cache')


class Command(BaseCommand):
    help = 'Verifica integridade do cache e remove entradas obsoletas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--so-relatorio',
            action='store_true',
            dest='so_relatorio',
            help='Apenas reporta problemas sem invalidar o cache',
        )

    def handle(self, *args, **options):
        so_relatorio = options['so_relatorio']
        problemas = []
        invalidadas = []

        self.stdout.write('=== Verificação de Cache — D\'ELLA Instore ===')

        # ── 1. Chaves simples (objetos únicos) ────────────────────────────────

        verificacoes_simples = [
            ('home_banners',              self._verificar_banners),
            ('home_mini_banners',         self._verificar_mini_banners),
            ('home_look_semana',          self._verificar_look),
            ('home_depoimentos',          self._verificar_depoimentos),
            ('home_produtos_destaque',    self._verificar_produtos_destaque),
            ('menu_categorias_ativas',    self._verificar_categorias),
            ('loja_config',               self._verificar_config_loja),
            ('guia_tabelas_medidas',      self._verificar_guia_tamanhos),
        ]

        for cache_key, verificador in verificacoes_simples:
            valor = cache.get(cache_key)
            if valor is None:
                self.stdout.write(f'  [MISS]  {cache_key}')
                continue
            erro = verificador(valor)
            if erro:
                problemas.append((cache_key, erro))
                if not so_relatorio:
                    cache.delete(cache_key)
                    invalidadas.append(cache_key)
                    self.stdout.write(self.style.WARNING(f'  [INVAL] {cache_key} — {erro}'))
                else:
                    self.stdout.write(self.style.WARNING(f'  [PROB]  {cache_key} — {erro}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'  [OK]    {cache_key}'))

        # ── 2. Chaves paginadas por slug (páginas estáticas) ──────────────────
        slugs_paginas = [
            'politica_privacidade', 'trocas_devolucoes', 'sobre',
            'termos_uso', 'perguntas_frequentes', 'meios_pagamento',
        ]
        for slug in slugs_paginas:
            key = f'pagina_estatica_{slug}'
            valor = cache.get(key)
            if valor is None:
                continue
            erro = self._verificar_pagina_estatica(valor, slug)
            if erro:
                problemas.append((key, erro))
                if not so_relatorio:
                    cache.delete(key)
                    invalidadas.append(key)
                    self.stdout.write(self.style.WARNING(f'  [INVAL] {key} — {erro}'))
                else:
                    self.stdout.write(self.style.WARNING(f'  [PROB]  {key} — {erro}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'  [OK]    {key}'))

        # ── 3. Resumo ─────────────────────────────────────────────────────────
        self.stdout.write('')
        if problemas:
            self.stdout.write(self.style.WARNING(f'{len(problemas)} problema(s) encontrado(s).'))
            if not so_relatorio:
                self.stdout.write(self.style.SUCCESS(f'{len(invalidadas)} chave(s) invalidada(s).'))
        else:
            self.stdout.write(self.style.SUCCESS('Cache íntegro. Nenhum problema encontrado.'))

    # ── Verificadores individuais ─────────────────────────────────────────────

    def _verificar_banners(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.conteudo.models import BannerPrincipal
            ids_cache = {b.pk for b in valor}
            ids_db = set(BannerPrincipal.objects.filter(pk__in=ids_cache).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} banner(s) deletado(s) no banco mas presentes no cache'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_mini_banners(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.conteudo.models import MiniBanner
            ids_cache = {b.pk for b in valor}
            ids_db = set(MiniBanner.objects.filter(pk__in=ids_cache).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} mini-banner(s) deletado(s) no banco mas presentes no cache'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_look(self, valor):
        if valor is None:
            return None
        try:
            from apps.conteudo.models import LookDaSemana
            if not LookDaSemana.objects.filter(pk=valor.pk, ativo=True).exists():
                return 'look da semana não existe mais ou foi desativado'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_depoimentos(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.produtos.models import Avaliacao
            ids_cache = {a.pk for a in valor}
            ids_db = set(Avaliacao.objects.filter(pk__in=ids_cache, aprovada=True).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} depoimento(s) removido(s) ou desaprovado(s)'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_produtos_destaque(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.produtos.models import Produto
            ids_cache = {p.pk for p in valor}
            ids_db = set(Produto.objects.filter(pk__in=ids_cache, ativo=True, destaque=True).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} produto(s) em destaque removido(s) ou desativado(s)'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_categorias(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.produtos.models import Categoria
            ids_cache = {c.pk for c in valor}
            ids_db = set(Categoria.objects.filter(pk__in=ids_cache, ativa=True, parent__isnull=True).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} categoria(s) removida(s) ou desativada(s)'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_config_loja(self, valor):
        if valor is None:
            return None
        try:
            from apps.conteudo.models import ConfiguracaoLoja
            if not ConfiguracaoLoja.objects.filter(pk=valor.pk).exists():
                return 'configuração da loja não existe mais no banco'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_guia_tamanhos(self, valor):
        if not isinstance(valor, list):
            return 'esperava lista'
        try:
            from apps.produtos.models import TabelaMedidas
            ids_cache = {t.pk for t in valor}
            ids_db = set(TabelaMedidas.objects.filter(pk__in=ids_cache, ativo=True).values_list('pk', flat=True))
            ausentes = ids_cache - ids_db
            if ausentes:
                return f'{len(ausentes)} tabela(s) de medidas removida(s) ou desativada(s)'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None

    def _verificar_pagina_estatica(self, valor, slug):
        if valor is None:
            return None
        try:
            from apps.conteudo.models import PaginaEstatica
            if not PaginaEstatica.objects.filter(pk=valor.pk, slug=slug, ativo=True).exists():
                return f'página estática "{slug}" não existe mais ou foi desativada'
        except Exception as e:
            return f'erro ao verificar: {e}'
        return None
