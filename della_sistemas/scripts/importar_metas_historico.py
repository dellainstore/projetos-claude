"""
Script de importação histórica de metas Jan-Jun 2026 a partir do metas_26.csv.

Executar com:
    cd /var/www/della-sistemas/projetos-claude/della_sistemas
    .venv/bin/python manage.py shell < scripts/importar_metas_historico.py

Importa MetaCanal para: show_room_sp, anaca, atacado, site_instagram
Período: Janeiro a Junho de 2026 (antes das metas individuais por vendedora)
"""

import sys
import django

# Django já está configurado ao rodar via manage.py shell

from apps.metas.models import MetaCanal

CANAL_MAP = {
    "VAREJO SHOW ROOM": "show_room_sp",
    "VAREJO ANACA":     "anaca",
    "ATACADO":          "atacado",
    "INSTAGRAM/SITE":   "site_instagram",
}

CSV_PATH = "/var/www/della-sistemas/projetos-claude/Relatorio_de_Metas/metas_26.csv"

criados = 0
atualizados = 0
erros = 0

with open(CSV_PATH, "r", encoding="utf-8") as f:
    linhas = f.readlines()

# Pula o header
for linha in linhas[1:]:
    linha = linha.strip().strip('"')
    if not linha:
        continue
    partes = linha.split(";")
    if len(partes) < 3:
        continue

    ano_mes_raw, canal_raw, meta_raw = partes[0].strip(), partes[1].strip(), partes[2].strip()

    # Ano/mes: "2026/01" ou "2026-01"
    sep = "/" if "/" in ano_mes_raw else "-"
    try:
        ano, mes = int(ano_mes_raw.split(sep)[0]), int(ano_mes_raw.split(sep)[1])
    except (ValueError, IndexError):
        print(f"  ERRO ao parsear ano_mes: {ano_mes_raw!r}")
        erros += 1
        continue

    canal_key = CANAL_MAP.get(canal_raw.upper())
    if not canal_key:
        print(f"  AVISO: canal não mapeado: {canal_raw!r} (linha: {linha!r})")
        continue

    try:
        valor = float(meta_raw)
    except ValueError:
        print(f"  ERRO ao parsear valor: {meta_raw!r}")
        erros += 1
        continue

    obj, created = MetaCanal.objects.update_or_create(
        canal=canal_key,
        ano=ano,
        mes=mes,
        defaults={"valor": valor},
    )

    if created:
        criados += 1
        print(f"  Criado : {canal_raw} → {canal_key} | {mes:02d}/{ano} | R$ {valor:,.2f}")
    else:
        atualizados += 1
        print(f"  Existia: {canal_raw} → {canal_key} | {mes:02d}/{ano} | R$ {valor:,.2f}")

print(f"\nConcluído: {criados} criados, {atualizados} já existiam, {erros} erros.")
print("MetaCanal no banco:")
for m in MetaCanal.objects.all().order_by("ano", "mes", "canal"):
    print(f"  {m.get_canal_display()} | {m.mes:02d}/{m.ano} | R$ {m.valor:,.2f}")
