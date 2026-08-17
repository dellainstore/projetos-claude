from django.contrib import admin

from apps.tarefas.models import ColunaStatus, HistoricoTarefa, Tarefa, TarefaComentario, TarefaResponsavel


@admin.register(ColunaStatus)
class ColunaStatusAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordem", "eh_conclusao", "ativa")
    list_editable = ("ordem", "ativa")


class TarefaResponsavelInline(admin.TabularInline):
    model = TarefaResponsavel
    fk_name = "tarefa"
    extra = 0


class TarefaComentarioInline(admin.TabularInline):
    model = TarefaComentario
    extra = 0


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "status", "prioridade", "prazo", "criado_por", "arquivada")
    list_filter = ("status", "prioridade", "arquivada")
    search_fields = ("titulo", "descricao")
    inlines = [TarefaResponsavelInline, TarefaComentarioInline]


@admin.register(HistoricoTarefa)
class HistoricoTarefaAdmin(admin.ModelAdmin):
    list_display = ("tarefa", "campo", "valor_anterior", "valor_novo", "alterado_por", "alterado_em")
    list_filter = ("campo",)
    date_hierarchy = "alterado_em"
