// Filtros ativos (pessoa/q/prazo) vivem só na querystring da página — lidos
// por qualquer ação (drag-and-drop via JS, ou hx-vals nos forms dos modais)
// pra preservar o que a pessoa filtrou mesmo depois de criar/editar/mover
// um card, sem precisar de estado duplicado em outro lugar.
function tarefasFiltroValor(nome) {
  return new URLSearchParams(location.search).get(nome) || '';
}
window.tarefasFiltroValor = tarefasFiltroValor;

// Textarea de descrição com auto-crescimento — só pra baixo, nunca pros
// lados (largura sempre 100%, sem "resize" de canto). Tamanho padrão até
// ~3 linhas (min-height no CSS); acima de max-height passa a rolar por
// dentro em vez de esticar sem limite.
function tarefasAutoGrow(el) {
  el.style.height = 'auto';
  const max = parseFloat(getComputedStyle(el).maxHeight) || 256;
  const altura = Math.min(el.scrollHeight, max);
  el.style.height = altura + 'px';
  el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden';
}

function tarefasAutoGrowTodas() {
  document.querySelectorAll('.ds-textarea-auto').forEach(tarefasAutoGrow);
}
window.tarefasAutoGrowTodas = tarefasAutoGrowTodas;

document.addEventListener('input', function (e) {
  if (e.target.matches && e.target.matches('.ds-textarea-auto')) {
    tarefasAutoGrow(e.target);
  }
});

// Modal (nova tarefa / editar tarefa) chega via htmx — ajusta a altura já
// no primeiro render, senão o textarea nasce do tamanho padrão mesmo tendo
// texto longo dentro (scrollHeight só é confiável depois de estar no DOM).
document.addEventListener('htmx:afterSwap', function () {
  tarefasAutoGrowTodas();
});

