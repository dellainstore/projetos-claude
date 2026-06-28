/* ─── Della Instore — JavaScript Principal ────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  const gaMeasurementId = document.body.dataset.gaMeasurementId || '';
  const clarityProjectId = document.body.dataset.clarityProjectId || '';

  // ─── UTM capture — persiste atribuicao por 30 dias em localStorage e cookie ─
  (function () {
    const UTM_KEY     = 'della_utms';
    const ATTR_COOKIE = 'della_attr';
    const UTM_TTL     = 30 * 24 * 60 * 60 * 1000;
    const COOKIE_DAYS = 30;
    const params      = new URLSearchParams(window.location.search);
    const keys        = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id'];
    const captured    = {};
    keys.forEach(k => { if (params.get(k)) captured[k] = params.get(k); });
    // Captura gclid e fbclid da URL para incluir no cookie de atribuicao
    if (params.get('gclid'))  captured.gclid  = params.get('gclid');
    if (params.get('fbclid')) captured.fbclid = params.get('fbclid');
    if (Object.keys(captured).length) {
      captured._ts = Date.now();
      try { localStorage.setItem(UTM_KEY, JSON.stringify(captured)); } catch (_) {}
      // Cookie legivel pelo backend: localStorage nao chega ao servidor
      try {
        const val = encodeURIComponent(JSON.stringify(captured));
        const exp = new Date(Date.now() + COOKIE_DAYS * 864e5).toUTCString();
        document.cookie = ATTR_COOKIE + '=' + val + '; expires=' + exp + '; path=/; SameSite=Lax';
      } catch (_) {}
    }
    window.dellaGetUTMs = function () {
      try {
        const raw = localStorage.getItem(UTM_KEY);
        if (!raw) return null;
        const d = JSON.parse(raw);
        if (Date.now() - (d._ts || 0) > UTM_TTL) { localStorage.removeItem(UTM_KEY); return null; }
        return d;
      } catch (_) { return null; }
    };
  })();

  function carregarGA() {
    if (!gaMeasurementId || window._gaCarregado) return;
    window._gaCarregado = true;

    const script = document.createElement('script');
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + gaMeasurementId;
    script.async = true;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
      window.dataLayer.push(arguments);
    };
    window.gtag('js', new Date());
    window.gtag('config', gaMeasurementId);

    // Dispara eventos de ecommerce registrados pelo template (view_item, purchase, etc.)
    dispararGAEventosCustom();
  }

  function carregarClarity() {
    if (!clarityProjectId || window._clarityCarregado) return;
    window._clarityCarregado = true;
    (function(c,l,a,r,i,t,y){
      c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
      t=l.createElement(r);t.async=1;t.src='https://www.clarity.ms/tag/'+i;
      y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window,document,'clarity','script',clarityProjectId);
  }

  // ─── Navbar: transparente no hero, sólida ao rolar ─────────────────────────
  const navbar = document.getElementById('navbar');
  // Se a página já iniciou com navbar sólida (ex: home com hero abaixo do menu),
  // não aplicar o efeito de transparência ao scroll.
  const navbarComEfeitoScroll = navbar && navbar.classList.contains('transparente');

  function atualizarNavbar() {
    if (!navbar || !navbarComEfeitoScroll) return;
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

  // ─── Hero: swap vídeo mobile antes do autoplay ─────────────────────────────
  if (window.innerWidth < 768) {
    document.querySelectorAll('.hero-video[data-src-mobile]').forEach(function(v) {
      const src = v.querySelector('source');
      if (src) { src.src = v.dataset.srcMobile; v.load(); }
    });
  }

  // Força play em todos os vídeos do hero (alguns navegadores bloqueiam autoplay
  // após .load(); chamar .play() explicitamente com muted=true é permitido)
  document.querySelectorAll('.hero-video').forEach(function(v) {
    v.muted = true;
    const tryPlay = () => v.play().catch(() => {});
    tryPlay();
    v.addEventListener('loadeddata', tryPlay, { once: true });
    v.addEventListener('canplay', tryPlay, { once: true });
  });

  // ─── Hero Slider ───────────────────────────────────────────────────────────
  const heroSlides    = document.querySelectorAll('.hero-slide');
  const heroDots      = document.querySelectorAll('.hero-dot');
  const heroProgress  = document.getElementById('hero-progress');
  const muteBtn       = document.getElementById('btn-mute');
  const muteIcon      = document.getElementById('mute-icon');
  const SLIDE_DURACAO = 6000; // 6 segundos por slide
  let slideAtual  = 0;
  let sliderTimer = null;
  let progressTimer = null;

  function videoAtivoHero() {
    return heroSlides.length > 0 ? heroSlides[slideAtual]?.querySelector('video') : null;
  }

  function atualizarControleAudioHero() {
    if (!muteBtn || !muteIcon) return;
    const video = videoAtivoHero();
    if (!video) {
      muteBtn.hidden = true;
      return;
    }
    muteBtn.hidden = false;
    muteIcon.className = video.muted ? 'fas fa-volume-mute' : 'fas fa-volume-up';
  }

  function iniciarProgressBar() {
    if (!heroProgress) return;
    heroProgress.style.transition = 'none';
    heroProgress.style.width = '0%';
    // força reflow antes de iniciar a animação
    void heroProgress.offsetWidth;
    heroProgress.style.transition = `width ${SLIDE_DURACAO}ms linear`;
    heroProgress.style.width = '100%';
  }

  function irParaSlide(idx) {
    if (!heroSlides.length) return;

    // Slide anterior
    const slideAnt = heroSlides[slideAtual];
    heroDots[slideAtual]?.classList.remove('ativo');
    heroDots[slideAtual]?.setAttribute('aria-selected', 'false');
    slideAnt.classList.remove('ativo');

    // Pausar vídeo se estava no slide de vídeo
    const videoAnt = slideAnt.querySelector('video');
    if (videoAnt) videoAnt.pause();

    slideAtual = idx;
    const slideNovo = heroSlides[slideAtual];
    slideNovo.classList.add('ativo');
    heroDots[slideAtual]?.classList.add('ativo');
    heroDots[slideAtual]?.setAttribute('aria-selected', 'true');

    // Tocar vídeo no novo slide se for vídeo
    const videoNovo = slideNovo.querySelector('video');
    if (videoNovo) {
      videoNovo.currentTime = 0;
      videoNovo.play().catch(() => {});
    }

    atualizarControleAudioHero();
    iniciarProgressBar();
  }

  function proximoSlide() {
    const prox = (slideAtual + 1) % heroSlides.length;
    irParaSlide(prox);
  }

  function iniciarTimer() {
    clearInterval(sliderTimer);
    sliderTimer = setInterval(proximoSlide, SLIDE_DURACAO);
    iniciarProgressBar();
  }

  function pararTimer() {
    clearInterval(sliderTimer);
    if (heroProgress) {
      heroProgress.style.transition = 'none';
    }
  }

  if (heroSlides.length > 1) {
    heroDots.forEach(dot => {
      // click para desktop
      dot.addEventListener('click', () => {
        irParaSlide(parseInt(dot.dataset.para, 10));
        iniciarTimer();
      });
      // touchstart para resposta imediata no mobile (sem delay de 300ms)
      dot.addEventListener('touchstart', (e) => {
        e.stopPropagation(); // impede que o swipe do heroEl interprete esse toque
        e.preventDefault();  // cancela ghost-click e atraso de 300ms do iOS
        irParaSlide(parseInt(dot.dataset.para, 10));
        iniciarTimer();
      }, { passive: false }); // não-passivo para permitir preventDefault
    });

    const heroEl = document.getElementById('hero-slider');
    if (heroEl) {
      heroEl.addEventListener('mouseenter', pararTimer);
      heroEl.addEventListener('mouseleave', iniciarTimer);

      // Swipe horizontal (mobile) — ignora se o toque foi num dot
      let touchStartX = 0, touchStartY = 0, touchAtivo = false;
      heroEl.addEventListener('touchstart', (e) => {
        if (e.target.classList.contains('hero-dot')) return; // dot cuida de si
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchAtivo = true;
      }, { passive: true });
      heroEl.addEventListener('touchend', (e) => {
        if (!touchAtivo) return;
        touchAtivo = false;
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
        const total = heroSlides.length;
        const prox = dx < 0 ? (slideAtual + 1) % total : (slideAtual - 1 + total) % total;
        irParaSlide(prox);
        iniciarTimer();
      }, { passive: true });
    }

    const heroPrev = document.getElementById('hero-arrow-prev');
    const heroNext = document.getElementById('hero-arrow-next');
    if (heroPrev) {
      heroPrev.addEventListener('click', () => {
        const prev = (slideAtual - 1 + heroSlides.length) % heroSlides.length;
        irParaSlide(prev);
        iniciarTimer();
      });
    }
    if (heroNext) {
      heroNext.addEventListener('click', () => {
        irParaSlide((slideAtual + 1) % heroSlides.length);
        iniciarTimer();
      });
    }

    iniciarTimer();
  }

  atualizarControleAudioHero();

  // Click em slides com url_botao
  heroSlides.forEach(slide => {
    const href = slide.dataset.href;
    if (href) {
      slide.addEventListener('click', () => { window.location.href = href; });
    }
  });

  // Se o primeiro slide tem vídeo sem loop, avançar ao terminar
  const primeiroVideoHero = heroSlides.length > 0
    ? heroSlides[0].querySelector('video')
    : null;
  if (primeiroVideoHero && heroSlides.length > 1) {
    let videoJaAvancou = false;
    primeiroVideoHero.addEventListener('ended', () => {
      if (videoJaAvancou) return;
      videoJaAvancou = true;
      clearInterval(sliderTimer);
      proximoSlide();
      iniciarTimer();
    });
  }

  // ─── Hero: mute/unmute do vídeo ativo ─────────────────────────────────────
  if (muteBtn) {
    muteBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      const heroVideo = videoAtivoHero();
      if (!heroVideo) return;
      heroVideo.muted = !heroVideo.muted;
      atualizarControleAudioHero();
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

  async function abrirCarrinho() {
    drawerOverlay?.classList.add('aberto');
    drawerCarrinho?.classList.add('aberto');
    document.body.style.overflow = 'hidden';
    // Sincroniza badge e itens com o estado real da sessão (corrige páginas em bfcache)
    try {
      const res  = await fetch('/carrinho/status/', { cache: 'no-store' });
      const dados = await res.json();
      window.atualizarDrawerConteudo(dados);
    } catch (_) {}
  }

  function fecharCarrinho() {
    drawerOverlay?.classList.remove('aberto');
    drawerCarrinho?.classList.remove('aberto');
    document.body.style.overflow = '';
  }

  window.abrirCarrinho = abrirCarrinho;
  window.fecharCarrinho = fecharCarrinho;

  btnAbrirCarrinho.forEach(btn => btn.addEventListener('click', abrirCarrinho));
  btnFecharCarrinho?.addEventListener('click', fecharCarrinho);

  // Sincroniza badge ao restaurar página do bfcache (navegar de volta após checkout)
  window.addEventListener('pageshow', async (e) => {
    if (!e.persisted) return;
    try {
      const res  = await fetch('/carrinho/status/', { cache: 'no-store' });
      const dados = await res.json();
      window.atualizarDrawerConteudo(dados);
    } catch (_) {}
  });
  drawerOverlay?.addEventListener('click', fecharCarrinho);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') fecharCarrinho();
  });

  document.addEventListener('click', (e) => {
    const dismissBtn = e.target.closest('[data-dismiss-parent]');
    if (dismissBtn?.parentElement) {
      dismissBtn.parentElement.remove();
      return;
    }

    if (e.target.closest('[data-fechar-carrinho]')) {
      fecharCarrinho();
      return;
    }

    const copyBtn = e.target.closest('[data-copy-target]');
    if (copyBtn) {
      const targetId = copyBtn.dataset.copyTarget || '';
      const input = document.getElementById(targetId);
      if (!input) return;

      const successHtml = copyBtn.dataset.copySuccessHtml || '<i class="fas fa-check"></i> Copiado!';
      const defaultHtml = copyBtn.dataset.copyDefaultHtml || copyBtn.innerHTML;

      navigator.clipboard?.writeText(input.value).then(() => {
        copyBtn.innerHTML = successHtml;
        setTimeout(() => {
          copyBtn.innerHTML = defaultHtml;
        }, 2500);
      }).catch(() => {
        input.select();
        document.execCommand('copy');
      });
    }
  });

  const mensagensSistema = document.getElementById('mensagens-sistema');
  if (mensagensSistema) {
    setTimeout(() => {
      mensagensSistema.remove();
    }, 5000);
  }

  // ─── Adicionar ao carrinho (AJAX) ──────────────────────────────────────────
  // Delegação de eventos: captura cliques em [data-produto-id] exceto no detalhe do produto
  // (o detalhe tem seu próprio handler no bloco js_extra para incluir variação + quantidade)
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-produto-id]');
    if (!btn) return;
    // O detalhe usa #btn-adicionar-carrinho e #btn-comprar-agora — evita duplo disparo
    if (btn.id === 'btn-adicionar-carrinho') return;
    if (btn.id === 'btn-comprar-agora') return;

    const produtoId   = btn.dataset.produtoId;
    const variacaoId  = btn.dataset.variacaoId || '';
    const produtoUrl  = btn.dataset.produtoUrl || '';
    const csrfToken   = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    const metaEventId = (window.crypto && window.crypto.randomUUID)
      ? `addtocart_${window.crypto.randomUUID().replace(/-/g, '')}`
      : `addtocart_${Date.now()}_${Math.random().toString(16).slice(2)}`;

    // Sem variação pré-selecionada → redireciona para o produto para escolher cor/tamanho
    if (!variacaoId && produtoUrl) {
      window.location.href = produtoUrl;
      return;
    }

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
        body: JSON.stringify({ variacao_id: variacaoId, quantidade: 1, meta_event_id: metaEventId }),
      });

      const dados = await res.json();

      if (dados.status === 'ok') {
        atualizarDrawerConteudo(dados);
        abrirCarrinho();
        const precoAtc = parseFloat(btn.dataset.produtoPreco || dados.total_valor || 0);
        if (window.fbq) {
          fbq('track', 'AddToCart', {
            content_ids: [produtoId],
            content_type: 'product',
            contents: [{ id: produtoId, quantity: 1, item_price: precoAtc }],
            value: precoAtc,
            currency: 'BRL',
          }, { eventID: metaEventId });
        }
        window.dellaTrackGA('add_to_cart', {
          currency: 'BRL',
          value: precoAtc,
          items: [{
            item_id: produtoId,
            item_name: btn.dataset.produtoNome || '',
            item_category: btn.dataset.produtoCategoria || '',
            price: precoAtc,
            quantity: 1,
          }],
        });
        btn.innerHTML = '<i class="fas fa-check"></i>';
        setTimeout(() => { btn.innerHTML = textoOriginal; btn.disabled = false; }, 1500);
      } else {
        btn.innerHTML = textoOriginal;
        btn.disabled = false;
        if (dados.mensagem) alert(dados.mensagem);
      }
    } catch (err) {
      btn.innerHTML = textoOriginal;
      btn.disabled = false;
    }
  });

  // ─── Helpers ───────────────────────────────────────────────────────────────
  function fmtBRL(value) {
    const partes = value.toFixed(2).split('.');
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return partes.join(',');
  }

  function atualizarFreteProgressoDrawer(total, totalItens) {
    const wrap = document.getElementById('drawer-frete-progresso');
    if (!wrap) return;
    const meta = parseFloat(wrap.dataset.meta || '0');
    if (!meta) { wrap.hidden = true; return; }
    if (totalItens === 0) { wrap.hidden = true; return; }
    wrap.hidden = false;

    const fill = document.getElementById('drawer-frete-progresso-fill');
    const msg  = document.getElementById('drawer-frete-progresso-msg');
    const faltante = Math.max(0, meta - total);
    const percentual = Math.min(100, (total / meta) * 100);
    if (fill) fill.style.width = percentual + '%';
    if (!msg) return;
    if (faltante <= 0) {
      wrap.classList.add('conquistado-state');
      msg.classList.add('conquistado');
      msg.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Você ganhou frete grátis';
    } else {
      wrap.classList.remove('conquistado-state');
      msg.classList.remove('conquistado');
      msg.innerHTML = 'Faltam <strong>R$ ' + fmtBRL(faltante) + '</strong> para frete grátis';
    }
  }

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
      totalValor.textContent = 'R$ ' + fmtBRL(parseFloat(dados.total_valor));
    }

    if (dados.total_valor !== undefined) {
      atualizarFreteProgressoDrawer(parseFloat(dados.total_valor), dados.total_itens || 0);
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
              <p class="drawer-item-preco">R$ ${fmtBRL(parseFloat(item.subtotal))}</p>
              <div class="drawer-item-qty">
                <button class="drawer-qty-btn" data-drawer-action="alterar" data-chave="${item.chave}" data-quantidade="${item.quantidade - 1}">−</button>
                <span>${item.quantidade}</span>
                <button class="drawer-qty-btn" data-drawer-action="alterar" data-chave="${item.chave}" data-quantidade="${item.quantidade + 1}">+</button>
              </div>
            </div>
            <button class="drawer-item-remover" data-drawer-action="remover" data-chave="${item.chave}" aria-label="Remover item">
              <i class="fas fa-times"></i>
            </button>
          </div>
        `).join('');
      }
    }
  };

  // Remover item pelo drawer
  window.drawerRemover = async function(chave, itemData) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    try {
      const res   = await fetch(`/carrinho/remover/${chave}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const dados = await res.json();
      if (dados.status === 'ok') {
        window.atualizarDrawerConteudo(dados);
        if (itemData) {
          window.dellaTrackGA('remove_from_cart', {
            currency: 'BRL',
            value: parseFloat(itemData.preco || 0) * parseInt(itemData.quantidade || 1, 10),
            items: [{
              item_id: String(itemData.id || ''),
              item_name: itemData.nome || '',
              price: parseFloat(itemData.preco || 0),
              quantity: parseInt(itemData.quantidade || 1, 10),
            }],
          });
        }
      }
    } catch(e) {}
  };

  // Alterar quantidade pelo drawer
  window.drawerAlterarQty = async function(chave, quantidade) {
    if (quantidade < 1) { window.drawerRemover(chave); return; }
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
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

  document.addEventListener('click', (e) => {
    const drawerBtn = e.target.closest('[data-drawer-action]');
    if (!drawerBtn) return;

    const chave = drawerBtn.dataset.chave || '';
    if (!chave) return;

    if (drawerBtn.dataset.drawerAction === 'remover') {
      const itemEl = drawerBtn.closest('.drawer-item');
      const itemData = itemEl ? {
        id: itemEl.dataset.produtoId || '',
        nome: itemEl.querySelector('.drawer-item-nome')?.textContent?.trim() || '',
        preco: parseFloat((itemEl.querySelector('.drawer-item-preco')?.textContent || '').replace(/[^0-9,]/g, '').replace(',', '.')) || 0,
        quantidade: parseInt(itemEl.querySelector('.drawer-item-qty span')?.textContent || '1', 10),
      } : null;
      window.drawerRemover(chave, itemData);
      return;
    }

    if (drawerBtn.dataset.drawerAction === 'alterar') {
      const quantidade = parseInt(drawerBtn.dataset.quantidade || '', 10);
      if (!Number.isNaN(quantidade)) {
        window.drawerAlterarQty(chave, quantidade);
      }
    }
  });

  // ─── Wishlist toggle (AJAX) ────────────────────────────────────────────────
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-wishlist-id]');
    if (!btn) return;

    const produtoId = btn.dataset.wishlistId;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

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
        // Pixel AddToWishlist — mesmo event_id do CAPI (deduplicação)
        if (dados.na_wishlist && dados.meta_event && window.fbq) {
          fbq('track', 'AddToWishlist', {
            content_ids: [dados.meta_event.content_id],
            content_type: 'product',
            content_name: dados.meta_event.content_name,
            content_category: dados.meta_event.content_category,
            value: dados.meta_event.value,
            currency: 'BRL',
          }, { eventID: dados.meta_event.id });
        }
      }
    } catch (err) { /* silencioso */ }
  });

  // ─── Contact — clique no WhatsApp (Pixel + GA4, condicionado a consent) ──────
  document.addEventListener('click', (e) => {
    const wa = e.target.closest('.whatsapp-opcao, a[href*="wa.me"]');
    if (!wa) return;
    if (window.fbq) {
      window.fbq('track', 'Contact', { content_category: 'whatsapp' });
    }
    window.dellaTrackGA('whatsapp_click', { label: wa.getAttribute('aria-label') || 'whatsapp' });
  });

  // ─── Newsletter (AJAX) ────────────────────────────────────────────────────
  function obterMensagemNewsletterHTML(dados) {
    const tituloCss = 'color:var(--dourado);font-family:var(--fonte-titulo);font-style:italic;font-size:1.1rem;text-align:center;margin:0;';
    const titulo = dados.novo
      ? 'Obrigada por se inscrever ✦'
      : 'Você já está cadastrada no nosso clube. Obrigada ✦';
    let html = '<p style="' + tituloCss + '">' + titulo + '</p>';
    if (dados.cupom) {
      const valor = dados.cupom.tipo === 'percentual'
        ? (parseFloat(dados.cupom.valor)).toString().replace('.', ',') + '% de desconto'
        : 'R$ ' + dados.cupom.valor + ' de desconto';
      html += '<div style="margin-top:1rem;text-align:center;font-family:var(--fonte-corpo);">' +
                '<p style="font-size:.78rem;color:var(--cinza-texto);margin:0 0 .35rem;letter-spacing:.1em;text-transform:uppercase;">Seu cupom de ' + valor + '</p>' +
                '<p style="font-size:1.25rem;font-weight:600;letter-spacing:.2em;color:var(--preto);margin:0;border:1px dashed var(--cinza-medio);padding:.65rem 1rem;display:inline-block;">' + dados.cupom.codigo + '</p>' +
                '<p style="font-size:.72rem;color:var(--cinza-texto);margin:.75rem 0 0;line-height:1.5;">Válido por ' + dados.cupom.dias_validade + ' dias. Também enviamos para o seu e-mail.</p>' +
              '</div>';
    }
    return html;
  }

  const formNewsletter = document.getElementById('form-newsletter');

  if (formNewsletter) {
    formNewsletter.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = formNewsletter.querySelector('input[type="email"]').value.trim();
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      const btn = formNewsletter.querySelector('button[type="submit"]');
      const aviso = document.getElementById('newsletter-aviso');
      const optin = document.getElementById('newsletter-optin');
      const optinErro = document.getElementById('newsletter-optin-erro');

      if (!email) return;

      if (optin && !optin.checked) {
        if (optinErro) optinErro.style.display = 'block';
        optin.focus();
        return;
      }
      if (optinErro) optinErro.style.display = 'none';

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
          // Pixel Lead — mesmo event_id do CAPI (deduplicação)
          if (dados.meta_event_id && window.fbq) {
            fbq('track', 'Lead', {
              content_name: 'Newsletter',
              content_category: 'newsletter',
            }, { eventID: dados.meta_event_id });
          }
          formNewsletter.style.display = 'none';
          const optinLabel = optin ? optin.closest('.newsletter-optin') : null;
          if (optinLabel) optinLabel.style.display = 'none';
          if (optinErro) optinErro.style.display = 'none';
          if (aviso) {
            aviso.style.cssText = 'margin-top:1rem;';
            aviso.innerHTML = obterMensagemNewsletterHTML(dados);
          }
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

    const optinChk = document.getElementById('newsletter-optin');
    const optinErroEl = document.getElementById('newsletter-optin-erro');
    if (optinChk && optinErroEl) {
      optinChk.addEventListener('change', function () {
        if (optinChk.checked) optinErroEl.style.display = 'none';
      });
    }
  }

  // ─── Busca inline no navbar ───────────────────────────────────────────────
  const btnBusca          = document.getElementById('btn-busca');
  const buscaDesktop      = document.getElementById('navbar-busca-desktop');
  const buscaMobile       = document.getElementById('navbar-busca-mobile');
  const buscaInputDesktop = document.getElementById('navbar-busca-input');
  const buscaInputMobile  = document.getElementById('navbar-busca-input-mobile');

  if (btnBusca) {
    function abrirBusca() {
      const isMobile = window.innerWidth <= 768;
      if (isMobile) {
        buscaMobile?.classList.add('ativo');
        buscaMobile?.removeAttribute('aria-hidden');
        buscaInputMobile?.focus();
      } else {
        buscaDesktop?.classList.add('ativo');
        buscaDesktop?.removeAttribute('aria-hidden');
        setTimeout(() => buscaInputDesktop?.focus(), 50);
      }
      btnBusca.setAttribute('aria-expanded', 'true');
      const icon = document.getElementById('btn-busca-icon');
      if (icon) { icon.classList.replace('fa-magnifying-glass', 'fa-xmark'); }
    }

    function fecharBusca() {
      buscaDesktop?.classList.remove('ativo');
      buscaMobile?.classList.remove('ativo');
      buscaDesktop?.setAttribute('aria-hidden', 'true');
      buscaMobile?.setAttribute('aria-hidden', 'true');
      btnBusca.setAttribute('aria-expanded', 'false');
      const icon = document.getElementById('btn-busca-icon');
      if (icon) { icon.classList.replace('fa-xmark', 'fa-magnifying-glass'); }
    }

    btnBusca.addEventListener('click', () => {
      if (btnBusca.getAttribute('aria-expanded') === 'true') {
        fecharBusca();
      } else {
        abrirBusca();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && btnBusca.getAttribute('aria-expanded') === 'true') {
        fecharBusca();
      }
    });
  }

  // ─── Autocomplete de busca ───────────────────────────────────────────────
  (function () {
    const pares = [
      { input: buscaInputDesktop, lista: document.getElementById('busca-sugestoes-desktop') },
      { input: buscaInputMobile,  lista: document.getElementById('busca-sugestoes-mobile') },
    ];

    let debounceTimer = null;
    let foco = -1;

    function fecharLista(lista) {
      if (!lista) return;
      lista.hidden = true;
      lista.innerHTML = '';
      foco = -1;
    }

    function fecharTodasListas() {
      pares.forEach(({ lista }) => fecharLista(lista));
    }

    function moverFoco(lista, delta) {
      const itens = lista.querySelectorAll('.busca-sugestao');
      if (!itens.length) return;
      foco = ((foco + delta + itens.length) % itens.length);
      itens.forEach((el, i) => el.classList.toggle('foco', i === foco));
      itens[foco]?.scrollIntoView({ block: 'nearest' });
    }

    function posicionarLista(input, lista) {
      const rect = input.getBoundingClientRect();
      lista.style.top    = (rect.bottom + 4) + 'px';
      lista.style.left   = rect.left + 'px';
      lista.style.width  = Math.max(rect.width, 240) + 'px';
      lista.style.right  = 'auto';
    }

    function renderizarSugestoes(input, lista, sugestoes) {
      lista.innerHTML = '';
      if (!sugestoes.length) { lista.hidden = true; return; }
      sugestoes.forEach((s) => {
        const li = document.createElement('li');
        li.className = 'busca-sugestao';
        li.setAttribute('role', 'option');
        const iconeClasse = s.tipo === 'categoria' ? 'fas fa-folder-open' : 'fas fa-bag-shopping';
        li.innerHTML = `<i class="${iconeClasse} busca-sugestao-icone"></i><span>${s.label}</span>`;
        li.addEventListener('mousedown', (e) => {
          e.preventDefault();
          window.location.href = s.url;
        });
        lista.appendChild(li);
      });
      posicionarLista(input, lista);
      lista.hidden = false;
      foco = -1;
    }

    function buscar(input, lista, q) {
      if (q.length < 2) { fecharLista(lista); return; }
      fetch(`/busca/autocomplete/?q=${encodeURIComponent(q)}`)
        .then((r) => r.ok ? r.json() : { sugestoes: [] })
        .then((data) => { if (input.value.trim() === q) renderizarSugestoes(input, lista, data.sugestoes || []); })
        .catch(() => {});
    }

    pares.forEach(({ input, lista }) => {
      if (!input || !lista) return;

      input.addEventListener('input', () => {
        const q = input.value.trim();
        foco = -1;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => buscar(input, lista, q), 220);
      });

      input.addEventListener('keydown', (e) => {
        if (lista.hidden) return;
        if (e.key === 'ArrowDown')  { e.preventDefault(); moverFoco(lista, 1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); moverFoco(lista, -1); }
        else if (e.key === 'Enter' && foco >= 0) {
          e.preventDefault();
          lista.querySelectorAll('.busca-sugestao')[foco]?.dispatchEvent(new MouseEvent('mousedown'));
        }
        else if (e.key === 'Escape') { fecharLista(lista); }
      });

      input.addEventListener('blur', () => setTimeout(() => fecharLista(lista), 150));

      input.setAttribute('aria-expanded', 'false');
      new MutationObserver(() => {
        input.setAttribute('aria-expanded', lista.hidden ? 'false' : 'true');
      }).observe(lista, { attributes: true, attributeFilter: ['hidden'] });
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.busca-form-wrapper')) fecharTodasListas();
    });

    window.addEventListener('resize', () => {
      pares.forEach(({ input, lista }) => {
        if (!lista.hidden) posicionarLista(input, lista);
      });
    });
  }());

  // ─── Menu mobile ──────────────────────────────────────────────────────────
  const btnMenuMobile     = document.getElementById('btn-menu-mobile');
  const btnFecharMenuMob  = document.getElementById('btn-menu-mobile-fechar');
  const menuMobilePanel   = document.getElementById('menu-mobile');

  function abrirMenuMobile() {
    menuMobilePanel?.classList.add('aberto');
    btnMenuMobile?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }
  function fecharMenuMobile() {
    menuMobilePanel?.classList.remove('aberto');
    btnMenuMobile?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  btnMenuMobile?.addEventListener('click', () => {
    if (menuMobilePanel?.classList.contains('aberto')) {
      fecharMenuMobile();
    } else {
      abrirMenuMobile();
    }
  });
  btnFecharMenuMob?.addEventListener('click', fecharMenuMobile);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menuMobilePanel?.classList.contains('aberto')) fecharMenuMobile();
  });

  // ─── Look da semana: tap no "+" abre/fecha o card (apenas touch) ──────────
  // Desktop segue com :hover. Em celular, o primeiro tap abre o card; tap no
  // "+" de novo fecha; tap fora fecha. Tap no próprio card navega ao produto.
  if (window.matchMedia('(hover: none)').matches) {
    const pontos = document.querySelectorAll('.look-ponto');
    if (pontos.length) {
      pontos.forEach(p => {
        p.addEventListener('click', (e) => {
          if (e.target.closest('.look-ponto-tooltip')) return;
          e.preventDefault();
          const jaAberto = p.classList.contains('aberto');
          pontos.forEach(o => o.classList.remove('aberto'));
          if (!jaAberto) p.classList.add('aberto');
        });
      });
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.look-ponto')) {
          pontos.forEach(p => p.classList.remove('aberto'));
        }
      });
    }
  }

  // ─── Sidebar: árvore de categorias ────────────────────────────────────────
  document.querySelectorAll('.sidebar-cat-mae').forEach(btn => {
    btn.addEventListener('click', () => {
      const subcats = btn.nextElementSibling;
      if (!subcats) return;
      const aberta = subcats.classList.toggle('aberta');
      btn.classList.toggle('expandida', aberta);
    });
  });

  // ─── Galeria do produto: setas + swipe ─────────────────────────────────────
  const galeriaPrincipal = document.querySelector('.galeria-principal');
  const galeriaFoto      = document.getElementById('foto-principal');
  const galeriaThumbs    = document.querySelectorAll('.galeria-thumb');
  const galeriaDinamicaPorCor = document.getElementById('produto-detalhe-config');

  if (!galeriaDinamicaPorCor && galeriaThumbs.length > 1 && galeriaPrincipal) {
    let indexAtual = 0;

    function irParaFoto(idx) {
      const total = galeriaThumbs.length;
      indexAtual = (idx + total) % total;
      const thumb = galeriaThumbs[indexAtual];
      if (galeriaFoto) {
        galeriaFoto.src = thumb.dataset.src;
        galeriaFoto.alt = thumb.dataset.alt;
      }
      galeriaThumbs.forEach(t => t.classList.remove('ativa'));
      thumb.classList.add('ativa');
    }

    const btnPrev = document.querySelector('.galeria-nav-prev');
    const btnNext = document.querySelector('.galeria-nav-next');

    btnPrev?.addEventListener('click', () => irParaFoto(indexAtual - 1));
    btnNext?.addEventListener('click', () => irParaFoto(indexAtual + 1));

    // Sincroniza indexAtual quando usuário clica em uma thumb
    galeriaThumbs.forEach((thumb, idx) => {
      thumb.addEventListener('click', () => { indexAtual = idx; });
    });

    // Swipe horizontal na foto principal (mobile)
    let gStartX = 0, gStartY = 0, gAtivo = false;
    galeriaPrincipal.addEventListener('touchstart', (e) => {
      gStartX = e.touches[0].clientX;
      gStartY = e.touches[0].clientY;
      gAtivo = true;
    }, { passive: true });
    galeriaPrincipal.addEventListener('touchend', (e) => {
      if (!gAtivo) return;
      gAtivo = false;
      const dx = e.changedTouches[0].clientX - gStartX;
      const dy = e.changedTouches[0].clientY - gStartY;
      if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
      irParaFoto(dx < 0 ? indexAtual + 1 : indexAtual - 1);
    }, { passive: true });
  }

  // ─── Modal: guia de tamanhos ──────────────────────────────────────────────
  const linkGuia   = document.getElementById('link-guia-tamanhos');
  const modalGuia  = document.getElementById('modal-guia-tamanhos');
  const btnFecharModal = document.getElementById('btn-fechar-modal-guia');

  function abrirModal() {
    modalGuia?.classList.add('aberto');
    document.body.style.overflow = 'hidden';
  }

  function fecharModal() {
    modalGuia?.classList.remove('aberto');
    document.body.style.overflow = '';
  }

  linkGuia?.addEventListener('click', (e) => { e.preventDefault(); abrirModal(); });
  btnFecharModal?.addEventListener('click', fecharModal);
  modalGuia?.addEventListener('click', (e) => {
    if (e.target === modalGuia) fecharModal();
  });

  // ─── Carrossel de Destaques da Semana ─────────────────────────────────────
  const destaquesCarousel  = document.getElementById('destaques-carousel');
  const destaquesViewport  = destaquesCarousel?.querySelector('.destaques-viewport');
  const destaquesTrack     = document.getElementById('destaques-track');
  const destaquesPrev      = document.getElementById('destaques-prev');
  const destaquesNext      = document.getElementById('destaques-next');

  if (destaquesTrack && destaquesViewport) {
    const cards = [...destaquesTrack.querySelectorAll('.produto-card')];
    let destaqIdx = 0;

    function destaqPerPage() {
      if (window.innerWidth < 641)  return 2;
      if (window.innerWidth < 1025) return 3;
      return 4;
    }

    function destaqMaxIdx() {
      // Garante >= 0: se cards.length <= pp não há como deslizar
      return Math.max(0, cards.length - destaqPerPage());
    }

    function destaqAtualizar() {
      const pp    = destaqPerPage();
      const max   = destaqMaxIdx();
      // Clamp defensivo: garante que idx nunca sai do intervalo válido
      destaqIdx   = Math.min(Math.max(0, destaqIdx), max);

      const gap   = 16; // 1rem em px
      const vw    = destaquesViewport.offsetWidth;
      const cardW = (vw - gap * (pp - 1)) / pp;
      const offset = destaqIdx * (cardW + gap);
      destaquesTrack.style.transform = `translateX(-${offset}px)`;

      // Desabilita setas quando não há itens suficientes para deslizar
      const podeNavegar = cards.length > pp;
      if (destaquesPrev) destaquesPrev.disabled = !podeNavegar || destaqIdx <= 0;
      if (destaquesNext) destaquesNext.disabled = !podeNavegar || destaqIdx >= max;
    }

    destaquesPrev?.addEventListener('click', () => {
      destaqIdx = Math.max(0, destaqIdx - 1);
      destaqAtualizar();
    });

    destaquesNext?.addEventListener('click', () => {
      destaqIdx = Math.min(destaqMaxIdx(), destaqIdx + 1);
      destaqAtualizar();
    });

    // Swipe mobile
    let dStartX = 0;
    destaquesViewport.addEventListener('touchstart', e => {
      dStartX = e.touches[0].clientX;
    }, { passive: true });
    destaquesViewport.addEventListener('touchend', e => {
      const dx = e.changedTouches[0].clientX - dStartX;
      if (Math.abs(dx) < 40) return;
      if (dx < 0) destaqIdx = Math.min(destaqMaxIdx(), destaqIdx + 1);
      else        destaqIdx = Math.max(0, destaqIdx - 1);
      destaqAtualizar();
    }, { passive: true });

    window.addEventListener('resize', destaqAtualizar);
    destaqAtualizar();
  }

  // ─── Newsletter Popup ─────────────────────────────────────────────────────
  const popupNewsletter = document.getElementById('popup-newsletter');
  const popupFechar     = document.getElementById('popup-newsletter-fechar');
  const formPopup       = document.getElementById('form-popup-newsletter');

  if (popupNewsletter) {
    const POPUP_KEY         = 'della_newsletter_popup';
    const FIRST_PAGE_KEY    = 'della_primeira_pagina';
    const LOGADO_VISTO_KEY  = 'della_logado_popup_visto';

    // Usuario logado nao inscrito: data-force-show="1" vem do Django (server-side)
    const forceShow = popupNewsletter.dataset.forceShow === '1';

    function mostrarPopupApos5s() {
      setTimeout(function() {
        var cookieBanner = document.getElementById('della-cookie-banner');
        if (cookieBanner && cookieBanner.style.display !== 'none') return;
        popupNewsletter.style.display = 'flex';
      }, 5000);
    }

    if (forceShow) {
      // Logado: usa sessionStorage proprio — mostra uma vez por sessao de navegador
      // sessionStorage e limpo ao fechar a aba/janela, entao aparece de novo na proxima visita
      if (!sessionStorage.getItem(LOGADO_VISTO_KEY)) {
        sessionStorage.setItem(LOGADO_VISTO_KEY, '1');
        mostrarPopupApos5s();
      }
    } else {
      // Anonimo: mostra apenas na primeira pagina da primeira visita (localStorage permanente)
      var ehPrimeiraPagina = !sessionStorage.getItem(FIRST_PAGE_KEY);
      sessionStorage.setItem(FIRST_PAGE_KEY, '1');
      if (!localStorage.getItem(POPUP_KEY) && ehPrimeiraPagina) {
        localStorage.setItem(POPUP_KEY, '1');
        mostrarPopupApos5s();
      }
    }

    function fecharPopup() { popupNewsletter.style.display = 'none'; }

    popupFechar?.addEventListener('click', fecharPopup);
    popupNewsletter.addEventListener('click', e => {
      if (e.target === popupNewsletter) fecharPopup();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') fecharPopup();
    });

    if (formPopup) {
      formPopup.addEventListener('submit', async e => {
        e.preventDefault();
        const email = formPopup.querySelector('input[type="email"]').value.trim();
        const optinChk = document.getElementById('popup-newsletter-optin');
        const optinErro = document.getElementById('popup-optin-erro');
        if (optinChk && !optinChk.checked) {
          if (optinErro) optinErro.style.display = 'block';
          optinChk.focus();
          return;
        }
        if (optinErro) optinErro.style.display = 'none';
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
        const btn = formPopup.querySelector('button[type="submit"]');
        if (!email) return;
        btn.disabled = true;
        btn.textContent = 'Aguarde...';
        try {
          const res   = await fetch('/newsletter/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ email }),
          });
          const dados = await res.json();
          if (dados.status === 'ok') {
            formPopup.innerHTML = obterMensagemNewsletterHTML(dados);
            setTimeout(fecharPopup, dados.cupom ? 12000 : 3000);
          } else {
            btn.disabled = false;
            btn.innerHTML = 'Assinar Newsletter <i class="fas fa-chevron-right"></i>';
          }
        } catch {
          btn.disabled = false;
          btn.innerHTML = 'Assinar Newsletter <i class="fas fa-chevron-right"></i>';
        }
      });

      const popupOptinChk = document.getElementById('popup-newsletter-optin');
      const popupOptinErroEl = document.getElementById('popup-optin-erro');
      if (popupOptinChk && popupOptinErroEl) {
        popupOptinChk.addEventListener('change', () => {
          if (popupOptinChk.checked) popupOptinErroEl.style.display = 'none';
        });
      }
    }
  }

  document.querySelectorAll('[data-auto-submit-form]').forEach((field) => {
    field.addEventListener('change', () => {
      const formId = field.dataset.autoSubmitForm;
      if (!formId) return;
      document.getElementById(formId)?.submit();
    });
  });

  // ─── Meta Pixel — carregamento condicional respeitando consent ────────────
  function carregarMetaPixel() {
    if (window.fbq) return; // já carregado
    const pixelId = document.body.dataset.metaPixelId;
    if (!pixelId) return;

    // Advanced Matching: email/telefone hash so com consent; fbc/fbp sempre
    const userData = {};
    const temConsentMarketing = !!(window.dellaConsent && window.dellaConsent.marketing);
    if (temConsentMarketing) {
      try {
        const amEl = document.getElementById('meta-am-data');
        if (amEl) Object.assign(userData, JSON.parse(amEl.textContent || '{}'));
      } catch (_) {}
    }
    const mFbc = document.cookie.match(/(?:^|;\s*)_fbc=([^;]+)/);
    const mFbp = document.cookie.match(/(?:^|;\s*)_fbp=([^;]+)/);
    if (mFbc) userData.fbc = decodeURIComponent(mFbc[1]);
    if (mFbp) userData.fbp = decodeURIComponent(mFbp[1]);

    // Snippet oficial da Meta
    !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}(window, document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');

    fbq('init', pixelId, userData);
    fbq('track', 'PageView');

    // Dispara eventos custom registrados pelo template (ViewContent, Purchase, etc.)
    dispararMetaEventosCustom();
  }

  function dispararMetaEventosCustom() {
    if (!window.fbq) return;
    document.querySelectorAll('script[type="application/json"][data-meta-event]').forEach(function (script) {
      try {
        const evento = script.dataset.metaEvent;
        const dados = JSON.parse(script.textContent || '{}');
        const eventId = dados._event_id || '';
        const onceKey = dados._once_key || '';
        delete dados._event_id;
        delete dados._once_key;

        if (onceKey) {
          try {
            if (sessionStorage.getItem('meta-event:' + onceKey)) return;
          } catch (e) { /* silencioso */ }
        }

        if (eventId) {
          fbq('track', evento, dados, { eventID: eventId });
        } else {
          fbq('track', evento, dados);
        }

        if (onceKey) {
          try {
            sessionStorage.setItem('meta-event:' + onceKey, '1');
          } catch (e) { /* silencioso */ }
        }
      } catch (e) { /* silencioso */ }
    });
  }

  // ─── GA4 Ecommerce — eventos de página declarados no template ──────────────
  // Espelho de dispararMetaEventosCustom: só roda depois de carregarGA (consent Análise).
  function dispararGAEventosCustom() {
    if (!window.gtag) return;
    document.querySelectorAll('script[type="application/json"][data-ga-event]').forEach(function (script) {
      try {
        const evento = script.dataset.gaEvent;
        const dados = JSON.parse(script.textContent || '{}');
        const onceKey = dados._once_key || '';
        delete dados._once_key;

        if (onceKey) {
          try {
            if (sessionStorage.getItem('ga-event:' + onceKey)) return;
          } catch (e) { /* silencioso */ }
        }

        window.gtag('event', evento, dados);

        if (onceKey) {
          try {
            sessionStorage.setItem('ga-event:' + onceKey, '1');
          } catch (e) { /* silencioso */ }
        }
      } catch (e) { /* silencioso */ }
    });
  }

  // ─── Helpers públicos de tracking (silenciosos sem consent) ────────────────
  window.dellaTrackGA = function (event, params) {
    try { if (window.gtag) window.gtag('event', event, params || {}); } catch (e) { /* silencioso */ }
  };
  window.dellaTrackMeta = function (event, params) {
    try { if (window.fbq) window.fbq('track', event, params || {}); } catch (e) { /* silencioso */ }
  };

  // ─── Cookie Consent (LGPD) ─────────────────────────────────────────────────
  (function () {
    const COOKIE_NAME = 'della_consent';
    const COOKIE_VERSION = 1;
    const VALID_DAYS = 180;

    function lerConsent() {
      const m = document.cookie.match(new RegExp('(?:^|;\\s*)' + COOKIE_NAME + '=([^;]+)'));
      if (!m) return null;
      try {
        const data = JSON.parse(decodeURIComponent(m[1]));
        if (data.v !== COOKIE_VERSION) return null;
        return data;
      } catch (e) { return null; }
    }

    function salvarConsent(prefs) {
      const data = {
        v: COOKIE_VERSION,
        necessary: true,
        analytics: !!prefs.analytics,
        marketing: !!prefs.marketing,
        ts: Math.floor(Date.now() / 1000),
      };
      const expira = new Date(Date.now() + VALID_DAYS * 86400 * 1000);
      const secure = location.protocol === 'https:' ? '; Secure' : '';
      document.cookie = COOKIE_NAME + '=' + encodeURIComponent(JSON.stringify(data))
        + '; path=/; expires=' + expira.toUTCString()
        + '; SameSite=Lax' + secure;
      window.dellaConsent = data;
      document.dispatchEvent(new CustomEvent('della:consent', { detail: data }));
    }

    const banner = document.getElementById('della-cookie-banner');
    const modal = document.getElementById('della-cookie-modal');
    const tgAnalytics = document.getElementById('della-cookie-tg-analytics');
    const tgMarketing = document.getElementById('della-cookie-tg-marketing');

    function abrirBanner() { if (banner) banner.style.display = 'block'; }
    function fecharBanner() { if (banner) banner.style.display = 'none'; }
    function abrirModal(prefs) {
      if (!modal) return;
      if (tgAnalytics) tgAnalytics.checked = !!(prefs && prefs.analytics);
      if (tgMarketing) tgMarketing.checked = !!(prefs && prefs.marketing);
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    }
    function fecharModal() {
      if (!modal) return;
      modal.style.display = 'none';
      document.body.style.overflow = '';
    }

    const existente = lerConsent();
    if (existente) {
      window.dellaConsent = existente;
      if (existente.analytics) { carregarGA(); carregarClarity(); }
    } else {
      abrirBanner();
    }
    // Pixel carrega sempre (PageView, ViewContent, AddToCart sem PII)
    // AM params (email/telefone hash) so sao incluidos se marketing consent = true
    carregarMetaPixel();

    // Quando o usuario consentir, carrega GA/Clarity (Pixel ja esta ativo)
    document.addEventListener('della:consent', function (e) {
      if (!e.detail) return;
      if (e.detail.analytics) { carregarGA(); carregarClarity(); }
    });

    const btnAceitarTudo = document.getElementById('della-cookie-aceitar-tudo');
    if (btnAceitarTudo) btnAceitarTudo.addEventListener('click', function () {
      salvarConsent({ analytics: true, marketing: true });
      fecharBanner();
    });

    const btnCustomizar = document.getElementById('della-cookie-customizar');
    if (btnCustomizar) btnCustomizar.addEventListener('click', function () {
      abrirModal(lerConsent() || { analytics: false, marketing: false });
    });

    const btnFecharModal = document.getElementById('della-cookie-modal-fechar');
    if (btnFecharModal) btnFecharModal.addEventListener('click', fecharModal);

    const btnNecess = document.getElementById('della-cookie-apenas-necessarios');
    if (btnNecess) btnNecess.addEventListener('click', function () {
      salvarConsent({ analytics: false, marketing: false });
      fecharModal();
      fecharBanner();
    });

    const btnSalvar = document.getElementById('della-cookie-salvar');
    if (btnSalvar) btnSalvar.addEventListener('click', function () {
      salvarConsent({
        analytics: tgAnalytics ? tgAnalytics.checked : false,
        marketing: tgMarketing ? tgMarketing.checked : false,
      });
      fecharModal();
      fecharBanner();
    });

    if (modal) modal.addEventListener('click', function (e) {
      if (e.target === modal) fecharModal();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal && modal.style.display === 'flex') fecharModal();
    });

    const linkPrefs = document.getElementById('della-cookie-preferencias-link');
    if (linkPrefs) linkPrefs.addEventListener('click', function (e) {
      e.preventDefault();
      abrirModal(lerConsent() || { analytics: false, marketing: false });
    });
  })();

  // ─── Tarja de Anúncios ─────────────────────────────────────────────────────
  (function() {
    const tarja = document.getElementById('tarja-anuncio');
    if (!tarja) return;

    const itens = tarja.querySelectorAll('.tarja-item');
    const total = itens.length;
    if (total === 0) return;

    tarja.setAttribute('data-total', total);

    let atual = 0;
    let timer = null;
    const DURACAO = 5000;

    function irPara(idx) {
      const anterior = itens[atual];
      anterior.classList.remove('tarja-ativa');
      anterior.classList.add('tarja-saindo');
      setTimeout(function() { anterior.classList.remove('tarja-saindo'); }, 500);

      atual = (idx + total) % total;
      itens[atual].classList.add('tarja-ativa');
    }

    function iniciarTimer() {
      clearInterval(timer);
      if (total > 1) timer = setInterval(function() { irPara(atual + 1); }, DURACAO);
    }

    iniciarTimer();

    const btnPrev = document.getElementById('tarja-prev');
    const btnNext = document.getElementById('tarja-next');
    if (btnPrev) btnPrev.addEventListener('click', function() { irPara(atual - 1); iniciarTimer(); });
    if (btnNext) btnNext.addEventListener('click', function() { irPara(atual + 1); iniciarTimer(); });
  })();

  // ─── Mascara de telefone no formulario de contato ──────────────────────────
  (function () {
    var contatoTel = document.querySelector('.contato-form #telefone');
    if (!contatoTel) return;
    function aplicarMascaraTel() {
      var v = contatoTel.value.replace(/\D/g, '').slice(0, 11);
      if (v.length > 7) v = v.replace(/(\d{2})(\d{1})(\d{4})(\d{0,4}).*/, '($1) $2 $3-$4');
      else if (v.length > 3) v = v.replace(/(\d{2})(\d)(\d+)/, '($1) $2 $3');
      else if (v.length > 2) v = v.replace(/(\d{2})(\d+)/, '($1) $2');
      contatoTel.value = v;
    }
    contatoTel.addEventListener('input', aplicarMascaraTel);
  })();

  // ─── select_item — clique em produto no grid de listagem ──────────────────
  document.addEventListener('click', function (e) {
    const link = e.target.closest('.produto-card a[data-item-id]');
    if (!link) return;
    window.dellaTrackGA('select_item', {
      item_list_id: document.body.dataset.itemListId || 'loja',
      item_list_name: document.body.dataset.itemListName || 'Listagem',
      items: [{
        item_id: link.dataset.itemId || '',
        item_name: link.dataset.itemName || '',
        item_category: link.dataset.itemCategory || '',
        price: parseFloat(link.dataset.itemPrice || 0),
        index: parseInt(link.dataset.itemIndex || 0, 10),
      }],
    });
  });

  // ─── search — rastreamento de busca (GA4 + Meta Pixel) ────────────────────
  document.querySelectorAll('.busca-form-wrapper form, form[action*="/loja/"]').forEach(function (form) {
    form.addEventListener('submit', function () {
      const input = form.querySelector('input[name="q"]');
      const q = (input ? input.value : '').trim();
      if (!q) return;
      window.dellaTrackGA('search', { search_term: q });
      if (window.fbq) fbq('track', 'Search', { search_string: q });
    });
  });

  // ─── data-confirm delegation (substitui onclick/onsubmit inline) ───────────
  document.addEventListener('click', function (e) {
    const el = e.target.closest('[data-confirm]');
    if (!el || el.tagName === 'FORM') return;
    const msg = el.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);

  document.addEventListener('submit', function (e) {
    const form = e.target.closest('form[data-confirm]');
    if (!form) return;
    const msg = form.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);

});

