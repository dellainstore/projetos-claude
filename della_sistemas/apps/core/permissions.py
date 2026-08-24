"""Árvore de permissões do sistema D'ELLA Sistemas."""

PERMISSION_TREE = [
    {
        "id": "estoque",
        "label": "Estoque",
        "perms": [
            {"id": "incluir",  "label": "Incluir estoque"},
            {"id": "historico","label": "Ver histórico de inclusões"},
            {"id": "excluir",  "label": "Excluir lançamentos"},
        ],
    },
    {
        "id": "consulta_rapida",
        "label": "Consulta Rápida",
        "perms": [
            {"id": "ver", "label": "Consultar produto por código de barras (SKU)"},
        ],
    },
    {
        "id": "aprovacoes",
        "label": "Aprovações",
        "perms": [
            {"id": "ver",    "label": "Ver solicitações pendentes"},
            {"id": "aprovar","label": "Aprovar / Rejeitar"},
        ],
    },
    {
        "id": "precos",
        "label": "Preços",
        "perms": [
            {"id": "ver",              "label": "Ver preços"},
            {"id": "alterar",          "label": "Alterar preços (varejo, custo, atacado)"},
            # "Exportar planilha de atacado" não é mais um checkbox aqui — a
            # exportação (CSV/XLSX pra importar no Bling) ficou travada em
            # is_superadmin direto (2026-08-17), pedido explícito do dono:
            # só ele deve ver/baixar essas planilhas, não é algo delegável.
        ],
    },
    {
        "id": "manutencao",
        "label": "Manutenção",
        "perms": [
            {"id": "sync",    "label": "Sincronizar catálogo Bling"},
            {"id": "rebuild", "label": "Rebuild variações"},
            {"id": "limpeza", "label": "Limpeza de dados"},
        ],
    },
    {
        "id": "metas",
        "label": "Metas e Pedidos",
        "perms": [
            {"id": "ver",          "label": "Ver metas e dashboard"},
            {"id": "cadastrar",    "label": "Cadastrar funcionarias e metas"},
            {"id": "ver_situacao", "label": "Ver faturamento por situação (Bling)"},
        ],
    },
    {
        "id": "pedidos",
        "label": "Pedidos",
        "perms": [
            {"id": "ver",    "label": "Ver pedidos e pagamentos"},
            {"id": "baixar", "label": "Dar baixa em pagamentos"},
            {"id": "sync",   "label": "Sincronizar pedidos com Bling (manual)"},
        ],
    },
    {
        "id": "em_breve",
        "label": "Em breve",
        "perms": [
            {"id": "ver", "label": "Ver seção 'Em breve' no menu"},
        ],
    },
    {
        "id": "estoque_analise",
        "label": "Estoque (Análise)",
        "perms": [
            {"id": "ver", "label": "Ver saúde, reposição, queima e previsão de estoque"},
        ],
    },
    {
        "id": "financeiro",
        "label": "Financeiro",
        "perms": [
            {"id": "ver", "label": "Ver dashboard de faturamento"},
        ],
    },
    {
        "id": "analytics",
        "label": "Site",
        "perms": [
            # Ate 2026-08-24 era um unico "ver" cobrindo tudo. Separado por
            # submenu porque nem todo mundo que precisa gerar link de
            # postagem deve enxergar visitas/vendas do site (dado sensivel de
            # faturamento), e vice-versa: pedido explicito do dono.
            {"id": "ver_visitas",   "label": "Ver Visitas (mapa, origem, funil)"},
            {"id": "ver_vendas",    "label": "Ver Vendas (faturamento, campanhas)"},
            {"id": "ver_relatorio", "label": "Ver Resumo Semanal (PDF)"},
            {"id": "gerar_link",    "label": "Gerar link para postagem (Instagram, TikTok, WhatsApp)"},
        ],
    },
    {
        "id": "tarefas",
        "label": "Tarefas",
        "perms": [
            {"id": "ver",   "label": "Ver o próprio painel de tarefas"},
            {"id": "criar", "label": "Criar tarefas e atribuir para outros"},
        ],
    },
    {
        "id": "rh",
        "label": "Recursos Humanos",
        "perms": [
            {"id": "ver",         "label": "Ver painel de RH"},
            {"id": "gerir",       "label": "Gerir colaboradores, salários, comissão, férias e benefícios"},
            {"id": "ponto_bater", "label": "Registrar o próprio ponto"},
            {"id": "ponto_jornada_ver", "label": "Ver a própria jornada de ponto (consulta, sem editar)"},
            {"id": "ponto_gerir", "label": "Ver e editar pontos de todos"},
        ],
    },
    {
        "id": "admin",
        "label": "Administração",
        "perms": [
            {"id": "usuarios", "label": "Gerenciar usuários e permissões"},
        ],
    },
]

