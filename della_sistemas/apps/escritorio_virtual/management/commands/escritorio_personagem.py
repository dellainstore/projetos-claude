"""Cadastro de personagens do escritório virtual pela linha de comando.

Enquanto não existe tela de configuração (fase futura), este comando é o jeito
de ligar um colaborador a uma personagem. Escreve APENAS em
`escritorio_virtual_personagemescritorio`: nunca toca em ponto, batida,
escala ou qualquer dado trabalhista.

    python manage.py escritorio_personagem --listar
    python manage.py escritorio_personagem --colaborador-id 1 --personagem tina --sala showroom-1
    python manage.py escritorio_personagem --colaborador-id 1 --desativar

É idempotente: rodar de novo com os mesmos argumentos atualiza a linha
existente em vez de duplicar.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.escritorio_virtual.models import PersonagemEscritorio, SalaEscritorio
from apps.rh.models import Colaborador


class Command(BaseCommand):
    help = "Cadastra/atualiza uma personagem do escritório virtual (não altera o ponto)."

    def add_arguments(self, parser):
        parser.add_argument("--listar", action="store_true", help="Lista o elenco atual.")
        parser.add_argument(
            "--colaboradores", action="store_true",
            help="Lista colaboradores que batem ponto, com id (para escolher).",
        )
        parser.add_argument("--colaborador-id", type=int, dest="colaborador_id")
        parser.add_argument("--personagem", help="Slug do sprite. Ex.: tina.")
        parser.add_argument("--sala", help="Slug da sala padrão. Ex.: showroom-1.")
        parser.add_argument("--pos-x", type=int, dest="pos_x", default=0)
        parser.add_argument("--pos-y", type=int, dest="pos_y", default=0)
        parser.add_argument("--desativar", action="store_true")
        parser.add_argument("--ativar", action="store_true")

    def handle(self, *args, **options):
        if options["colaboradores"]:
            return self._listar_colaboradores()
        if options["listar"]:
            return self._listar()

        colab_id = options.get("colaborador_id")
        if not colab_id:
            raise CommandError(
                "Informe --colaborador-id (veja os ids com --colaboradores) "
                "ou use --listar."
            )

        colaborador = Colaborador.objects.filter(pk=colab_id).first()
        if colaborador is None:
            raise CommandError(f"Colaborador {colab_id} não encontrado.")

        existente = PersonagemEscritorio.objects.filter(colaborador=colaborador).first()

        if options["desativar"] or options["ativar"]:
            if existente is None:
                raise CommandError(f"{colaborador.nome} ainda não tem personagem.")
            existente.ativo = bool(options["ativar"])
            existente.save(update_fields=["ativo"])
            estado = "ativada" if existente.ativo else "desativada"
            self.stdout.write(self.style.SUCCESS(f"Personagem {estado}: {existente}"))
            return

        personagem = (options.get("personagem") or "").strip()
        if not personagem and existente is None:
            raise CommandError("Informe --personagem (slug do sprite).")
        personagem = personagem or existente.personagem

        sala = None
        slug_sala = (options.get("sala") or "").strip()
        if slug_sala:
            sala = SalaEscritorio.objects.filter(slug=slug_sala).first()
            if sala is None:
                disponiveis = ", ".join(
                    SalaEscritorio.objects.values_list("slug", flat=True)
                ) or "nenhuma"
                raise CommandError(f"Sala '{slug_sala}' não existe. Disponíveis: {disponiveis}")
        elif existente is not None:
            sala = existente.sala_padrao

        obj, criado = PersonagemEscritorio.objects.update_or_create(
            colaborador=colaborador,
            defaults={
                "tipo_ator": PersonagemEscritorio.HUMAN_EMPLOYEE,
                "personagem": personagem,
                "sala_padrao": sala,
                "pos_x": options["pos_x"],
                "pos_y": options["pos_y"],
                "ativo": True,
            },
        )
        verbo = "criada" if criado else "atualizada"
        self.stdout.write(self.style.SUCCESS(f"Personagem {verbo}: {obj}"))

    def _listar(self):
        elenco = (
            PersonagemEscritorio.objects
            .select_related("colaborador", "sala_padrao").order_by("personagem")
        )
        if not elenco:
            self.stdout.write("Nenhuma personagem cadastrada.")
            return
        for p in elenco:
            sala = p.sala_padrao.slug if p.sala_padrao else "sem sala padrão"
            status = "ativa" if p.ativo else "inativa"
            self.stdout.write(
                f"[{p.pk}] {p.personagem} · {p.tipo_ator} · sala {sala} · "
                f"({p.pos_x},{p.pos_y}) · {status}"
                + (f" · colaborador_id={p.colaborador_id}" if p.colaborador_id else "")
            )

    def _listar_colaboradores(self):
        qs = Colaborador.objects.filter(ativo=True, registra_ponto=True).order_by("nome")
        for c in qs:
            tem = PersonagemEscritorio.objects.filter(colaborador=c).exists()
            marca = "já tem personagem" if tem else "sem personagem"
            self.stdout.write(f"[{c.pk}] {c.nome} · {c.cargo or 'sem cargo'} · {marca}")
