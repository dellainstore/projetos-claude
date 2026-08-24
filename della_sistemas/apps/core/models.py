from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuário com permissões granulares por módulo."""

    PAPEL_CHOICES = [
        ("superadmin", "Super Admin"),
        ("gestor", "Gestor"),
        ("operador", "Operador"),
        ("viewer", "Viewer"),
    ]
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES, default="operador")
    permissoes = models.JSONField(default=dict, verbose_name="Permissões")

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def tem_perm(self, perm: str) -> bool:
        """Verifica permissão 'modulo.chave'. Se permissoes={}, usa papel legado."""
        if self.is_superuser:
            return True
        modulo, chave = perm.split(".", 1)
        if self.permissoes:
            return bool(self.permissoes.get(modulo, {}).get(chave, False))
        # fallback para papel enquanto permissoes não foi configurado
        from apps.core.permissions import DEFAULT_PERMS_BY_PAPEL
        return bool(DEFAULT_PERMS_BY_PAPEL.get(self.papel, {}).get(modulo, {}).get(chave, False))

    def resumo_acessos(self) -> list[str]:
        """Módulos a que o usuário tem algum acesso, derivado das permissões
        efetivas (não do papel). Usado na lista de usuários."""
        from apps.core.permissions import PERMISSION_TREE
        labels = []
        for grupo in PERMISSION_TREE:
            if any(self.tem_perm(f"{grupo['id']}.{p['id']}") for p in grupo["perms"]):
                labels.append(grupo["label"])
        return labels

    # ── helpers legados (usados nos templates existentes) ──────────────────
    @property
    def is_superadmin(self) -> bool:
        return self.tem_perm("admin.usuarios")

    @property
    def is_gestor_or_above(self) -> bool:
        return self.tem_perm("aprovacoes.aprovar")

    @property
    def pode_aprovar(self) -> bool:
        return self.tem_perm("aprovacoes.aprovar")

    @property
    def pode_ver_precos(self) -> bool:
        return self.tem_perm("precos.ver")

    @property
    def pode_incluir(self) -> bool:
        return self.tem_perm("estoque.incluir")

    @property
    def pode_ver_historico(self) -> bool:
        return self.tem_perm("estoque.historico")

    @property
    def pode_excluir_estoque(self) -> bool:
        return self.tem_perm("estoque.excluir")

    @property
    def pode_ver_resumo_produtos(self) -> bool:
        # "Resumo" agrega pendências/inclusões/aprovações — mesma audiência de
        # quem já mexe nesse fluxo (inclui, aprova ou vê o histórico).
        return self.pode_incluir or self.pode_aprovar or self.pode_ver_historico

    @property
    def pode_consulta_rapida(self) -> bool:
        return self.tem_perm("consulta_rapida.ver")

    @property
    def pode_ver_metas(self) -> bool:
        return self.tem_perm("metas.ver")

    @property
    def pode_cadastrar_metas(self) -> bool:
        return self.tem_perm("metas.cadastrar")

    @property
    def pode_ver_situacao_metas(self) -> bool:
        return self.tem_perm("metas.ver_situacao")

    @property
    def pode_ver_em_breve(self) -> bool:
        return self.tem_perm("em_breve.ver")

    @property
    def pode_ver_estoque_analise(self) -> bool:
        return self.tem_perm("estoque_analise.ver")

    @property
    def pode_ver_financeiro(self) -> bool:
        return self.tem_perm("financeiro.ver")

    @property
    def pode_ver_pedidos(self) -> bool:
        return self.tem_perm("pedidos.ver")

    @property
    def pode_dar_baixa(self) -> bool:
        return self.tem_perm("pedidos.baixar")

    @property
    def pode_sync_pedidos(self) -> bool:
        return self.tem_perm("pedidos.sync")

    @property
    def pode_ver_visitas(self) -> bool:
        return self.tem_perm("analytics.ver_visitas")

    @property
    def pode_ver_vendas(self) -> bool:
        return self.tem_perm("analytics.ver_vendas")

    @property
    def pode_ver_relatorio_semanal(self) -> bool:
        return self.tem_perm("analytics.ver_relatorio")

    @property
    def pode_gerar_link(self) -> bool:
        return self.tem_perm("analytics.gerar_link")

    @property
    def pode_ver_analytics(self) -> bool:
        """Algum acesso ao grupo 'Site' (visitas, vendas, relatorio ou gerar
        link) — usado so para abrir/fechar o grupo inteiro no menu. Cada link
        dentro do grupo checa a propria permissao especifica, nao esta."""
        return (
            self.pode_ver_visitas or self.pode_ver_vendas
            or self.pode_ver_relatorio_semanal or self.pode_gerar_link
        )

    @property
    def pode_ver_tarefas(self) -> bool:
        return self.tem_perm("tarefas.ver")

    @property
    def pode_criar_tarefas(self) -> bool:
        return self.tem_perm("tarefas.criar")

    @property
    def pode_ver_rh(self) -> bool:
        return self.tem_perm("rh.ver")

    @property
    def pode_gerir_rh(self) -> bool:
        return self.tem_perm("rh.gerir")

    @property
    def pode_bater_ponto(self) -> bool:
        return self.tem_perm("rh.ponto_bater")

    @property
    def pode_ver_jornada_propria(self) -> bool:
        return self.tem_perm("rh.ponto_jornada_ver")

    @property
    def pode_gerir_ponto(self) -> bool:
        return self.tem_perm("rh.ponto_gerir")

    @property
    def pode_visualizar(self) -> bool:
        return True
