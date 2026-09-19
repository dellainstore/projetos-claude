"""Testes da resolução de sala (loja da batida -> sala mapeada -> padrão -> fallback)."""

from apps.escritorio_virtual.models import PersonagemEscritorio, SalaEscritorio
from apps.escritorio_virtual.services import salas as svc_salas
from apps.escritorio_virtual.services.projecao import EstadoPersonagem, projetar_cena
from apps.escritorio_virtual.tests.test_projecao import (
    SEGUNDA_A,
    BaseEscritorioTestCase,
    hoje_fixo,
)


class ResolucaoDeSalaTests(BaseEscritorioTestCase):

    def _sala_trabalho(self, dia=SEGUNDA_A):
        cena = projetar_cena(dia=dia)
        return cena.atores[0].sala_trabalho

    def test_loja_conhecida_resolve_pela_loja(self):
        self.dia_completo(SEGUNDA_A, loja="sp")
        r = self._sala_trabalho()
        self.assertEqual(r.slug, "showroom")
        self.assertEqual(r.origem, svc_salas.ORIGEM_LOJA)
        self.assertIsNone(r.aviso)

    def test_outra_loja_resolve_para_outra_sala(self):
        self.dia_completo(SEGUNDA_A, loja="anaca")
        r = self._sala_trabalho()
        self.assertEqual(r.slug, "anaca")
        self.assertEqual(r.origem, svc_salas.ORIGEM_LOJA)

    def test_usa_a_loja_da_batida_mais_recente(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada", loja="sp")
        self.bater(SEGUNDA_A, 12, 0, "saida_almoco", loja="sp")
        self.bater(SEGUNDA_A, 13, 0, "volta_almoco", loja="anaca")
        self.bater(SEGUNDA_A, 19, 0, "saida", loja="anaca")
        self.assertEqual(self._sala_trabalho().slug, "anaca")

    def test_loja_sem_sala_mapeada_cai_na_sala_padrao_com_aviso(self):
        self.showroom2.loja = None
        self.showroom2.save(update_fields=["loja"])
        self.dia_completo(SEGUNDA_A, loja="anaca")
        r = self._sala_trabalho()
        self.assertEqual(r.origem, svc_salas.ORIGEM_SALA_PADRAO)
        self.assertEqual(r.slug, "showroom")
        self.assertEqual(r.aviso, "loja_sem_sala_mapeada")

    def test_batida_sem_loja_cai_na_sala_padrao(self):
        self.dia_completo(SEGUNDA_A, loja=None)
        r = self._sala_trabalho()
        self.assertEqual(r.origem, svc_salas.ORIGEM_SALA_PADRAO)
        self.assertEqual(r.slug, "showroom")
        self.assertIsNone(r.aviso)

    def test_sem_batida_nenhuma_usa_sala_padrao(self):
        r = self._sala_trabalho()
        self.assertEqual(r.origem, svc_salas.ORIGEM_SALA_PADRAO)
        self.assertEqual(r.slug, "showroom")

    def test_personagem_sem_sala_padrao_usa_entrada_como_fallback(self):
        self.personagem.sala_padrao = None
        self.personagem.save(update_fields=["sala_padrao"])
        self.dia_completo(SEGUNDA_A, loja=None)
        r = self._sala_trabalho()
        self.assertEqual(r.origem, svc_salas.ORIGEM_FALLBACK)
        self.assertEqual(r.slug, svc_salas.SLUG_ENTRADA)
        self.assertEqual(r.aviso, "personagem_sem_sala_padrao")

    def test_sala_padrao_inativa_cai_no_fallback(self):
        self.showroom1.ativo = False
        self.showroom1.save(update_fields=["ativo"])
        self.dia_completo(SEGUNDA_A, loja=None)
        r = self._sala_trabalho()
        self.assertEqual(r.origem, svc_salas.ORIGEM_FALLBACK)
        self.assertEqual(r.slug, svc_salas.SLUG_ENTRADA)

    def test_sem_nenhuma_sala_configurada_nao_quebra(self):
        SalaEscritorio.objects.all().delete()
        self.dia_completo(SEGUNDA_A, loja="sp")
        cena = projetar_cena(dia=SEGUNDA_A)
        r = cena.atores[0].sala_trabalho
        self.assertIsNone(r.sala)
        self.assertEqual(r.origem, svc_salas.ORIGEM_INDEFINIDA)
        self.assertIn("sem_salas_configuradas", cena.avisos)

    def test_mapa_loja_para_sala_ignora_sala_inativa(self):
        self.showroom1.ativo = False
        self.showroom1.save(update_fields=["ativo"])
        mapa = svc_salas.mapa_loja_para_sala()
        self.assertNotIn(self.loja_sp.pk, mapa)
        self.assertIn(self.loja_anaca.pk, mapa)


class SalaDaCenaTests(BaseEscritorioTestCase):
    """A sala exibida depende do estado, não só da loja."""

    def test_almoco_leva_ao_refeitorio_mantendo_a_sala_de_trabalho(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada", loja="anaca")
            self.bater(SEGUNDA_A, 12, 0, "saida_almoco", loja="anaca")
            ator = self.ator(dia=SEGUNDA_A, agora=self._agora(12, 30))
        self.assertEqual(ator.estado, EstadoPersonagem.LUNCH)
        self.assertEqual(ator.sala.slug, svc_salas.SLUG_REFEITORIO)
        self.assertEqual(ator.sala_trabalho.slug, "anaca")

    def test_sem_refeitorio_configurado_avisa_e_mantem_a_sala(self):
        self.refeitorio.delete()
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
            ator = self.ator(dia=SEGUNDA_A, agora=self._agora(12, 30))
        self.assertEqual(ator.sala.slug, "showroom")
        self.assertIn("sem_refeitorio_configurado", ator.avisos)

    def test_estados_sem_presenca_nao_renderizam_sala(self):
        for estado_esperado, montar in (
            (EstadoPersonagem.MISSING_PUNCH, lambda: self.bater(SEGUNDA_A, 9, 0, "entrada")),
            (EstadoPersonagem.ABSENT, lambda: None),
        ):
            with self.subTest(estado=estado_esperado):
                from apps.rh.models import BatidaPonto
                BatidaPonto.objects.filter(colaborador=self.colab).delete()
                montar()
                ator = self.ator(dia=SEGUNDA_A)
                self.assertEqual(ator.estado, estado_esperado)
                self.assertIsNone(ator.sala.sala)

    def _agora(self, hora, minuto=0):
        from apps.escritorio_virtual.tests.test_projecao import aware
        return aware(SEGUNDA_A, hora, minuto)


class ConfiguracaoDoPersonagemTests(BaseEscritorioTestCase):

    def test_personagem_inativa_sai_da_cena(self):
        self.personagem.ativo = False
        self.personagem.save(update_fields=["ativo"])
        cena = projetar_cena(dia=SEGUNDA_A)
        self.assertEqual(cena.atores, [])

    def test_humano_sem_colaborador_e_rejeitado_pelo_banco(self):
        from django.db.utils import IntegrityError
        with self.assertRaises(IntegrityError):
            PersonagemEscritorio.objects.create(
                tipo_ator=PersonagemEscritorio.HUMAN_EMPLOYEE, personagem="fantasma",
            )

    def test_ator_nao_humano_com_colaborador_e_rejeitado_pelo_banco(self):
        from django.db.utils import IntegrityError
        with self.assertRaises(IntegrityError):
            PersonagemEscritorio.objects.create(
                tipo_ator=PersonagemEscritorio.AI_AGENT, personagem="bot",
                colaborador=self.colab,
            )
