"""Notícias dentro do motor de cenas (sem rede, sem chaves): construção da cena, saneamento e fluxos."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news import scene as ns
from news.hook import NewsContext
from scene_schema import sanitize_scene


def item(n, outlet="Folha de S.Paulo", image="https://img.example/a.jpg", published="2026-10-26T12:00:00+00:00"):
    return {"id": f"i{n}", "title": f"Manchete número {n}", "outlet": outlet, "url": f"https://site.example/{n}", "published": published, "image": image}


class Texto(unittest.TestCase):
    def test_clean_spoken(self):
        t = ns.clean_spoken("**Dólar** cai [1] segundo o [g1](https://g1.globo.com/x). Veja https://x.com/y agora.\n- item")
        self.assertNotIn("[", t)
        self.assertNotIn("http", t)
        self.assertNotIn("*", t)
        self.assertIn("Dólar cai segundo o g1.", t)

    def test_split_agrupa_frases_ate_o_limite(self):
        txt = "Primeira frase curta. Segunda frase curta. " + ("Terceira frase um pouco maior, com mais palavras para encher. " * 3)
        beats = ns.split_beats(txt, limit=100)
        self.assertGreater(len(beats), 1)
        self.assertTrue(all(len(b) <= 100 for b in beats))
        self.assertTrue(beats[0].startswith("Primeira frase curta. Segunda"))

    def test_frase_gigante_e_cortada_sem_perder_texto_e_respeita_o_maximo(self):
        gigante = ", ".join(f"parte {i} da frase" for i in range(40)) + "."
        beats = ns.split_beats(gigante, limit=120, max_beats=50)
        self.assertTrue(all(len(b) <= 120 for b in beats))
        self.assertEqual(" ".join(beats).replace(" ", ""), gigante.replace(" ", ""))
        self.assertEqual(len(ns.split_beats("Frase. " * 40, limit=30, max_beats=4)), 4)

    def test_veiculo_citado(self):
        self.assertTrue(ns.outlet_mentioned("Folha de S.Paulo", "Segundo a Folha, o dólar caiu."))
        self.assertTrue(ns.outlet_mentioned("g1", "De acordo com o g1, houve queda."))
        self.assertFalse(ns.outlet_mentioned("Valor Econômico", "O valor da moeda caiu."))
        self.assertTrue(ns.outlet_mentioned("Valor Econômico", "Segundo o Valor Econômico, caiu."))
        self.assertFalse(ns.outlet_mentioned("", "qualquer coisa"))

    def test_hora(self):
        self.assertEqual(ns._hora(None), "")
        self.assertEqual(ns._hora("lixo"), "")
        self.assertRegex(ns._hora("2020-01-02T15:00:00+00:00"), r"^\d\d/\d\d$")


class Cena(unittest.TestCase):
    def ctx(self, items, **kw):
        return NewsContext(kw.get("kind", "search"), kw.get("query", "o que aconteceu hoje com o dólar"), kw.get("topic", "mercado"), items)

    def test_cena_valida_com_cartoes_e_chamadas(self):
        items = [item(1, "Folha de S.Paulo"), item(2, "g1"), item(3, "Valor Econômico", image=None), item(4, "Reuters")]
        text = "Segundo a Folha, o dólar fechou em queda. De acordo com o g1, a bolsa subiu. Os números ainda divergem entre os veículos."
        s = ns.build_scene(text, self.ctx(items), provider="gemini-search")
        self.assertEqual(s["kind"], "news")
        self.assertEqual(len(s["media"]), 4)
        self.assertTrue(all(m["kind"] == "news" and m["news"]["url"].startswith("https://") for m in s["media"]))
        self.assertTrue(s["beats"])
        for b in s["beats"]:
            self.assertEqual(b["layout"], "media")
            self.assertLessEqual(len(b["show"]), 3)
            self.assertIn(b["media"], b["show"])
        first = s["beats"][0]
        folha = next(m["id"] for m in s["media"] if m["news"]["outlet"].startswith("Folha"))
        self.assertEqual(first["media"], folha)  # o veículo citado vira o cartão em destaque
        self.assertTrue(any(c["target"] == folha and "Folha" in c["text"] for c in first["callouts"]))
        self.assertTrue(s["id"] and s["answer"] and s["provider"] == "gemini-search")
        self.assertTrue(s["news"]["sources"] == 4)

    def test_capas_primeiro_e_sem_duplicar(self):
        items = [item(1, image=None), item(2), item(2), item(3, image=None), item(4)]
        picked = ns.pick_items(items)
        self.assertEqual([i["id"] for i in picked], ["i2", "i4", "i1", "i3"])

    def test_sem_fontes_vira_cena_so_de_fala(self):
        s = ns.build_scene("Não consegui buscar as notícias agora.", self.ctx([]))
        self.assertEqual(s["media"], [])
        self.assertEqual(s["beats"][0]["layout"], "title")

    def test_links_perigosos_nao_passam(self):
        bad = item(1)
        bad["url"] = "javascript:alert(1)"
        ok = item(2)
        ok["image"] = "data:text/html;base64,AAA"
        s = ns.build_scene("Segundo a Folha, algo aconteceu.", self.ctx([bad, ok]))
        self.assertEqual([m["news"]["url"] for m in s["media"]], ["https://site.example/2"])
        self.assertIsNone(s["media"][0]["news"]["image"])

    def test_titulo(self):
        self.assertEqual(ns.scene_title(NewsContext("briefing", "bom dia", None, [])), "Resumo do dia")
        self.assertTrue(ns.scene_title(self.ctx([], query="últimas notícias do mercado")).startswith("Notícias"))

    def test_schema_ignora_noticia_sem_dados_e_diretor_nao_cria_cartao(self):
        raw = {"title": "T", "media": [{"id": "a", "kind": "news", "query": "algo qualquer"}], "beats": [{"say": "Oi.", "layout": "media"}]}
        s = sanitize_scene(raw)
        self.assertEqual(s["media"][0]["kind"], "image")  # "news" sem dados válidos vira imagem comum
        self.assertNotIn("news", s["media"][0])

    def test_headline_fallback(self):
        self.assertIn("Não consegui", ns.headline_fallback(self.ctx([])))
        t = ns.headline_fallback(self.ctx([item(1, "g1")]))
        self.assertIn("g1: Manchete número 1.", t)


class Fluxo(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig = ns.prepare_news

    def tearDown(self):
        ns.prepare_news = self._orig
        sys.modules.pop("llm", None)

    async def test_nao_noticia_devolve_none(self):
        async def fake(messages, persona=""):
            return None
        ns.prepare_news = fake
        self.assertIsNone(await ns.news_scene_for([{"role": "user", "content": "que horas são"}], "p"))

    async def test_com_resposta_pesquisada(self):
        async def fake(messages, persona=""):
            c = NewsContext("search", "dólar hoje", "mercado", [item(1), item(2, "g1")], answer="Segundo a Folha, o dólar caiu. [1]", grounded=True)
            return c
        ns.prepare_news = fake
        s = await ns.news_scene_for([{"role": "user", "content": "dólar hoje"}], "p")
        self.assertEqual(s["provider"], "gemini-search")
        self.assertNotIn("[1]", s["answer"])
        self.assertEqual(len(s["media"]), 2)

    async def test_rss_resumido_pelo_llm_do_projeto(self):
        async def fake(messages, persona=""):
            return NewsContext("search", "mercado", "mercado", [item(1)], facts="FATOS")
        calls = {}

        async def complete(msgs, system=None, **kw):
            calls["msgs"], calls["system"] = msgs, system
            return "Segundo a Folha, o mercado subiu.", "groq"
        ns.prepare_news = fake
        sys.modules["llm"] = types.SimpleNamespace(complete=complete, LLMError=RuntimeError)
        s = await ns.news_scene_for([{"role": "system", "content": "x"}, {"role": "user", "content": "notícias do mercado"}], "persona")
        self.assertEqual(s["provider"], "groq")
        self.assertTrue(calls["msgs"][-1]["content"].startswith("FATOS"))
        self.assertTrue(all(m["role"] != "system" for m in calls["msgs"]))
        self.assertEqual(calls["system"], "persona")

    async def test_llm_fora_do_ar_fala_as_manchetes_sem_inventar(self):
        async def fake(messages, persona=""):
            return NewsContext("search", "mercado", "mercado", [item(1, "g1")], facts="FATOS")

        async def complete(*a, **k):
            raise RuntimeError("sem provedor")
        ns.prepare_news = fake
        sys.modules["llm"] = types.SimpleNamespace(complete=complete, LLMError=RuntimeError)
        s = await ns.news_scene_for([{"role": "user", "content": "notícias do mercado"}], "p")
        self.assertEqual(s["provider"], "manchetes")
        self.assertIn("g1: Manchete número 1.", s["answer"])

    async def test_erro_inesperado_nao_derruba(self):
        async def boom(messages, persona=""):
            raise ValueError("falha")
        ns.prepare_news = boom
        self.assertIsNone(await ns.news_scene_for([{"role": "user", "content": "notícias"}], "p"))


if __name__ == "__main__":
    unittest.main()
