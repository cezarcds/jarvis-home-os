$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$files = @{
  App = Join-Path $root "frontend/src/App.jsx"
  Nav = Join-Path $root "frontend/src/components/NavRail.jsx"
  Resolver = Join-Path $root "frontend/src/stage/useMediaResolver.js"
  NewsScene = Join-Path $root "backend/news/scene.py"
}

foreach ($entry in $files.GetEnumerator()) {
  if (-not (Test-Path -LiteralPath $entry.Value)) {
    throw "Arquivo não encontrado: $($entry.Value). Execute este script na raiz do jarvis-home-os."
  }
}

function Replace-ExactlyOnce {
  param(
    [string]$Source,
    [string]$Old,
    [string]$New,
    [string]$Description
  )
  $Source = $Source.Replace("`r`n", "`n")
  $Old = $Old.Replace("`r`n", "`n")
  $New = $New.Replace("`r`n", "`n")
  $count = ([regex]::Matches($Source, [regex]::Escape($Old))).Count
  if ($count -ne 1) {
    throw "Não foi possível aplicar '$Description': esperado 1 trecho, encontrado $count. Nenhum arquivo foi alterado. Confirme se seu projeto está na versão esperada."
  }
  return $Source.Replace($Old, $New)
}

# Lê e prepara todas as alterações antes de gravar qualquer arquivo.
$app = [System.IO.File]::ReadAllText($files.App).Replace("`r`n", "`n")
$nav = [System.IO.File]::ReadAllText($files.Nav).Replace("`r`n", "`n")
$resolver = [System.IO.File]::ReadAllText($files.Resolver).Replace("`r`n", "`n")
$news = [System.IO.File]::ReadAllText($files.NewsScene).Replace("`r`n", "`n")

