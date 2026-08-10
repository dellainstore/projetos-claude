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

// Drag-and-drop do quadro de Tarefas — HTML5 Drag and Drop API nativa,
// sem biblioteca extra. No "drop", chama htmx.ajax contra o endpoint de
// mover status; a resposta substitui o quadro inteiro (dataset pequeno,
// dispensa otimizar por card).
(function () {
  document.addEventListener('dragstart', function (e) {
    const card = e.target.closest('.kanban-card');
    if (!card) return;
    card.classList.add('arrastando');
    e.dataTransfer.setData('text/plain', card.dataset.tarefaId);
    e.dataTransfer.effectAllowed = 'move';
  });

  document.addEventListener('dragend', function (e) {
    const card = e.target.closest('.kanban-card');
    if (card) card.classList.remove('arrastando');
  });

  document.addEventListener('dragover', function (e) {
    const corpo = e.target.closest('.kanban-coluna-corpo');
    if (!corpo) return;
    e.preventDefault();
    corpo.classList.add('arraste-sobre');
  });

  document.addEventListener('dragleave', function (e) {
    const corpo = e.target.closest('.kanban-coluna-corpo');
    if (corpo) corpo.classList.remove('arraste-sobre');
  });

  document.addEventListener('drop', function (e) {
    const corpo = e.target.closest('.kanban-coluna-corpo');
    if (!corpo) return;
    e.preventDefault();
    corpo.classList.remove('arraste-sobre');

    const tarefaId = e.dataTransfer.getData('text/plain');
    const statusId = corpo.dataset.statusId;
    const card = document.querySelector('.kanban-card[data-tarefa-id="' + tarefaId + '"]');
    if (!card || !statusId) return;

    htmx.ajax('POST', card.dataset.moverUrl, {
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
})();