// Drag-and-drop do quadro de Tarefas.
//
// Antes era a HTML5 Drag and Drop API nativa. O problema: durante um arraste
// nativo o navegador sequestra o loop de input — no Chrome nao chega evento
// "wheel" pro JS e a pagina nao rola sozinha nas bordas. Com coluna longa, um
// card la embaixo simplesmente nao tinha como alcancar a coluna de destino.
// Aqui o arraste e feito na mao com Pointer Events: o scroll do mouse volta a
// funcionar normalmente e da pra fazer auto-scroll quando o cursor encosta no
// topo/rodape da janela.
(function () {
  var ZONA = 90;     // px do topo/rodape da janela que acionam o auto-scroll
  var VEL_MAX = 22;  // px por frame quando o cursor esta na borda da zona
  var LIMIAR = 6;    // px de movimento pra virar arraste (abaixo disso e clique)

  var pendente = null;   // pointerdown num card, ainda sem passar do limiar
  var arraste = null;    // arraste em andamento
  var frame = null;      // requestAnimationFrame do auto-scroll
  var corpoAtivo = null; // coluna destacada sob o cursor

  function alturaHeader() {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--header-h');
    return parseFloat(v) || 0;
  }

  function marcarCorpo(corpo) {
    if (corpoAtivo === corpo) return;
    if (corpoAtivo) corpoAtivo.classList.remove('arraste-sobre');
    corpoAtivo = corpo;
    if (corpoAtivo) corpoAtivo.classList.add('arraste-sobre');
  }

  // O ghost tem pointer-events:none, entao elementFromPoint enxerga a coluna
  // que esta debaixo dele e nao o proprio card sendo arrastado.
  function corpoSob(x, y) {
    var el = document.elementFromPoint(x, y);
    return el && el.closest ? el.closest('.kanban-coluna-corpo') : null;
  }

  function posicionarGhost() {
    arraste.ghost.style.left = (arraste.x - arraste.offsetX) + 'px';
    arraste.ghost.style.top = (arraste.y - arraste.offsetY) + 'px';
  }

  function loopScroll() {
    if (!arraste) { frame = null; return; }
    var limiteTopo = alturaHeader() + ZONA;
    var limiteBase = window.innerHeight - ZONA;
    var dy = 0;
    if (arraste.y < limiteTopo) {
      dy = -VEL_MAX * Math.min(1, (limiteTopo - arraste.y) / ZONA);
    } else if (arraste.y > limiteBase) {
      dy = VEL_MAX * Math.min(1, (arraste.y - limiteBase) / ZONA);
    }
    if (dy) {
      var antes = window.scrollY;
      window.scrollBy(0, dy);
      // A pagina andou embaixo de um cursor parado: o alvo mudou sem pointermove.
      if (window.scrollY !== antes) marcarCorpo(corpoSob(arraste.x, arraste.y));
    }
    frame = requestAnimationFrame(loopScroll);
  }

  function iniciar(card, x, y) {
    var r = card.getBoundingClientRect();
    var ghost = card.cloneNode(true);
    // Limpa o que so faz sentido no card original (htmx, id de tarefa).
    ['id', 'hx-get', 'hx-target', 'hx-trigger', 'data-tarefa-id', 'data-mover-url', 'draggable']
      .forEach(function (a) { ghost.removeAttribute(a); });
    ghost.style.cssText =
      'position:fixed;margin:0;pointer-events:none;z-index:1200;' +
      'width:' + r.width + 'px;opacity:.95;transform:rotate(1.5deg);' +
      'box-shadow:0 8px 20px rgba(0,0,0,.18);';
    document.body.appendChild(ghost);
    card.classList.add('arrastando');

    arraste = {
      card: card,
      ghost: ghost,
      tarefaId: card.dataset.tarefaId,
      moverUrl: card.dataset.moverUrl,
      offsetX: x - r.left,
      offsetY: y - r.top,
      x: x,
      y: y,
    };
    posicionarGhost();
    document.body.style.userSelect = 'none';
    marcarCorpo(corpoSob(x, y));
    frame = requestAnimationFrame(loopScroll);
  }

  function limpar() {
    if (frame) { cancelAnimationFrame(frame); frame = null; }
    if (arraste) {
      arraste.ghost.remove();
      arraste.card.classList.remove('arrastando');
    }
    marcarCorpo(null);
    document.body.style.userSelect = '';
    arraste = null;
  }

  // O card abre o modal no click (hx-trigger="click"). Depois de arrastar, o
  // navegador ainda dispara um click no ponto de solta — engole so esse.
  function engolirProximoClique() {
    var t = setTimeout(function () {
      document.removeEventListener('click', bloqueia, true);
    }, 300);
    function bloqueia(ev) {
      ev.stopPropagation();
      ev.preventDefault();
      clearTimeout(t);
      document.removeEventListener('click', bloqueia, true);
    }
    document.addEventListener('click', bloqueia, true);
  }

  document.addEventListener('pointerdown', function (e) {
    // Toque continua rolando a pagina normalmente (o arraste no celular exigiria
    // travar o touch-action do card e ai nao daria pra rolar a coluna com o dedo).
    if (e.button !== 0 || e.pointerType === 'touch') return;
    var card = e.target.closest ? e.target.closest('.kanban-card') : null;
    if (!card || !card.dataset.moverUrl) return;
    pendente = { card: card, x: e.clientX, y: e.clientY };
  });

  // Ouve no document (e nao via setPointerCapture) porque o quadro se
  // auto-atualiza a cada 15s: se o card for trocado no meio do arraste, o
  // elemento capturado sumiria junto com os eventos.
  document.addEventListener('pointermove', function (e) {
    if (pendente && !arraste) {
      var dist = Math.abs(e.clientX - pendente.x) + Math.abs(e.clientY - pendente.y);
      if (dist < LIMIAR) return;
      iniciar(pendente.card, e.clientX, e.clientY);
    }
    if (!arraste) return;
    arraste.x = e.clientX;
    arraste.y = e.clientY;
    posicionarGhost();
    marcarCorpo(corpoSob(e.clientX, e.clientY));
  });

  // Roda nativamente (nao damos preventDefault); so recalculamos, no frame
  // seguinte, qual coluna ficou embaixo do cursor depois que a pagina andou.
  window.addEventListener('wheel', function () {
    if (!arraste) return;
    requestAnimationFrame(function () {
      if (arraste) marcarCorpo(corpoSob(arraste.x, arraste.y));
    });
  }, { passive: true });

  document.addEventListener('pointerup', function (e) {
    pendente = null;
    if (!arraste) return;
    var destino = corpoSob(e.clientX, e.clientY);
    var moverUrl = arraste.moverUrl;
    limpar();
    engolirProximoClique();

    var statusId = destino && destino.dataset.statusId;
    if (!statusId || !moverUrl) return;

    htmx.ajax('POST', moverUrl, {
      target: '#kanban-board',
      swap: 'innerHTML',
      values: {
        status_id: statusId,
        pessoa: tarefasFiltroValor('pessoa'),
        q: tarefasFiltroValor('q'),
        prazo_de: tarefasFiltroValor('prazo_de'),
        prazo_ate: tarefasFiltroValor('prazo_ate'),
      },
      headers: { 'X-CSRFToken': window.DELLA_CSRF || '' },
    });
  });

  document.addEventListener('pointercancel', function () {
    pendente = null;
    limpar();
  });

  // O poll de 15s do quadro trocaria o card no meio do arraste (o ghost fica,
  // mas o card de origem some e a coluna destacada vira elemento morto).
  document.addEventListener('htmx:beforeRequest', function (e) {
    var elt = e.detail && e.detail.elt;
    var verbo = e.detail && e.detail.requestConfig && e.detail.requestConfig.verb;
    if (arraste && elt && elt.id === 'kanban-board' && verbo === 'get') {
      e.preventDefault();
    }
  });
})();
