"""Testes da lógica pura (sem rede). Rode:  cd backend && python -m unittest discover -s tests -v"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from news import config, rss
from news.cache import TTLCache
from news.enrich import outlet_from_url, parse_meta
from news.hook import NewsContext, attach_news, inject_facts
from news.intent import detect
from news.research import facts_block
from news.safety import is_public_http_url

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google Notícias</title>
<item><title>Ibovespa fecha em alta com bancos - InfoMoney</title><link>https://news.google.com/rss/articles/AAA</link>
<pubDate>Sun, 25 Oct 2026 20:00:00 GMT</pubDate><source url="https://www.infomoney.com.br">InfoMoney</source></item>
<item><title>Dólar cai e fecha a R$ 5,10 - Valor Econômico</title><link>https://news.google.com/rss/articles/BBB</link>
<pubDate>Mon, 26 Oct 2026 12:00:00 GMT</pubDate><source url="https://valor.globo.com">Valor Econômico</source></item>
<item><title>Ibovespa fecha em alta com bancos - Outro Site</title><link>https://news.google.com/rss/articles/CCC</link>
<pubDate>Mon, 26 Oct 2026 11:00:00 GMT</pubDate><source url="https://outro.com">Outro Site</source></item>
<item><title></title><link>https://x.com</link></item>
</channel></rss>"""


class Intent(unittest.TestCase):
    def kind(self, t):
        i = detect(t)
        return i.kind if i else None

    def test_positivos(self):
        for t in [
            "me dá as últimas notícias do mercado",
            "o que aconteceu nas eleições do Brasil do último domingo?",
            "Jarvis, manchetes sobre o dólar",
            "o que rolou hoje no Ibovespa",
            "dólar hoje",
            "me atualiza sobre a Selic",
            "como foi a bolsa ontem",
        ]:
            self.assertEqual(self.kind(t), "search", t)

    def test_negativos(self):
        for t in [
            "que horas são",
            "o que aconteceu com o Império Romano?",
            "tenho uma boa notícia pra você",
            "acende a luz da sala",
            "quanto é 2 mais 2",
            "como foi a Revolução Francesa",
        ]:
            self.assertIsNone(detect(t), t)

    def test_briefing(self):
        self.assertEqual(self.kind("bom dia jarvis"), "briefing")
        self.assertEqual(self.kind("Bom dia, o que aconteceu com o dólar hoje?"), "search")

    def test_topico_e_janela(self):
        i = detect("o que rolou hoje no Ibovespa")
        self.assertEqual(i.topic, "mercado")
        self.assertEqual(i.when, "1d")
        self.assertIn("Ibovespa", i.short_query)
        self.assertNotIn("rolou", i.short_query)
        self.assertEqual(detect("o que aconteceu nas eleições do último domingo").topic, "politica")


class Rss(unittest.TestCase):
    def test_parse(self):
        items = rss.parse_rss(SAMPLE_RSS)
        self.assertEqual(len(items), 2)  # vazio descartado, duplicado por título descartado
        self.assertEqual(items[0]["outlet"], "Valor Econômico")  # mais recente primeiro
        self.assertEqual(items[0]["title"], "Dólar cai e fecha a R$ 5,10")
        self.assertTrue(items[0]["published"].startswith("2026-10-26"))

    def test_xml_invalido(self):
        self.assertEqual(rss.parse_rss("<nope"), [])

    def test_extra_feeds_agrupa(self):
        os.environ["NEWS_EXTRA_FEEDS"] = "mercado=https://a.com/rss, mercado=https://b.com/rss,cripto=https://c.com/rss,lixo,x=ftp://z"
        try:
            self.assertEqual(config.extra_feeds(), {"mercado": ["https://a.com/rss", "https://b.com/rss"], "cripto": ["https://c.com/rss"]})
            self.assertEqual(len(rss.topic_urls("mercado")), 3)
        finally:
            del os.environ["NEWS_EXTRA_FEEDS"]


class Enrich(unittest.TestCase):
    def test_meta(self):
        html = """<html><head><title>Fallback</title>
        <meta property="og:title" content="Título &amp; Cia">
        <meta property="og:image" content="/img/capa.jpg">
        <meta property="og:site_name" content="Meu Jornal">
        <meta property="article:published_time" content="2026-10-25T21:00:00-03:00"></head></html>"""
        m = parse_meta(html, "https://exemplo.com/a/b")
        self.assertEqual(m["title"], "Título & Cia")
        self.assertEqual(m["image"], "https://exemplo.com/img/capa.jpg")
        self.assertEqual(m["site_name"], "Meu Jornal")
        self.assertEqual(m["published"], "2026-10-25T21:00:00-03:00")

    def test_imagem_perigosa_descartada(self):
        self.assertIsNone(parse_meta('<meta property="og:image" content="javascript:alert(1)">', "https://a.com")["image"])

    def test_outlet(self):
        self.assertEqual(outlet_from_url("https://www.folha.uol.com.br/x"), "Folha de S.Paulo")
        self.assertEqual(outlet_from_url("https://g1.globo.com/y"), "g1")
        self.assertEqual(outlet_from_url("https://www.blogdofulano.com/z"), "blogdofulano.com")


