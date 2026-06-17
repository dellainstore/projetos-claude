document.addEventListener('DOMContentLoaded', () => {
  const csrfToken =
    document.querySelector('meta[name="csrf-token"]')?.content ||
    document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
    '';

  function fmtBRL(value) {
    const partes = value.toFixed(2).split('.');
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'R$ ' + partes.join(',');
  }

  async function removerItem(chave) {
    try {
      const res = await fetch(`/carrinho/remover/${chave}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const dados = await res.json();
      if (dados.status === 'ok') {
        document.getElementById(`item-${chave}`)?.remove();
        atualizarResumo(dados);
        if (dados.total_itens === 0) location.reload();
      }
    } catch (_) {}
  }

  function atualizarPagina(dados, chave, novaQty) {
    const qtyEl = document.getElementById(`qty-${chave}`);
    if (qtyEl) qtyEl.textContent = novaQty;

    const itemEl = document.getElementById(`item-${chave}`);
    const precoUnitText = itemEl?.querySelector('.carrinho-item-preco-unit')?.textContent || '';
    const precoUnit = parseFloat(precoUnitText.replace('R$', '').replace(/\./g, '').replace(',', '.').trim());
    const subEl = document.getElementById(`sub-${chave}`);
    if (subEl && !Number.isNaN(precoUnit)) {
      subEl.textContent = fmtBRL(precoUnit * novaQty);
    }

    atualizarResumo(dados);
  }

  function atualizarResumo(dados) {
    const badge = document.querySelector('.badge-carrinho');
    const resumoQtd = document.getElementById('resumo-qtd');
    const resumoSubtotal = document.getElementById('resumo-subtotal');
    const resumoTotal = document.getElementById('resumo-total');
    const drawerTotal = document.querySelector('.drawer-total-valor');
    const total = parseFloat(dados.total_valor);
    const totalFmt = fmtBRL(total);

    if (badge) badge.textContent = dados.total_itens;
    if (resumoQtd) resumoQtd.textContent = dados.total_itens;
    if (resumoSubtotal) resumoSubtotal.textContent = totalFmt;
    if (resumoTotal) resumoTotal.textContent = totalFmt;
    if (drawerTotal) drawerTotal.textContent = totalFmt;

    atualizarFreteProgresso(total);
  }

  function atualizarFreteProgresso(total) {
    const wrap = document.getElementById('frete-progresso');
    if (!wrap) return;
    const meta = parseFloat(wrap.dataset.meta || '0');
    if (!meta) return;
    const fill = document.getElementById('frete-progresso-fill');
    const msg = document.getElementById('frete-progresso-msg');
    const faltante = Math.max(0, meta - total);
    const percentual = Math.min(100, (total / meta) * 100);
    if (fill) fill.style.width = percentual + '%';
    wrap.dataset.total = String(total);
    if (!msg) return;
    if (faltante <= 0) {
      wrap.classList.add('conquistado-state');
      msg.classList.add('conquistado');
      msg.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Você ganhou frete grátis';
    } else {
      wrap.classList.remove('conquistado-state');
      msg.classList.remove('conquistado');
      msg.innerHTML = 'Faltam <strong>' + fmtBRL(faltante) + '</strong> para frete grátis';
    }
  }

  document.querySelectorAll('.carrinho-qty-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const chave = btn.dataset.chave;
      const acao = btn.dataset.acao;
      const qtyEl = document.getElementById(`qty-${chave}`);
      let qty = parseInt(qtyEl?.textContent || '1', 10);

      if (acao === 'diminuir') qty -= 1;
      else qty += 1;

      if (qty < 1) {
        await removerItem(chave);
        return;
      }

      try {
        const res = await fetch('/carrinho/atualizar/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
          body: JSON.stringify({ chave, quantidade: qty }),
        });
        const dados = await res.json();
        if (dados.status === 'ok') atualizarPagina(dados, chave, qty);
      } catch (_) {}
    });
  });

  document.querySelectorAll('.carrinho-item-remover').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await removerItem(btn.dataset.chave);
    });
  });
});
