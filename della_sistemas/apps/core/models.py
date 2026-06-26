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
    def pode_incluir(self) -> bool:
        return self.tem_perm("estoque.incluir")

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
    def pode_ver_pedidos(self) -> bool:
        return self.tem_perm("pedidos.ver")

    @property
    def pode_dar_baixa(self) -> bool:
        return self.tem_perm("pedidos.baixar")

    @property
    def pode_sync_pedidos(self) -> bool:
        return self.tem_perm("pedidos.sync")

    @property
    def pode_ver_analytics(self) -> bool:
        return self.tem_perm("analytics.ver")

    @property
    def pode_visualizar(self) -> bool:
        return True
