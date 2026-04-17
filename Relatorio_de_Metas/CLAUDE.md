# Relatório de Metas — D'Ella Sistemas

Gera um PDF com o relatório de metas de faturamento por loja/canal, cruzando as metas manuais (CSV) com as vendas reais (CSV do Bling).

---

## Como funciona

### Entradas

| Arquivo | Localização | Descrição |
|---|---|---|
| `metas_<YY>.csv` | pasta do script (`Relatorio_de_Metas/`) | Metas mensais por canal, preenchidas manualmente |
| `vendas_atendidas_<ANO>.csv` | `/var/www/della-sistemas/data/Relatorio de Vendas Atendidas/` | Exportado automaticamente pelo job do Bling |

### Saída

| Arquivo | Localização |
|---|---|
| `Metas_Faturamento_<ANO>.pdf` | pasta do script (`Relatorio_de_Metas/`) |

---

## Como rodar

```bash
# Da pasta do projeto:
cd /var/www/della-sistemas/projetos-claude/Relatorio_de_Metas

# Gerar relatório do ano atual (2026):
python metas.py 2026

# Gerar relatório de 2025:
python metas.py 2025
```

---

## Canais / Lojas mapeados

| Canal no CSV de metas | Situações no CSV de vendas |
|---|---|
| VAREJO SHOW ROOM | `Atendido` |
| VAREJO ANACA | `Atendido-Anaca` |
| ATACADO | `Atendido-Atacado` |
| INSTAGRAM/SITE | `Atendido-Londrina`, `Atendido-Site`, `Atendido-Instagram` |

---

## Formato do arquivo de metas (`metas_<YY>.csv`)

```
"ano_mes;canal;meta"
"2026/01;VAREJO SHOW ROOM;35000"
"2026/01;VAREJO ANACA;30000"
"2026/01;ATACADO;10000"
"2026/01;INSTAGRAM/SITE;15000"
```

- `ano_mes`: formato `AAAA/MM` ou `AAAA-MM`
- `canal`: exatamente um dos 4 canais acima
- `meta`: valor numérico (sem R$, sem ponto)
- Separador: `;`
- Encoding: UTF-8

**Para adicionar meses futuros:** basta adicionar as linhas correspondentes no CSV, respeitando o mesmo formato.

---

## O que o PDF contém

- Uma tabela por mês (apenas meses de janeiro até o mês atual)
- Mês vigente: mostra **PARCIAL ATÉ dd/mm/aaaa HH:MM** com projeções de R$/dia e R$/semana para bater a meta
- Meses anteriores: mostra **METAS FECHADAS** (sem R$/dia e R$/semana)
- Coluna **% META** fica verde quando >= 100%
- Última tabela: **RESUMO ANUAL POR LOJA** (acumulado do ano até o mês vigente)
- Colunas: LOJA | FATURAMENTO META | QTD PEÇAS VENDIDAS | FATURAMENTO ATUAL | R$/FALTAM | R$/DIA | R$/SEMANA | % META

---

## Cron / automação na VPS

O script é rodado automaticamente via cron (ou job scheduler). Log em:

```
/var/www/della-sistemas/data/metas_runner.log
```

Para rodar manualmente e ver o log ao vivo:

```bash
python /var/www/della-sistemas/projetos-claude/Relatorio_de_Metas/metas.py 2026
```

---

## Dependências Python

```
pandas
reportlab
```

Instalar (se necessário):

```bash
pip install pandas reportlab
```
