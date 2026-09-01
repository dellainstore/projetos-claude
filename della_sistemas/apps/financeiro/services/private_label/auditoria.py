"""Log de auditoria genérico do módulo — ver `LogAuditoriaFinanceiro`."""
from apps.financeiro.models import LogAuditoriaFinanceiro


def registrar_log(*, operacao, entidade: str, objeto_id: int, acao: str,
                   usuario=None, campo: str = "", valor_de="", valor_para="") -> LogAuditoriaFinanceiro:
    return LogAuditoriaFinanceiro.objects.create(
        operacao=operacao,
        entidade=entidade,
        objeto_id=objeto_id,
        acao=acao,
        usuario=usuario,
        campo=campo,
        valor_de="" if valor_de in (None, "") else str(valor_de),
        valor_para="" if valor_para in (None, "") else str(valor_para),
    )
