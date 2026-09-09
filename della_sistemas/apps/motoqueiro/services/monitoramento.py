"""Monitoramento de cotação Lalamove — cota um trajeto de novo a cada rodada
do cron (ver management/commands/checar_monitoramento_motoqueiro.py, a cada
20 min) até achar um preço igual ou abaixo do alvo, ou até bater o horário
que o funcionário definiu na criação (sempre no mesmo dia, nunca estende).

Nunca cria pedido sozinho — só cota (criar_cotacao não cobra nada). Quando
acha, avisa no Telegram com um link que leva pra tela de Solicitar já com os
endereços preenchidos, mas pedindo uma cotação NOVA na hora (a que disparou o
aviso pode já ter expirado ou mudado de preço)."""
import logging
from decimal import Decimal
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from ..models import MonitoramentoCotacao
from . import lalamove, telegram
from .config import PAINEL_BASE_URL

logger = logging.getLogger(__name__)

VEICULOS_LALAMOVE = [
    (MonitoramentoCotacao.VEICULO_LALAGO, "LalaGo (moto, sem baú)"),
    (MonitoramentoCotacao.VEICULO_LALAPRO, "LalaPro (moto com baú)"),
]


def criar_monitoramento(
    *, criado_por, endereco_retirada: str, complemento_retirada: str,
    lat_retirada: float, lng_retirada: float,
    endereco_entrega: str, complemento_entrega: str,
    lat_entrega: float, lng_entrega: float,
    veiculo: str, preco_alvo: Decimal, expira_em,
) -> MonitoramentoCotacao:
    return MonitoramentoCotacao.objects.create(
        criado_por=criado_por,
        endereco_retirada=endereco_retirada, complemento_retirada=complemento_retirada,
        lat_retirada=lat_retirada, lng_retirada=lng_retirada,
        endereco_entrega=endereco_entrega, complemento_entrega=complemento_entrega,
        lat_entrega=lat_entrega, lng_entrega=lng_entrega,
        veiculo=veiculo, preco_alvo=preco_alvo,
        status=MonitoramentoCotacao.STATUS_ATIVO,
        expira_em=expira_em,
    )


def _endereco_lalamove(endereco: str, complemento: str) -> str:
    return f"{endereco} - {complemento}" if complemento else endereco


def _cotar(monitor: MonitoramentoCotacao) -> tuple[dict, str]:
    """Cota só os veículos relevantes pra esse monitoramento (os dois, se
    'qualquer', ou só o escolhido). Devolve (precos, erro) — precos é
    {service_type: (Decimal, label)}; erro fica vazio se pelo menos uma
    cotação deu certo (uma falha isolada não derruba a rodada)."""
    veiculos = VEICULOS_LALAMOVE if monitor.veiculo == MonitoramentoCotacao.VEICULO_QUALQUER \
        else [v for v in VEICULOS_LALAMOVE if v[0] == monitor.veiculo]

    endereco_retirada = _endereco_lalamove(monitor.endereco_retirada, monitor.complemento_retirada)
    endereco_entrega = _endereco_lalamove(monitor.endereco_entrega, monitor.complemento_entrega)

    precos = {}
    erros = []
    for service_type, label in veiculos:
        try:
            resp = lalamove.criar_cotacao(
                endereco_retirada=endereco_retirada, lat_retirada=monitor.lat_retirada, lng_retirada=monitor.lng_retirada,
                endereco_entrega=endereco_entrega, lat_entrega=monitor.lat_entrega, lng_entrega=monitor.lng_entrega,
                service_type=service_type,
            )
            preco_raw = resp.get("data", {}).get("priceBreakdown", {}).get("total")
            precos[service_type] = (Decimal(str(preco_raw)), label)
        except lalamove.LalamoveError as e:
            erros.append(f"{label}: {e.status_code} — {str(e.body)[:150]}")
        except Exception as e:
            erros.append(f"{label}: {e}")

    # Só reporta erro se NENHUM veículo cotou — se um dos dois falhou mas o
    # outro deu certo, a rodada segue normal (o erro isolado não é útil).
    erro = " | ".join(erros) if not precos and erros else ""
    return precos, erro


