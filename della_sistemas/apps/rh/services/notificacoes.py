"""Geração de pendências de ponto (notificações). Roda no job diário e também
pode ser disparada manualmente pelo gestor."""

from datetime import date

from django.utils import timezone

from apps.rh.models import Colaborador, NotificacaoPonto, ParametrosPonto
from apps.rh.services.ponto import dia_incompleto


def _mensagem(colaborador, dia: date) -> str:
    from apps.rh.services.afastamentos import afastamento_no_dia, slots_dispensados_por_afastamento
    from apps.rh.services.ponto import _batidas_do_dia_qs, BATIDAS_POR_DIA
    af = afastamento_no_dia(colaborador, dia)
    dispensados = slots_dispensados_por_afastamento(colaborador, dia, af) if af else set()
    esperadas = BATIDAS_POR_DIA - len(dispensados)
    n = _batidas_do_dia_qs(colaborador, dia).count()
    if n == 0 and not dispensados:
        return (f"Nenhum ponto registrado em {dia:%d/%m/%Y}. "
                "Verifique e peça correção ao gestor se trabalhou nesse dia.")
    if n % 2 == 1:
        # Número ímpar de batidas: sempre falta a outra metade de um par
        # (normalmente a saída), mesmo que já tenha batido o suficiente ou mais
        # que `esperadas` — um afastamento parcial de manhã não dispensa quem
        # trabalhou à tarde e esqueceu de bater a última batida.
        return (f"Falta 1 batida em {dia:%d/%m/%Y} ({n} registradas, número "
                "ímpar — provavelmente a saída). Avise o gestor para corrigir.")
    faltam = esperadas - n
    plural = "batida" if faltam == 1 else "batidas"
    return (f"Faltou {faltam} {plural} em {dia:%d/%m/%Y} "
            f"({n} de {esperadas} registradas). Avise o gestor para corrigir.")


def gerar_pendencias_do_dia(dia: date) -> int:
    """Cria/atualiza notificações para colaboradores com batidas incompletas no dia.

    Se o dia ficou completo (correção posterior), resolve a pendência existente.
    Retorna o número de pendências abertas (criadas ou mantidas)."""
    # Antes da data de início do controle de ponto não se cobra batida: nada é
    # apurado e nenhuma correção é liberada para dias anteriores.
    if dia < ParametrosPonto.get().data_inicio:
        return 0
    # O dia só é cobrado depois de fechado — nunca gerar pendência para hoje
    # ou datas futuras (o colaborador ainda pode bater os pontos do dia).
    if dia >= timezone.localdate():
        return 0
    abertas = 0
    for colaborador in Colaborador.objects.filter(ativo=True, registra_ponto=True):
        incompleto = dia_incompleto(colaborador, dia)
        existente = NotificacaoPonto.objects.filter(colaborador=colaborador, data=dia).first()

        if incompleto:
            if existente is None:
                NotificacaoPonto.objects.create(
                    colaborador=colaborador, data=dia, mensagem=_mensagem(colaborador, dia),
                )
            elif existente.status == "resolvido":
                # Reabre se a correção foi desfeita.
                existente.status = "pendente"
                existente.lida = False
                existente.resolvido_em = None
                existente.mensagem = _mensagem(colaborador, dia)
                existente.save(update_fields=["status", "lida", "resolvido_em", "mensagem"])
            else:
                existente.mensagem = _mensagem(colaborador, dia)
                existente.save(update_fields=["mensagem"])
            abertas += 1
        elif existente is not None and existente.status != "resolvido":
            # Dia ficou completo → resolve automaticamente.
            existente.status = "resolvido"
            existente.resolvido_em = timezone.now()
            existente.save(update_fields=["status", "resolvido_em"])
    return abertas