class Safety(unittest.TestCase):
    def test_bloqueios(self):
        for u in ["http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.0.1/", "http://169.254.169.254/latest",
                  "http://[::1]/", "file:///etc/passwd", "ftp://8.8.8.8/", "javascript:alert(1)", "http:///x"]:
            self.assertFalse(is_public_http_url(u), u)

    def test_publico(self):
        self.assertTrue(is_public_http_url("https://8.8.8.8/"))


class Modelo(unittest.TestCase):
    def test_prefixo_litellm(self):
        os.environ["GEMINI_MODEL"] = "gemini/gemini-3.5-flash-lite"
        try:
            self.assertEqual(config.gemini_model(), "gemini-3.5-flash-lite")
        finally:
            del os.environ["GEMINI_MODEL"]


class Cache(unittest.TestCase):
    def test_ttl(self):
        c = TTLCache(ttl=0.05)
        c.set("a", 1)
        self.assertEqual(c.get("a"), 1)
        time.sleep(0.07)
        self.assertIsNone(c.get("a"))

    def test_maxsize(self):
        c = TTLCache(ttl=10, maxsize=2)
        for i in range(5):
            c.set(i, i)
        self.assertLessEqual(len(c._data), 2)


class Hook(unittest.TestCase):
    def test_inject_nao_muta_original(self):
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "e as eleições?"}]
        ctx = NewsContext("search", "q", None, [{"id": "1", "title": "T", "outlet": "O", "url": "u", "published": None, "image": None}], facts="FATOS")
        out = inject_facts(msgs, ctx)
        self.assertEqual(msgs[1]["content"], "e as eleições?")
        self.assertTrue(out[1]["content"].startswith("FATOS"))
        self.assertTrue(out[1]["content"].endswith("e as eleições?"))

    def test_attach(self):
        self.assertEqual(attach_news({"a": 1}, None), {"a": 1})
        self.assertNotIn("news", attach_news({"a": 1}, NewsContext("search", "q", None, [])))
        ctx = NewsContext("search", "q", "mercado", [{"id": "1", "title": "T"}])
        self.assertEqual(attach_news({}, ctx)["news"]["items"][0]["title"], "T")

    def test_completion(self):
        ctx = NewsContext("search", "q", None, [], answer="Olá")
        self.assertEqual(ctx.completion()["choices"][0]["message"]["content"], "Olá")

    def test_facts_block(self):
        b = facts_block([{"title": "Dólar cai", "outlet": "Valor", "published": "2026-10-26T12:00:00+00:00"}], "H")
        self.assertIn("[1] Valor (26/10 09:00): Dólar cai", b)


class HookAsync(unittest.IsolatedAsyncioTestCase):
    async def test_fluxo_com_answer(self):
        from news import hook
        from news.research import Research

        async def fake(intent, persona):
            return Research(intent.query, answer="Segundo a Folha...", items=[{"id": "1", "title": "T", "outlet": "Folha", "url": "u", "published": None, "image": None}], grounded=True)

        orig, hook.research = hook.research, fake
        try:
            ctx = await hook.prepare_news([{"role": "user", "content": "o que aconteceu nas eleições do último domingo?"}], "persona")
        finally:
            hook.research = orig
        self.assertEqual(ctx.answer, "Segundo a Folha...")
        self.assertTrue(ctx.payload()["grounded"])

    async def test_fluxo_sem_fontes_nao_inventa(self):
        from news import hook
        from news.research import Research

        async def fake(intent, persona):
            return Research(intent.query)

        orig, hook.research = hook.research, fake
        try:
            ctx = await hook.prepare_news([{"role": "user", "content": "últimas notícias do mercado"}], "p")
        finally:
            hook.research = orig
        self.assertIsNone(ctx.answer)
        self.assertIn("NÃO invente", ctx.facts)

    async def test_nao_noticia_devolve_none(self):
        from news import hook
        self.assertIsNone(await hook.prepare_news([{"role": "user", "content": "que horas são"}], "p"))

    async def test_desligado_por_env(self):
        from news import hook
        os.environ["NEWS_ENABLED"] = "0"
        try:
            self.assertIsNone(await hook.prepare_news([{"role": "user", "content": "últimas notícias"}], "p"))
        finally:
            del os.environ["NEWS_ENABLED"]


if __name__ == "__main__":
    unittest.main()