// ─── Exit-intent popup (captura email carrinho abandonado) ───────────────────
(function () {
  var STORAGE_KEY = 'della_popup_cart';

  function jaExibido() {
    try { return sessionStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { return false; }
  }
  function marcarExibido() {
    try { sessionStorage.setItem(STORAGE_KEY, '1'); } catch (e) {}
  }

  function abrir() {
    var el = document.getElementById('popup-carrinho-email');
    if (!el) return;
    if (el.classList.contains('popup-ativo')) return;
    el.classList.add('popup-ativo');
    el.removeAttribute('aria-hidden');
    // Registra no analytics interno que o pop-up de saida apareceu para esta sessao.
    if (typeof window.dellaTrack === 'function') window.dellaTrack('popup_saida_exibido');
    // Marca como exibido na hora em que abre: garante 1x por sessao e impede
    // re-disparo do evento caso o gatilho de saida ocorra mais de uma vez.
    marcarExibido();
    var input = el.querySelector('#popup-carrinho-email-input');
    if (input) setTimeout(function () { input.focus(); }, 320);
  }

  function fechar() {
    var el = document.getElementById('popup-carrinho-email');
    if (!el) return;
    el.classList.remove('popup-ativo');
    el.setAttribute('aria-hidden', 'true');
    marcarExibido();
  }

  function init() {
    var popup = document.getElementById('popup-carrinho-email');
    if (!popup) return;
    if (jaExibido()) return;
    if (!window._dellaTemCarrinho) return;

    popup.setAttribute('aria-hidden', 'true');

    popup.addEventListener('click', function (e) {
      if (e.target === popup) fechar();
    });
    var btnFechar = popup.querySelector('.popup-carrinho-fechar');
    if (btnFechar) btnFechar.addEventListener('click', fechar);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && popup.classList.contains('popup-ativo')) fechar();
    });

    var form = document.getElementById('popup-carrinho-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var input = document.getElementById('popup-carrinho-email-input');
        var btn   = document.getElementById('popup-carrinho-btn');
        var email = (input ? input.value : '').trim();
        if (!email) return;

        if (btn) { btn.disabled = true; btn.textContent = 'Enviando...'; }

        var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content
                   || (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';

        fetch('/analytics/capturar-email-popup/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
          body: JSON.stringify({ email: email }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (form) form.style.display = 'none';
          var msg = document.getElementById('popup-carrinho-msg');
          if (msg) {
            msg.style.display = 'block';
            if (data.codigo) {
              var codigoEl = msg.querySelector('.popup-carrinho-codigo');
              if (codigoEl) codigoEl.textContent = data.codigo;
            }
          }
          marcarExibido();
        })
        .catch(function () {
          if (btn) { btn.disabled = false; btn.textContent = 'Quero meu cupom'; }
        });
      });
    }

    // Desktop: mouse saindo pelo topo (exit-intent)
    function onMouseLeave(e) {
      if (e.clientY <= 0 && !jaExibido()) {
        document.removeEventListener('mouseleave', onMouseLeave);
        setTimeout(abrir, 400);
      }
    }
    document.addEventListener('mouseleave', onMouseLeave);

    // Saida (mobile + desktop): aba fica oculta -- troca de app, bloqueio de
    // tela, fechar ou trocar de aba. Dispara na SAIDA (hidden), nunca no retorno:
    // o abandono tipico no mobile e sair e NAO voltar, entao esperar o 'visible'
    // (versao anterior) perdia justamente esse caso e o popup nunca aparecia.
    // Guarda navegacao interna: clique em link/submit do proprio site tambem
    // dispara 'hidden', e nesse caso o popup nao deve abrir (nao e abandono).
    var navegandoInterno = false;
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (a && a.origin === window.location.origin) navegandoInterno = true;
    }, true);
    document.addEventListener('submit', function () { navegandoInterno = true; }, true);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') {
        navegandoInterno = false;
        return;
      }
      if (document.visibilityState === 'hidden' && !jaExibido() && !navegandoInterno) {
        abrir();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

// ─── D'ELLA Analytics interno ────────────────────────────────────────────────
window.dellaTrack = function (tipo, dados) {
  try {
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content
              || (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    fetch('/analytics/evento/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
        'X-Analytics-Source': 'della-tracker',
      },
      body: JSON.stringify(Object.assign({ tipo: tipo }, dados || {})),
      keepalive: true,
    }).catch(function () {});
  } catch (_) {}
};
