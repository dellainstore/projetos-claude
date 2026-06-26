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
            {"id": "exportar_atacado", "label": "Exportar planilha de atacado (CSV)"},
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
        "id": "analytics",
        "label": "Analytics do Site",
        "perms": [
            {"id": "ver", "label": "Ver painel de analytics do site"},
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
        "aprovacoes": {"ver": True,       "aprovar": True},
        "precos":     {"ver": True,       "alterar": True,   "exportar_atacado": True},
        "manutencao": {"sync": True,      "rebuild": True,   "limpeza": True},
        "metas":      {"ver": True, "cadastrar": True, "ver_situacao": True},
        "pedidos":    {"ver": True, "baixar": True, "sync": True},
        "em_breve":   {"ver": True},
        "analytics":  {"ver": True},
        "admin":      {"usuarios": True},
    },
    "gestor": {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": False},
        "aprovacoes": {"ver": True,       "aprovar": True},
        "precos":     {"ver": True,       "alterar": True,   "exportar_atacado": True},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": True, "ver_situacao": True},
        "pedidos":    {"ver": True, "baixar": True, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver": True},
        "admin":      {"usuarios": False},
    },
    "operador": {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": False},
        "aprovacoes": {"ver": False,      "aprovar": False},
        "precos":     {"ver": False,      "alterar": False,  "exportar_atacado": False},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": False, "ver_situacao": False},
        "pedidos":    {"ver": True, "baixar": False, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver": False},
        "admin":      {"usuarios": False},
    },
    "viewer": {
        "estoque":    {"incluir": False, "historico": True,  "excluir": False},
        "aprovacoes": {"ver": True,       "aprovar": False},
        "precos":     {"ver": False,      "alterar": False,  "exportar_atacado": False},
        "manutencao": {"sync": False,     "rebuild": False,  "limpeza": False},
        "metas":      {"ver": True, "cadastrar": False, "ver_situacao": False},
        "pedidos":    {"ver": True, "baixar": False, "sync": False},
        "em_breve":   {"ver": False},
        "analytics":  {"ver": False},
        "admin":      {"usuarios": False},
    },
}
