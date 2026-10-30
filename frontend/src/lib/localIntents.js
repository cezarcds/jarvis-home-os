// Pedidos que o backend resolve sozinho (abrir programas, organizar a tela, olhar a tela).
// Sem isso, "o que você acha desse gráfico?" cairia no motor de cenas (explicações visuais).
// Espelha o que backend/actions/intents.py entende; na dúvida o backend decide.

const OPEN =
  /^(?:(?:por favor|pode|poderia|quero|queria|preciso|agora|entao) )*(?:me )?(?:abr(?:e|a|ir)|inicia(?:r)?|inicie|execut(?:a|ar|e)|lanc(?:a|ar|e)) /;
const NOT_APP = /\b(mapa|imagem|imagens|foto|fotos|video|videos|diagrama|grafico|desenho|rotina|rotinas|painel|admin|conversa)\b/;
const LAYOUT = /\b(organiz\w+|arrum\w+|divid\w+|ajust\w+|reorganiz\w+)\b.*\b(tela|janelas?)\b|\btela (toda|inteira|cheia)\b/;
const SCREEN = /\b(tela|janela|monitor)\b/;
const LOOK = /\b(olha|olhe|olhar|veja|ve|ver|analisa|analise|analisar|observa|observe|confere|confira|descreve|descreva|interpreta|comenta)\b/;
const SEEING = /\bo que (voce )?(esta|ta) vendo\b|\bo que (voce )?acha (disso|desse|deste|desta|dessa)\b/;
const MODE = /\b(modo|ativa\w*|liga\w*|entra\w*)\b.*\b(analise|copiloto|co piloto)\b|\banalisa(r)? comigo\b|\bacompanha\w* (minha|a) tela\b/;
const STOP = /\b(para|pare|parar|chega|deixa|deixe) de (olhar|ver|acompanhar|analisar)\b/;

/** `n` já vem normalizado (minúsculas, sem acento nem pontuação). */
export function isLocalCommand(n, visionActive = false) {
  const q = n.replace(/^((ei|oi|ola|ok|e ai) )?jarvis /, "");
  if (visionActive) return true; // modo análise: toda pergunta vai para o assistente, junto com a tela
  if (OPEN.test(q) && !NOT_APP.test(q)) return true;
  if (LAYOUT.test(q) || SEEING.test(q) || MODE.test(q) || STOP.test(q)) return true;
  if (LOOK.test(q) && (SCREEN.test(q) || /\b(isso|aqui|grafico|candles?)\b/.test(q))) return true;
  return false;
}