$app = Replace-ExactlyOnce $app 'import HeadlinesCard from "./components/news/HeadlinesCard.jsx";' "`"__REMOVE_HEADLINES_IMPORT__`"" "remover import do painel de manchetes"
$app = $app.Replace("`"__REMOVE_HEADLINES_IMPORT__`"`r`n", "")
$app = $app.Replace("`"__REMOVE_HEADLINES_IMPORT__`"`n", "")
if ($app.Contains("__REMOVE_HEADLINES_IMPORT__")) { throw "Falha ao remover import do painel de manchetes." }

$app = Replace-ExactlyOnce $app @'
            onSettings={() => goTo("ADMIN")}
            mic={{
'@ @'
            onSettings={() => goTo("ADMIN")}
            onNews={() => sendVisual("Pesquise notícias recentes sobre os principais acontecimentos do Brasil e do mundo, explique o contexto e mostre imagens e vídeos relacionados.")}
            mic={{
'@ "adicionar atalho de notícias ao NavRail"

$app = Replace-ExactlyOnce $app @'
                  <LeftPanels />
                  <HeadlinesCard />
'@ @'
                  <LeftPanels />
'@ "retirar notícias permanentes da tela inicial"

$nav = Replace-ExactlyOnce $nav '  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,' @'
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  newspaper: <><path d="M4 4h14v16H4z" /><path d="M18 8h2v10a2 2 0 01-2 2M7 8h8M7 12h8M7 16h5" /></>,
'@ "adicionar ícone de notícias"

$nav = Replace-ExactlyOnce $nav 'export default function NavRail({ phase, onHome, onRoutines, onSettings, mic }) {' 'export default function NavRail({ phase, onHome, onRoutines, onSettings, onNews, mic }) {' "adicionar callback de notícias"

$nav = Replace-ExactlyOnce $nav @'
      <Item icon="list" label="Rotinas" onClick={onRoutines} title="Painel de rotinas (Alt+R)" />
      <Item icon="sliders" label="Config" onClick={onSettings} title="Conexões e configurações" />
'@ @'
      <Item icon="list" label="Rotinas" onClick={onRoutines} title="Painel de rotinas (Alt+R)" />
      <Item icon="newspaper" label="Notícias" onClick={onNews} title="Pesquisar notícias e abrir apresentação visual" />
      <Item icon="sliders" label="Config" onClick={onSettings} title="Conexões e configurações" />
'@ "adicionar item Notícias ao menu lateral"

$resolver = Replace-ExactlyOnce $resolver @'
          if (image) {
            try { await preloadImage(image); } catch { image = null; }
          }
'@ @'
          if (image) {
            try { await preloadImage(image); } catch { image = null; }
          }
          // Sem capa válida? Busca uma imagem complementar no mesmo serviço de mídia do palco.
          if (!image) {
            try {
              const found = await searchMediaAll(m.query || m.news.title, "image");
              const candidates = [found?.item, ...(found?.alternatives || [])].filter(Boolean);
              for (const candidate of candidates) {
                const url = candidate.url || candidate.fallback_url;
                if (!url) continue;
                try { await preloadImage(url); image = url; break; }
                catch { /* tenta o próximo candidato */ }
              }
            } catch (err) {
              console.warn("[JARVIS] Imagem complementar indisponível:", err.message);
            }
          }
'@ "buscar imagem quando a notícia não tem capa"

$news = Replace-ExactlyOnce $news @'
    items = pick_items(ctx.items)
    media = [
        {
            "id": f"n{i + 1}", "kind": "news", "query": it["title"][:80], "caption": "",
            "news": {k: it.get(k) for k in ("title", "outlet", "url", "image", "published")},
        }
        for i, it in enumerate(items)
    ]
    by_id = {m["id"]: it for m, it in zip(media, items)}

    beats = []
'@ @'
    # Reserva espaço para quatro cartões de reportagem e dois vídeos relacionados.
    # O limite MAX_MEDIA do scene_schema é seis itens por cena.
    items = pick_items(ctx.items)[:4]
    media = [
        {
            "id": f"n{i + 1}", "kind": "news", "query": it["title"][:80], "caption": "",
            "news": {k: it.get(k) for k in ("title", "outlet", "url", "image", "published")},
        }
        for i, it in enumerate(items)
    ]
    by_id = {m["id"]: it for m, it in zip(media, items)}
    for i, it in enumerate(items[:2]):
        media.append({
            "id": f"v{i + 1}", "kind": "video", "query": it["title"][:80],
            "caption": "Vídeo relacionado",
        })

    beats = []
'@ "adicionar vídeos relacionados às cenas de notícias"

$news = Replace-ExactlyOnce $news @'
        n = min(SHOW, len(media))
        start = (i * 2) % len(media)
        window = [media[(start + k) % len(media)]["id"] for k in range(n)]
        cited = [m["id"] for m in media if outlet_mentioned(by_id[m["id"]].get("outlet") or "", say)]
        featured = cited[0] if cited else window[0]
        show = [featured] + [w for w in window if w != featured][: n - 1]
'@ @'
        n = min(SHOW, len(items))
        start = (i * 2) % len(items)
        window = [f"n{(start + k) % len(items) + 1}" for k in range(n)]
        cited = [f"n{j + 1}" for j, it in enumerate(items) if outlet_mentioned(it.get("outlet") or "", say)]
        featured = cited[0] if cited else window[0]
        # Mantém matérias como fonte principal e intercala vídeos reais encontrados pelo Media Engine.
        video_id = f"v{(i % min(2, len(items))) + 1}"
        show = [featured] + [w for w in window if w != featured][:1]
        if video_id in {m["id"] for m in media}:
            show.append(video_id)
'@ "intercalar vídeos no mural de notícias"

# Backups e gravação: só começa depois de validar todos os trechos.
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targets = @(
  @{ Path = $files.App; Content = $app },
  @{ Path = $files.Nav; Content = $nav },
  @{ Path = $files.Resolver; Content = $resolver },
  @{ Path = $files.NewsScene; Content = $news }
)

foreach ($target in $targets) {
  Copy-Item -LiteralPath $target.Path -Destination ($target.Path + ".bak-" + $stamp)
}
foreach ($target in $targets) {
  [System.IO.File]::WriteAllText($target.Path, $target.Content, [System.Text.UTF8Encoding]::new($false))
}

Write-Host ""
Write-Host "Atualização aplicada com sucesso." -ForegroundColor Green
Write-Host "Backups originais criados ao lado dos arquivos com sufixo .bak-$stamp"
Write-Host ""
Write-Host "O que mudou:"
Write-Host " - Manchetes removidas da tela inicial."
Write-Host " - Novo item Notícias no menu lateral; abre o palco de cenas sob demanda."
Write-Host " - Notícias sem capa válida tentam buscar imagem pelo Media Engine."
Write-Host " - Cenas de notícias podem incluir até dois vídeos relacionados."
Write-Host ""
Write-Host "Próximo passo: execute seu fluxo normal de desenvolvimento e teste uma busca de notícias."
