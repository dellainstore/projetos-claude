/* ─── Della Instore — JavaScript Principal ────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {

  // ─── Navbar: transparente no hero, sólida ao rolar ─────────────────────────
  const navbar = document.getElementById('navbar');

  function atualizarNavbar() {
    if (!navbar) return;
    if (window.scrollY > 60) {
      navbar.classList.remove('transparente');
      navbar.classList.add('solida');
    } else {
      navbar.classList.add('transparente');
      navbar.classList.remove('solida');
    }
  }

  if (navbar) {
    atualizarNavbar();
    window.addEventListener('scroll', atualizarNavbar, { passive: true });
  }

  // ─── Hero: mute/unmute do vídeo ────────────────────────────────────────────
  const heroVideo  = document.getElementById('hero-video');
  const muteBtn    = document.getElementById('btn-mute');
  const muteIcon   = document.getElementById('mute-icon');

  if (heroVideo && muteBtn) {
    heroVideo.muted = true;

    muteBtn.addEventListener('click', () => {
      heroVideo.muted = !heroVideo.muted;
      muteIcon.className = heroVideo.muted ? 'fas fa-volume-mute' : 'fas fa-volume-up';
    });
  }

  // ─── Fade in ao scroll (IntersectionObserver) ──────────────────────────────
  const fadeLista = document.querySelectorAll('.fade-in');

  if (fadeLista.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visivel');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    fadeLista.forEach(el => observer.observe(el));
  }

  // ─── WhatsApp flutuante ────────────────────────────────────────────────────
  const whatsappBtn   = document.getElementById('whatsapp-fab-btn');
  const whatsappOpts  = document.getElementById('whatsapp-opcoes');

  if (whatsappBtn && whatsappOpts) {
    whatsappBtn.addEventListener('click', () => {
      const aberto = whatsappOpts.classList.toggle('aberto');
      whatsappBtn.setAttribute('aria-expanded', aberto);
    });

    // Fecha ao clicar fora
    document.addEventListener('click', (e) => {
      if (!whatsappBtn.closest('.whatsapp-fab').contains(e.target)) {
        whatsappOpts.classList.remove('aberto');
        whatsappBtn.setAttribute('aria-expanded', false);
      }
    });
  }

  // ─── Drawer do carrinho ────────────────────────────────────────────────────
  const drawerOverlay   = document.getElementById('drawer-overlay');
  const drawerCarrinho  = document.getElementById('drawer-carrinho');
  const btnAbrirCarrinho = document.querySelectorAll('[data-abrir-carrinho]');
  const btnFecharCarrinho = document.getElementById('btn-fechar-carrinho');

  function abrirCarrinho() {
    drawerOverlay?.classList.add('aberto');
    drawerCarrinho?.classList.add('aberto');
    document.body.style.overflow = 'hidden';
  }

  function fecharCarrinho() {
    drawerOverlay?.classList.remove('aberto');
    drawerCarrinho?.classList.remove('aberto');
    document.body.style.overflow = '';
  }

  btnAbrirCarrinho.forEach(btn => btn.addEventListener('click', abrirCarrinho));
  btnFecharCarrinho?.addEventListener('click', fecharCarrinho);
  drawerOverlay?.addEventListener('click', fecharCarrinho);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') fecharCarrinho();
  });

  // ─── Adicionar ao carrinho (AJAX) ──────────────────────────────────────────
  // Delegação de eventos: captura cliques em [data-produto-id] exceto no detalhe do produto
  // (o detalhe tem seu próprio handler no bloco js_extra para incluir variação + quantidade)
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-produto-id]');
    if (!btn) return;
    // O detalhe usa #btn-adicionar-carrinho — evita duplo disparo
    if (btn.id === 'btn-adicionar-carrinho') return;

    const produtoId  = btn.dataset.produtoId;
    const variacaoId = btn.dataset.variacaoId || '';
    const csrfToken  = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

    btn.disabled = true;
    const textoOriginal = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
      const res = await fetch(`/carrinho/adicionar/${produtoId}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ variacao_id: variacaoId, quantidade: 1 }),
      });

      const dados = await res.json();

      if (dados.status === 'ok') {
        atualizarDrawerConteudo(dados);
        abrirCarrinho();
        btn.innerHTML = '<i class="fas fa-check"></i>';
        setTimeout(() => { btn.innerHTML = textoOriginal; btn.disabled = false; }, 1500);
      }
    } catch (err) {
      btn.innerHTML = textoOriginal;
      btn.disabled = false;
    }
  });

  // ─── Atualizar conteúdo do drawer ─────────────────────────────────────────
  window.atualizarDrawerConteudo = function(dados) {
    const badge      = document.querySelector('.badge-carrinho');
    const totalValor = document.querySelector('.drawer-total-valor');
    const listaEl    = document.getElementById('drawer-itens-lista');

    if (badge) {
      badge.textContent = dados.total_itens;
      badge.style.display = dados.total_itens > 0 ? 'flex' : 'none';
    }

    if (totalValor && dados.total_valor !== undefined) {
      const valor = parseFloat(dados.total_valor);
      totalValor.textContent = 'R$ ' + valor.toFixed(2).replace('.', ',');
    }

    if (listaEl && dados.itens !== undefined) {
      if (dados.itens.length === 0) {
        listaEl.innerHTML = '<p class="text-center text-gray-400 text-sm mt-12 font-light">Seu carrinho está vazio.</p>';
      } else {
        listaEl.innerHTML = dados.itens.map(item => `
          <div class="drawer-item" data-chave="${item.chave}">
            <div class="drawer-item-foto">
              ${item.imagem ? `<img src="${item.imagem}" alt="${item.nome}" loading="lazy">` : '<div class="drawer-item-sem-foto"></div>'}
            </div>
            <div class="drawer-item-info">
              <p class="drawer-item-nome">${item.nome}</p>
              ${item.variacao ? `<p class="drawer-item-variacao">${item.variacao}</p>` : ''}
              <p class="drawer-item-preco">R$ ${parseFloat(item.subtotal).toFixed(2).replace('.', ',')}</p>
              <div class="drawer-item-qty">
                <button class="drawer-qty-btn" onclick="window.drawerAlterarQty('${item.chave}', ${item.quantidade - 1})">−</button>
                <span>${item.quantidade}</span>
                <button class="drawer-qty-btn" onclick="window.drawerAlterarQty('${item.chave}', ${item.quantidade + 1})">+</button>
              </div>
            </div>
            <button class="drawer-item-remover" onclick="window.drawerRemover('${item.chave}')" aria-label="Remover item">
              <i class="fas fa-times"></i>
            </button>
          </div>
        `).join('');
      }
    }
  };

  // Remover item pelo drawer
  window.drawerRemover = async function(chave) {
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    try {
      const res   = await fetch(`/carrinho/remover/${chave}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const dados = await res.json();
      if (dados.status === 'ok') window.atualizarDrawerConteudo(dados);
    } catch(e) {}
  };

  // Alterar quantidade pelo drawer
  window.drawerAlterarQty = async function(chave, quantidade) {
    if (quantidade < 1) { window.drawerRemover(chave); return; }
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    try {
      const res   = await fetch('/carrinho/atualizar/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ chave, quantidade }),
      });
      const dados = await res.json();
      if (dados.status === 'ok') window.atualizarDrawerConteudo(dados);
    } catch(e) {}
  };

  // ─── Wishlist toggle (AJAX) ────────────────────────────────────────────────
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-wishlist-id]');
    if (!btn) return;

    const produtoId = btn.dataset.wishlistId;
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

    try {
      const res = await fetch(`/wishlist/toggle/${produtoId}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const dados = await res.json();

      if (dados.status === 'ok') {
        btn.classList.toggle('ativo', dados.na_wishlist);
        const icon = btn.querySelector('i');
        if (icon) {
          icon.className = dados.na_wishlist ? 'fas fa-heart' : 'far fa-heart';
        }
      }
    } catch (err) { /* silencioso */ }
  });

  // ─── Newsletter (AJAX) ────────────────────────────────────────────────────
  const formNewsletter = document.getElementById('form-newsletter');

  if (formNewsletter) {
    formNewsletter.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = formNewsletter.querySelector('input[type="email"]').value.trim();
      const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      const btn = formNewsletter.querySelector('button[type="submit"]');
      const aviso = document.getElementById('newsletter-aviso');

      if (!email) return;

      btn.disabled = true;
      btn.textContent = 'Aguarde...';

      try {
        const res = await fetch('/newsletter/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({ email }),
        });

        const dados = await res.json();

        if (dados.status === 'ok') {
          formNewsletter.innerHTML = '<p style="color:var(--dourado);font-family:var(--fonte-titulo);font-style:italic;font-size:1.1rem;">Obrigada por se inscrever ✦</p>';
        } else {
          if (aviso) aviso.textContent = dados.erro || 'Tente novamente.';
          btn.disabled = false;
          btn.textContent = 'Inscrever-se';
        }
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Inscrever-se';
      }
    });
  }

  // ─── Menu mobile ──────────────────────────────────────────────────────────
  const btnMenuMobile   = document.getElementById('btn-menu-mobile');
  const menuMobilePanel = document.getElementById('menu-mobile');

  btnMenuMobile?.addEventListener('click', () => {
    const aberto = menuMobilePanel?.classList.toggle('aberto');
    btnMenuMobile.setAttribute('aria-expanded', aberto);
  });

});
