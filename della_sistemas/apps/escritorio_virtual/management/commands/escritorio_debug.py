"""Diagnóstico do escritório virtual: mostra o estado derivado de um dia.

**Somente leitura.** Não cria, altera nem apaga nada, e não gera notificação
de ponto. Serve para conferir a projeção contra a tela oficial de Jornada
antes de qualquer coisa aparecer na cena.

    python manage.py escritorio_debug
    python manage.py escritorio_debug --data 2026-09-18
    python manage.py escritorio_debug --colaborador-id 1
    python manage.py escritorio_debug --json

Nunca imprime latitude, longitude nem distância do geofence.
"""

import json
from datetime import date, datetime, time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.escritorio_virtual.services.projecao import projetar_cena
from apps.rh.services.ponto import dia_incompleto

LARGURA = 78


class Command(BaseCommand):
    help = "Mostra o estado derivado do escritório virtual para um dia (somente leitura)."

    def add_arguments(self, parser):
        parser.add_argument("--data", help="Dia a projetar (YYYY-MM-DD). Padrão: hoje.")
        parser.add_argument(
            "--colaborador-id", type=int, dest="colaborador_id",
            help="Projeta só a personagem deste colaborador.",
        )
        parser.add_argument(
            "--agora", help="Instante de referência (HH:MM). Padrão: agora, ou o "
                            "fim do dia quando --data é um dia passado.",
        )
        parser.add_argument("--json", action="store_true", help="Saída em JSON.")

    def handle(self, *args, **options):
        dia = self._parse_data(options.get("data"))
        agora = self._parse_agora(dia, options.get("agora"))

        cena = projetar_cena(
            dia=dia, agora=agora, colaborador_id=options.get("colaborador_id"),
        )

        if options["json"]:
            self.stdout.write(json.dumps(self._como_dict(cena), ensure_ascii=False, indent=2))
            return

        self._imprimir(cena)

    # ── parsing ──────────────────────────────────────────────────────────────

    def _parse_data(self, raw) -> date:
        if not raw:
            return timezone.localdate()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise CommandError(f"Data inválida: {raw}. Use YYYY-MM-DD.")

    def _parse_agora(self, dia: date, raw):
        if not raw:
            return None
        try:
            h, _, m = raw.partition(":")
            hora = time(int(h), int(m or 0))
        except ValueError:
            raise CommandError(f"Hora inválida: {raw}. Use HH:MM.")
        return timezone.make_aware(datetime.combine(dia, hora))

    # ── saída ────────────────────────────────────────────────────────────────

    def _hm(self, dt) -> str:
        return timezone.localtime(dt).strftime("%H:%M") if dt else "sem registro"

    def _imprimir(self, cena):
        self.stdout.write("=" * LARGURA)
        self.stdout.write(
            f"ESCRITÓRIO VIRTUAL · {cena.data:%d/%m/%Y} "
            f"(referência {self._hm(cena.gerado_em)})"
        )
        self.stdout.write("=" * LARGURA)
        self.stdout.write(
            f"Loja: {cena.estado_loja}  ·  luzes "
            f"{'acesas' if cena.luzes_acesas else 'apagadas'}  ·  porta "
            f"{'aberta' if cena.porta_aberta else 'fechada'}"
        )
        self.stdout.write(
            f"Parâmetros: margem de fechamento {cena.parametros.margem_fechamento_minutos} min · "
            f"limite absoluto {cena.parametros.hora_limite_absoluta:%H:%M} · "
            f"animação {cena.parametros.evento_recente_segundos}s · "
            f"poll {cena.parametros.poll_segundos}s"
        )
        if cena.avisos:
            self.stdout.write(self.style.WARNING("Avisos técnicos: " + ", ".join(cena.avisos)))
        self.stdout.write("")

        if not cena.atores:
            self.stdout.write(self.style.WARNING(
                "Nenhuma personagem ativa configurada. "
                "Use `manage.py escritorio_personagem` para cadastrar."
            ))
            return

        for ator in cena.atores:
            self._imprimir_ator(ator, cena.data)

    def _imprimir_ator(self, ator, dia):
        colab = ator.personagem.colaborador
        estilo = self.style.ERROR if ator.inconsistencia else self.style.SUCCESS

        self.stdout.write("-" * LARGURA)
        self.stdout.write(
            f"{ator.nome_exibicao} (personagem '{ator.personagem.personagem}', "
            f"{ator.personagem.tipo_ator}"
            + (f", colaborador_id={colab.pk}" if colab else "")
            + ")"
        )
        self.stdout.write(f"  estado          : {estilo(ator.estado)}")
        if ator.estado != ator.estado_estavel:
            self.stdout.write(f"  estado estável  : {ator.estado_estavel} (transição em curso)")
        self.stdout.write(f"  motivo          : {ator.motivo}")
        self.stdout.write(f"  desde           : {self._hm(ator.desde)}")

        sala = ator.sala.slug or "fora de cena"
        trabalho = ator.sala_trabalho.slug or "indefinida"
        self.stdout.write(f"  sala na cena    : {sala}")
        self.stdout.write(
            f"  sala de trabalho: {trabalho}  (origem: {ator.sala_trabalho.origem})"
        )
        if ator.sala_trabalho.origem != "loja":
            self.stdout.write(
                "                    "
                + self.style.WARNING("não veio da loja da batida; é fallback")
            )

        if ator.evento_recente:
            e = ator.evento_recente
            self.stdout.write(
                f"  animação        : {e.event} ({e.event_id}) às {self._hm(e.occurred_at)}"
            )

        if ator.eventos:
            linha = "  ".join(
                f"{self._hm(e.occurred_at)} {e.event}" for e in ator.eventos
            )
            self.stdout.write(f"  batidas do dia  : {linha}")
            ultima = ator.eventos[-1]
            self.stdout.write(
                f"  batida + recente: {self._hm(ultima.occurred_at)} "
                f"{ultima.event} ({ultima.event_id})"
            )
        else:
            self.stdout.write("  batidas do dia  : nenhuma")

        if ator.inconsistencia:
            self.stdout.write(self.style.ERROR(f"  inconsistência  : {ator.inconsistencia}"))
        if ator.avisos:
            self.stdout.write(self.style.WARNING(f"  avisos          : {', '.join(ator.avisos)}"))

        # Conferência contra a fonte oficial.
        if colab:
            veredito = dia_incompleto(colab, dia)
            self.stdout.write(
                f"  ponto oficial   : dia_incompleto() = {veredito}"
            )
            self.stdout.write(
                f"  conferir em     : /rh/ponto/jornada/?colaborador={colab.pk}"
                f"&modo=custom&inicio={dia:%Y-%m-%d}&fim={dia:%Y-%m-%d}"
            )

    def _como_dict(self, cena) -> dict:
        """Mesma informação da saída de texto, para diff automatizado.

        Inclui campos de diagnóstico (motivo, dia_incompleto) que NÃO existem
        no payload da API — este comando roda no terminal do servidor, não é
        exposto por HTTP."""
        return {
            "data": cena.data.isoformat(),
            "gerado_em": timezone.localtime(cena.gerado_em).isoformat(),
            "loja": {
                "estado": cena.estado_loja,
                "luzes_acesas": cena.luzes_acesas,
                "porta_aberta": cena.porta_aberta,
            },
            "avisos": cena.avisos,
            "personagens": [
                {
                    "personagem": a.personagem.personagem,
                    "tipo_ator": a.personagem.tipo_ator,
                    "colaborador_id": a.personagem.colaborador_id,
                    "nome_exibicao": a.nome_exibicao,
                    "estado": a.estado,
                    "estado_estavel": a.estado_estavel,
                    "motivo": a.motivo,
                    "desde": timezone.localtime(a.desde).isoformat() if a.desde else None,
                    "sala": a.sala.slug,
                    "sala_trabalho": a.sala_trabalho.slug,
                    "sala_origem": a.sala_trabalho.origem,
                    "inconsistencia": a.inconsistencia,
                    "avisos": a.avisos,
                    "eventos": [e.como_dict() for e in a.eventos],
                    "ponto_oficial_dia_incompleto": (
                        dia_incompleto(a.personagem.colaborador, cena.data)
                        if a.personagem.colaborador_id else None
                    ),
                }
                for a in cena.atores
            ],
        }
