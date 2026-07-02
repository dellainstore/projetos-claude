from django.contrib import admin

from apps.rh.models import (
    Afastamento,
    BatidaPonto,
    BeneficioVT,
    Colaborador,
    ComissaoPedido,
    CorrecaoPonto,
    EventoFolha,
    GozoFerias,
    LancamentoBeneficio,
    LocalEmpresa,
    NotificacaoPonto,
    ParametrosPonto,
    PeriodoAquisitivo,
    TipoBeneficio,
)


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ("nome", "cargo", "tipo_contrato", "bling_vendedor_id", "salario_base", "ativo")
    list_filter = ("tipo_contrato", "ativo")
    search_fields = ("nome", "cargo")


@admin.register(LocalEmpresa)
class LocalEmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome", "latitude", "longitude", "raio_metros", "ativo")


@admin.register(BatidaPonto)
class BatidaPontoAdmin(admin.ModelAdmin):
    list_display = ("colaborador", "momento", "tipo", "loja", "origem", "dentro_raio", "distancia_m")
    list_filter = ("tipo", "origem", "dentro_raio", "loja")
    date_hierarchy = "momento"


@admin.register(ParametrosPonto)
class ParametrosPontoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "tolerancia_minutos", "intervalo_minimo_minutos", "atualizado_em")


@admin.register(NotificacaoPonto)
class NotificacaoPontoAdmin(admin.ModelAdmin):
    list_display = ("colaborador", "data", "status", "lida", "criado_em")
    list_filter = ("status", "lida")
    date_hierarchy = "data"


@admin.register(CorrecaoPonto)
class CorrecaoPontoAdmin(admin.ModelAdmin):
    list_display = ("colaborador", "data", "sem_almoco", "status", "avaliado_por", "criado_em")
    list_filter = ("status", "sem_almoco")
    date_hierarchy = "data"


@admin.register(Afastamento)
class AfastamentoAdmin(admin.ModelAdmin):
    list_display = ("colaborador", "tipo", "data_inicio", "data_fim", "remunerado", "criado_em")
    list_filter = ("tipo", "remunerado")
    date_hierarchy = "data_inicio"
    search_fields = ("colaborador__nome", "observacao")


@admin.register(TipoBeneficio)
class TipoBeneficioAdmin(admin.ModelAdmin):
    list_display = ("nome", "sigla", "eh_vt", "ativo")
    list_filter = ("ativo", "eh_vt")


@admin.register(LancamentoBeneficio)
class LancamentoBeneficioAdmin(admin.ModelAdmin):
    list_display = ("colaborador", "tipo", "ano", "mes", "valor")
    list_filter = ("tipo", "ano", "mes")
    search_fields = ("colaborador__nome",)


admin.site.register(EventoFolha)
admin.site.register(ComissaoPedido)
admin.site.register(PeriodoAquisitivo)
admin.site.register(GozoFerias)
admin.site.register(BeneficioVT)