def montar_query_pedir_agora(monitor: MonitoramentoCotacao) -> str:
    """Só a querystring (sem path/domínio) pra reabrir Solicitar já
    preenchido com os endereços deste monitoramento — o JS da tela detecta
    `auto_cotar=1` e já dispara uma cotação nova sozinho, sem o usuário
    redigitar nada. Usada tanto no botão "Pedir agora" (link relativo) quanto
    — com path e domínio na frente — no aviso do Telegram."""
    return urlencode({
        "endereco_retirada": monitor.endereco_retirada,
        "complemento_retirada": monitor.complemento_retirada,
        "lat_retirada": monitor.lat_retirada,
        "lng_retirada": monitor.lng_retirada,
        "endereco_entrega": monitor.endereco_entrega,
        "complemento_entrega": monitor.complemento_entrega,
        "lat_entrega": monitor.lat_entrega,
        "lng_entrega": monitor.lng_entrega,
        "auto_cotar": "1",
    })


def link_absoluto_pedir_agora(monitor: MonitoramentoCotacao) -> str:
    return f"{PAINEL_BASE_URL}{reverse('motoqueiro:solicitar')}?{montar_query_pedir_agora(monitor)}"


def _texto_encontrado(monitor: MonitoramentoCotacao) -> str:
    link = link_absoluto_pedir_agora(monitor)
    return (
        "🏍️ Cotação encontrada!\n"
        f"De {monitor.endereco_retirada} para {monitor.endereco_entrega}\n"
        f"{monitor.veiculo_encontrado}: R$ {monitor.preco_encontrado} (meta: R$ {monitor.preco_alvo})\n"
        f"Peça agora: {link}"
    )


def _texto_expirado(monitor: MonitoramentoCotacao) -> str:
    ultimo = monitor.ultimo_preco_lalago if monitor.ultimo_preco_lalago is not None else monitor.ultimo_preco_lalapro
    trecho_ultimo = f" Último preço visto: R$ {ultimo}." if ultimo is not None else " Nenhuma cotação válida foi conseguida."
    return (
        "⌛ Monitoramento encerrado sem achar o preço alvo.\n"
        f"De {monitor.endereco_retirada} para {monitor.endereco_entrega}\n"
        f"Meta era R$ {monitor.preco_alvo}.{trecho_ultimo}"
    )


def checar_monitoramentos_ativos() -> dict:
    """Chamado pelo cron a cada 20 min. Pra cada monitoramento ativo:
    - se já passou do horário definido na criação: expira e avisa (sem
      gastar mais uma chamada de cotação);
    - senão cota de novo; se algum veículo bateu a meta, marca 'encontrado'
      e avisa; senão só atualiza o último preço visto e segue ativo."""
    agora = timezone.now()
    ativos = MonitoramentoCotacao.objects.filter(status=MonitoramentoCotacao.STATUS_ATIVO)
    verificados = encontrados = expirados = 0

    for monitor in ativos:
        if agora >= monitor.expira_em:
            monitor.status = MonitoramentoCotacao.STATUS_EXPIRADO
            monitor.save(update_fields=["status"])
            telegram.enviar_mensagem(_texto_expirado(monitor))
            expirados += 1
            continue

        precos, erro = _cotar(monitor)
        monitor.ultima_consulta_em = agora
        monitor.ultimo_erro = erro
        if MonitoramentoCotacao.VEICULO_LALAGO in precos:
            monitor.ultimo_preco_lalago = precos[MonitoramentoCotacao.VEICULO_LALAGO][0]
        if MonitoramentoCotacao.VEICULO_LALAPRO in precos:
            monitor.ultimo_preco_lalapro = precos[MonitoramentoCotacao.VEICULO_LALAPRO][0]

        candidatos = [
            (preco, label) for preco, label in precos.values() if preco <= monitor.preco_alvo
        ]
        if candidatos:
            preco, label = min(candidatos, key=lambda c: c[0])
            monitor.status = MonitoramentoCotacao.STATUS_ENCONTRADO
            monitor.encontrado_em = agora
            monitor.preco_encontrado = preco
            monitor.veiculo_encontrado = label
            monitor.save()
            telegram.enviar_mensagem(_texto_encontrado(monitor))
            encontrados += 1
        else:
            monitor.save(update_fields=["ultima_consulta_em", "ultimo_erro", "ultimo_preco_lalago", "ultimo_preco_lalapro"])
        verificados += 1

    return {"verificados": verificados, "encontrados": encontrados, "expirados": expirados}