# Permissões padrão por papel (fallback enquanto permissoes={})
DEFAULT_PERMS_BY_PAPEL = {
    "superadmin": {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": True},
        "consulta_rapida": {"ver": True},
        "estoque_analise": {"ver": True},
        "financeiro":      {"ver": True},
        "aprovacoes": {"ver": True,       "aprovar": True},
        "precos":     {"ver": True,       "alterar": True},
        "manutencao": {"sync": True,      "rebuild": True,   "limpeza": True},
        "metas":      {"ver": True, "cadastrar": True, "ver_situacao": True},
        "pedidos":    {"ver": True, "baixar": True, "sync": True},
        "em_breve":   {"ver": True},
        "analytics":  {"ver_visitas": True, "ver_vendas": True, "ver_relatorio": True, "gerar_link": True},
        "tarefas":    {"ver": True, "criar": True},
        "rh":         {"ver": True, "gerir": True, "ponto_bater": True, "ponto_jornada_ver": True, "ponto_gerir": True},
        "admin":      {"usuarios": True},
    },
    "gestor": {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": False},
        "consulta_rapida": {"ver": True},
        "estoque_analise": {"ver": False},
        "financeiro":      {"ver": False},
        "aprovacoes": {"ver": True,       "aprovar": True},
        "precos":     {"ver": True,       "alterar": True},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": True, "ver_situacao": True},
        "pedidos":    {"ver": True, "baixar": True, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver_visitas": True, "ver_vendas": True, "ver_relatorio": True, "gerar_link": True},
        "tarefas":    {"ver": True, "criar": True},
        "rh":         {"ver": True, "gerir": True, "ponto_bater": True, "ponto_jornada_ver": True, "ponto_gerir": True},
        "admin":      {"usuarios": False},
    },
    "operador": {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": False},
        "consulta_rapida": {"ver": True},
        "estoque_analise": {"ver": False},
        "financeiro":      {"ver": False},
        "aprovacoes": {"ver": False,      "aprovar": False},
        "precos":     {"ver": False,      "alterar": False},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": False, "ver_situacao": False},
        "pedidos":    {"ver": True, "baixar": False, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver_visitas": False, "ver_vendas": False, "ver_relatorio": False, "gerar_link": True},
        "tarefas":    {"ver": True, "criar": True},
        "rh":         {"ver": False, "gerir": False, "ponto_bater": True, "ponto_jornada_ver": True, "ponto_gerir": False},
        "admin":      {"usuarios": False},
    },
    "viewer": {
        "estoque":    {"incluir": False, "historico": True,  "excluir": False},
        "estoque_analise": {"ver": False},
        "financeiro":      {"ver": False},
        "aprovacoes": {"ver": True,       "aprovar": False},
        "precos":     {"ver": False,      "alterar": False},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": False, "ver_situacao": False},
        "pedidos":    {"ver": True, "baixar": False, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver_visitas": False, "ver_vendas": False, "ver_relatorio": False, "gerar_link": True},
        "tarefas":    {"ver": True, "criar": True},
        "rh":         {"ver": False, "gerir": False, "ponto_bater": True, "ponto_jornada_ver": True, "ponto_gerir": False},
        "admin":      {"usuarios": False},
    },
}
