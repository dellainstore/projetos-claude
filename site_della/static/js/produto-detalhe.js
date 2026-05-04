document.addEventListener('DOMContentLoaded', () => {
  const configEl = document.getElementById('produto-detalhe-config');
  if (!configEl) return;

  let config = null;
  try {
    config = JSON.parse(configEl.textContent || '{}');
  } catch (_) {
    return;
  }

  const fotoPrincipal = document.getElementById('foto-principal');
  const thumbsWrap = document.getElementById('galeria-thumbs');
  const galeriaPrincipal = document.querySelector('.galeria-principal');
  const variacoesMap = config.variacoes || {};
  const galeriasPorCor = config.galerias_por_cor || {};
  const galeriaPadrao = config.galeria_padrao || [];
  const corInicialId = config.cor_inicial_id || '';
  const labelCorSel = document.getElementById('label-cor-selecionada');
  const labelTamSel = document.getElementById('label-tamanho-selecionado');
  const infoDisponibilidade = document.getElementById('info-disponibilidade-variacao');
  const precoDeEl = document.getElementById('produto-preco-de');
  const precoPorEl = document.getElementById('produto-preco-por');
  const parcelamentoEl = document.getElementById('produto-parcelamento');
  const qtyInput = document.getElementById('qty-input');
  const btnComprar = document.getElementById('btn-adicionar-carrinho');
  const btnComprarAgora = document.getElementById('btn-comprar-agora');
  const btnPrev = document.querySelector('.galeria-nav-prev');
  const btnNext = document.querySelector('.galeria-nav-next');

  let corSelecionadaId = null;
  let tamSelecionadoId = null;
  let variacaoSelecionadaId = null;
  let variacaoSelecionada = null;
  let galeriaAtual = [];
  let indexAtual = 0;
  let gStartX = 0;
  let gStartY = 0;
  let gAtivo = false;

  const corButtons = Array.from(document.querySelectorAll('.variacao-cor'));
  const tamanhoButtons = Array.from(document.querySelectorAll('.variacao-tamanho'));
  const temCores = corButtons.length > 0;
  const temTamanhos = tamanhoButtons.length > 0;

  function fmtBRL(v) {
    return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function galeriaParaCor(corId) {
    if (corId && Array.isArray(galeriasPorCor[corId]) && galeriasPorCor[corId].length) {
      return galeriasPorCor[corId];
    }
    if (corInicialId && Array.isArray(galeriasPorCor[corInicialId]) && galeriasPorCor[corInicialId].length) {
      return galeriasPorCor[corInicialId];
    }
    return galeriaPadrao;
  }

  function atualizarVisibilidadeNavegacao() {
    const mostrar = galeriaAtual.length > 1;
    if (thumbsWrap) {
      thumbsWrap.style.display = mostrar ? '' : 'none';
    }
    if (btnPrev) btnPrev.style.display = mostrar ? '' : 'none';
    if (btnNext) btnNext.style.display = mostrar ? '' : 'none';
  }

  function ativarThumb(idx) {
    if (!fotoPrincipal || !galeriaAtual.length) return;
    const total = galeriaAtual.length;
    indexAtual = ((idx % total) + total) % total;
    const foto = galeriaAtual[indexAtual];
    fotoPrincipal.src = foto.src;
    fotoPrincipal.alt = foto.alt;
    if (thumbsWrap) {
      thumbsWrap.querySelectorAll('.galeria-thumb').forEach((thumb, thumbIdx) => {
        thumb.classList.toggle('ativa', thumbIdx === indexAtual);
      });
    }
  }

  function renderGaleria(corId) {
    galeriaAtual = galeriaParaCor(corId);
    if (!galeriaAtual.length) {
      galeriaAtual = galeriaPadrao;
    }
    if (!galeriaAtual.length) return;

    if (thumbsWrap) {
      thumbsWrap.innerHTML = '';
      galeriaAtual.forEach((foto, idx) => {
        const thumb = document.createElement('button');
        thumb.className = `galeria-thumb${idx === 0 ? ' ativa' : ''}`;
        thumb.type = 'button';
        thumb.dataset.src = foto.src;
        thumb.dataset.alt = foto.alt;
        thumb.setAttribute('role', 'listitem');
        thumb.setAttribute('aria-label', `Foto ${idx + 1}`);
        const img = document.createElement('img');
        img.src = foto.src;
        img.alt = foto.alt;
        img.loading = 'lazy';
        thumb.appendChild(img);
        thumb.addEventListener('click', () => ativarThumb(idx));
        thumbsWrap.appendChild(thumb);
      });
    }

    indexAtual = 0;
    ativarThumb(0);
    atualizarVisibilidadeNavegacao();
  }

  function atualizarPrecoExibido(entry) {
    if (!btnComprar || !precoPorEl) return;
    const precoBase = entry ? entry.preco_base : (btnComprar.dataset.precoBase || btnComprar.dataset.preco || '0');
    const precoAtual = entry ? entry.preco_atual : (btnComprar.dataset.precoPromocional || btnComprar.dataset.preco || '0');
    const precoPromocional = entry ? entry.preco_promocional : (btnComprar.dataset.precoPromocional || '');
    const emPromocao = entry ? entry.em_promocao : !!precoPromocional;
    const precoUsado = emPromocao ? precoAtual : precoBase;
    btnComprar.dataset.preco = precoUsado;
    precoPorEl.textContent = `R$ ${fmtBRL(precoUsado)}`;
    if (precoDeEl) {
      if (emPromocao) {
        precoDeEl.style.display = '';
        precoDeEl.textContent = `R$ ${fmtBRL(precoBase)}`;
      } else {
        precoDeEl.style.display = 'none';
        precoDeEl.textContent = '';
      }
    }
    if (parcelamentoEl) {
      const total = Number(precoUsado || 0);
      let texto = '';
      if (total >= 300) {
        for (let n = 5; n >= 2; n -= 1) {
          const parcela = total / n;
          if (parcela >= 150) {
            texto = `ou ${n}x de R$ ${fmtBRL(parcela)} sem juros`;
            break;
          }
        }
      }
      if (texto) {
        parcelamentoEl.style.display = '';
        parcelamentoEl.textContent = texto;
      } else {
        parcelamentoEl.style.display = 'none';
        parcelamentoEl.textContent = '';
      }
    }
  }

  function resolverVariacao() {
    const corKey = corSelecionadaId || 'null';
    const tamKey = tamSelecionadoId || 'null';
    const entry = variacoesMap[`${corKey}_${tamKey}`];
    variacaoSelecionadaId = entry ? entry.id : null;
    variacaoSelecionada = entry || null;
    window.variacaoSelecionada = variacaoSelecionada;

    if (qtyInput) {
      const maxQty = (entry && entry.disponibilidade === 'imediata' && entry.estoque > 0) ? entry.estoque : 10;
      qtyInput.max = maxQty;
      if (parseInt(qtyInput.value, 10) > maxQty) qtyInput.value = maxQty;
    }
    if (infoDisponibilidade) {
      if (entry) {
        infoDisponibilidade.style.display = '';
        infoDisponibilidade.textContent = entry.disponibilidade_label + '.';
      } else {
        infoDisponibilidade.style.display = 'none';
        infoDisponibilidade.textContent = '';
      }
    }
    atualizarPrecoExibido(entry);
  }

  function atualizarDisponibilidadeTamanhos() {
    tamanhoButtons.forEach((btn) => {
      const tamId = btn.dataset.tamanhoId;
      if (!corSelecionadaId) {
        btn.classList.remove('esgotado');
        btn.disabled = false;
        btn.removeAttribute('aria-disabled');
        btn.title = '';
        return;
      }
      const entry = variacoesMap[`${corSelecionadaId}_${tamId}`];
      if (entry === undefined) {
        btn.classList.add('esgotado');
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
        btn.title = 'Indisponível nesta cor';
      } else if (!entry.disponivel) {
        btn.classList.add('esgotado');
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
        btn.title = 'Esgotado';
      } else {
        btn.classList.remove('esgotado');
        btn.disabled = false;
        btn.removeAttribute('aria-disabled');
        btn.title = '';
      }
    });
  }

  function atualizarDisponibilidadeCores() {
    corButtons.forEach((btn) => {
      const corId = btn.dataset.corId;
      const tamKey = tamSelecionadoId || 'null';
      if (!tamSelecionadoId) {
        btn.classList.remove('esgotado');
        btn.disabled = false;
        btn.removeAttribute('aria-disabled');
        btn.title = '';
        return;
      }
      const entry = variacoesMap[`${corId}_${tamKey}`];
      if (entry === undefined) {
        btn.classList.add('esgotado');
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
        btn.title = 'Indisponível neste tamanho';
      } else if (!entry.disponivel) {
        btn.classList.add('esgotado');
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
        btn.title = 'Esgotado';
      } else {
        btn.classList.remove('esgotado');
        btn.disabled = false;
        btn.removeAttribute('aria-disabled');
        btn.title = '';
      }
    });
  }

  function validarTamanhoAposCorMudar() {
    if (!tamSelecionadoId) return;
    const entry = variacoesMap[`${corSelecionadaId || 'null'}_${tamSelecionadoId}`];
    if (!entry || !entry.disponivel) {
      document.querySelector('.variacao-tamanho.selecionado')?.classList.remove('selecionado');
      tamSelecionadoId = null;
      if (labelTamSel) labelTamSel.textContent = 'Selecione';
    }
  }

  function validarCorAposTamanhoMudar() {
    if (!corSelecionadaId) return;
    const entry = variacoesMap[`${corSelecionadaId}_${tamSelecionadoId || 'null'}`];
    if (!entry || !entry.disponivel) {
      const fallback = corButtons.find((btn) => !btn.disabled);
      corButtons.forEach((btn) => btn.classList.remove('selecionado'));
      corSelecionadaId = fallback ? fallback.dataset.corId : null;
      if (fallback) {
        fallback.classList.add('selecionado');
        if (labelCorSel) labelCorSel.textContent = fallback.dataset.cor;
        renderGaleria(corSelecionadaId);
      } else if (labelCorSel) {
        labelCorSel.textContent = 'Selecione';
      }
    }
  }

  function mostrarAviso(msg, scrollSelector) {
    const aviso = document.getElementById('aviso-variacao');
    if (aviso) {
      aviso.textContent = msg;
      aviso.classList.remove('hidden');
    }
    if (scrollSelector) {
      document.querySelector(scrollSelector)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  async function adicionarAoCarrinho({ redirecionarCheckout = false }) {
    if (temCores && !corSelecionadaId) {
      mostrarAviso('Selecione uma cor antes de continuar.', '.variacao-cor');
      return;
    }
    if (temTamanhos && !tamSelecionadoId) {
      mostrarAviso('Selecione um tamanho antes de continuar.', '.variacao-tamanho');
      return;
    }
    document.getElementById('aviso-variacao')?.classList.add('hidden');

    const produtoId = (redirecionarCheckout ? btnComprarAgora : btnComprar)?.dataset.produtoId;
    const quantidade = parseInt(qtyInput?.value || '1', 10);
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    const precoEvento = variacaoSelecionada?.preco_atual
      ? parseFloat(variacaoSelecionada.preco_atual)
      : parseFloat((btnComprar?.dataset.preco || '0'));
    const metaEventId = (window.crypto && window.crypto.randomUUID)
      ? `addtocart_${window.crypto.randomUUID().replace(/-/g, '')}`
      : `addtocart_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const btn = redirecionarCheckout ? btnComprarAgora : btnComprar;
    const textoOriginal = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = redirecionarCheckout
      ? '<i class="fas fa-spinner fa-spin"></i> Indo para o checkout...'
      : '<i class="fas fa-spinner fa-spin"></i> Adicionando...';

    try {
      const res = await fetch(`/carrinho/adicionar/${produtoId}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          variacao_id: variacaoSelecionadaId || '',
          quantidade,
          meta_event_id: metaEventId,
        }),
      });
      const dados = await res.json();

      if (dados.status === 'ok') {
        if (window.fbq) {
          fbq('track', 'AddToCart', {
            content_ids: [produtoId],
            content_type: 'product',
            value: precoEvento * quantidade,
            currency: 'BRL',
          }, { eventID: metaEventId });
        }
        if (redirecionarCheckout) {
          window.location.href = '/carrinho/checkout/';
          return;
        }
        if (typeof window.atualizarDrawerConteudo === 'function') {
          window.atualizarDrawerConteudo(dados);
        }
        if (typeof window.abrirCarrinho === 'function') {
          window.abrirCarrinho();
        }
        btn.innerHTML = '<i class="fas fa-check"></i> Adicionado!';
        setTimeout(() => {
          btn.innerHTML = textoOriginal;
          btn.disabled = false;
        }, 2000);
      } else {
        mostrarAviso(dados.mensagem || 'Estoque insuficiente.');
        btn.innerHTML = textoOriginal;
        btn.disabled = false;
      }
    } catch (_) {
      btn.innerHTML = textoOriginal;
      btn.disabled = false;
    }
  }

  async function consultarFreteProduto() {
    const cepInput = document.getElementById('frete-produto-cep');
    const btn = document.getElementById('frete-produto-btn');
    const resultado = document.getElementById('frete-produto-resultado');
    if (!cepInput || !btn || !resultado) return;

    const cep = cepInput.value.replace(/\D/g, '');
    if (cep.length !== 8) {
      resultado.innerHTML = '<p class="frete-erro">Informe um CEP válido (8 dígitos).</p>';
      return;
    }

    btn.disabled = true;
    btn.textContent = '...';
    resultado.innerHTML = '';

    const preco = btnComprar ? (btnComprar.dataset.preco || '0') : '0';
    const peso = btnComprar ? (btnComprar.dataset.peso || '500') : '500';
    const qty = qtyInput ? qtyInput.value : '1';
    const prazoAdicional = window.variacaoSelecionada ? (window.variacaoSelecionada.prazo_confeccao_dias || 0) : 0;

    function dataEntrega(prazo) {
      const d = new Date();
      d.setDate(d.getDate() + parseInt(prazo || 0, 10));
      return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    }

    try {
      const [resEnd, resFrete] = await Promise.all([
        fetch(`/carrinho/cep/${cep}/`),
        fetch(`/carrinho/frete/?cep=${cep}&preco=${preco}&quantidade=${qty}&peso=${peso}&prazo_adicional=${prazoAdicional}`),
      ]);
      const dadosEnd = await resEnd.json();
      const dadosFrete = await resFrete.json();

      let html = '';
      if (dadosEnd.status === 'ok' && (dadosEnd.logradouro || dadosEnd.cidade)) {
        const end = [dadosEnd.logradouro, dadosEnd.bairro, dadosEnd.cidade, dadosEnd.estado].filter(Boolean).join(', ');
        html += `<p class="frete-endereco"><i class="fas fa-location-dot"></i> ${end}</p>`;
      }
      if (dadosFrete.status === 'ok' && dadosFrete.opcoes.length) {
        html += '<ul class="frete-opcoes">';
        dadosFrete.opcoes.forEach((op) => {
          const precoOp = parseFloat(op.preco).toLocaleString('pt-BR', { minimumFractionDigits: 2 });
          html += `
            <li class="frete-opcao">
              <div>
                <span class="frete-opcao-nome">${op.empresa} ${op.nome}</span>
                <span class="frete-opcao-data">${dataEntrega(op.prazo)}</span>
                <span class="frete-opcao-data">${op.descricao}</span>
              </div>
              <span class="frete-opcao-preco">R$&nbsp;${precoOp}</span>
            </li>`;
        });
        html += '</ul>';
      } else if (dadosFrete.status !== 'ok') {
        html += `<p class="frete-erro">${dadosFrete.erro || 'Não foi possível calcular o frete.'}</p>`;
      }
      resultado.innerHTML = html;
    } catch (_) {
      resultado.innerHTML = '<p class="frete-erro">Erro ao consultar. Tente novamente.</p>';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Consultar';
    }
  }

  corButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      corButtons.forEach((b) => b.classList.remove('selecionado'));
      btn.classList.add('selecionado');
      corSelecionadaId = btn.dataset.corId;
      if (labelCorSel) labelCorSel.textContent = btn.dataset.cor;
      renderGaleria(corSelecionadaId);
      atualizarDisponibilidadeTamanhos();
      atualizarDisponibilidadeCores();
      validarTamanhoAposCorMudar();
      resolverVariacao();
    });
  });

  tamanhoButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      const jaSelecionado = btn.classList.contains('selecionado');
      tamanhoButtons.forEach((b) => b.classList.remove('selecionado'));
      if (jaSelecionado) {
        tamSelecionadoId = null;
        if (labelTamSel) labelTamSel.textContent = 'Selecione';
      } else {
        btn.classList.add('selecionado');
        tamSelecionadoId = btn.dataset.tamanhoId;
        if (labelTamSel) labelTamSel.textContent = btn.dataset.tamanho;
      }
      atualizarDisponibilidadeCores();
      validarCorAposTamanhoMudar();
      resolverVariacao();
    });
  });

  btnPrev?.addEventListener('click', () => ativarThumb(indexAtual - 1));
  btnNext?.addEventListener('click', () => ativarThumb(indexAtual + 1));

  galeriaPrincipal?.addEventListener('touchstart', (e) => {
    gStartX = e.touches[0].clientX;
    gStartY = e.touches[0].clientY;
    gAtivo = true;
  }, { passive: true });

  galeriaPrincipal?.addEventListener('touchend', (e) => {
    if (!gAtivo || galeriaAtual.length <= 1) return;
    gAtivo = false;
    const dx = e.changedTouches[0].clientX - gStartX;
    const dy = e.changedTouches[0].clientY - gStartY;
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
    ativarThumb(dx < 0 ? indexAtual + 1 : indexAtual - 1);
  }, { passive: true });

  document.getElementById('qty-menos')?.addEventListener('click', () => {
    const v = parseInt(qtyInput.value, 10);
    if (v > 1) qtyInput.value = v - 1;
  });
  document.getElementById('qty-mais')?.addEventListener('click', () => {
    const v = parseInt(qtyInput.value, 10);
    const max = parseInt(qtyInput.max || '10', 10);
    if (v < max) qtyInput.value = v + 1;
  });
  btnComprar?.addEventListener('click', () => adicionarAoCarrinho({ redirecionarCheckout: false }));
  btnComprarAgora?.addEventListener('click', () => adicionarAoCarrinho({ redirecionarCheckout: true }));
  document.querySelectorAll('.acordeao-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.acordeao;
      const conteudo = document.getElementById(`acordeao-${id}`);
      const icon = btn.querySelector('i');
      const aberto = conteudo.classList.toggle('aberto');
      btn.setAttribute('aria-expanded', aberto);
      if (icon) icon.className = aberto ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
    });
  });
  document.getElementById('frete-produto-cep')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 8);
    if (v.length > 5) v = v.slice(0, 5) + '-' + v.slice(5);
    e.target.value = v;
  });
  document.getElementById('frete-produto-btn')?.addEventListener('click', consultarFreteProduto);
  document.getElementById('frete-produto-cep')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') consultarFreteProduto();
  });

  corSelecionadaId = corInicialId || (corButtons[0] ? corButtons[0].dataset.corId : null);
  if (corSelecionadaId) {
    const btnInicial = corButtons.find((btn) => btn.dataset.corId === corSelecionadaId) || corButtons[0];
    if (btnInicial) {
      corButtons.forEach((btn) => btn.classList.remove('selecionado'));
      btnInicial.classList.add('selecionado');
      corSelecionadaId = btnInicial.dataset.corId;
      if (labelCorSel) labelCorSel.textContent = btnInicial.dataset.cor;
    }
  }
  renderGaleria(corSelecionadaId);
  atualizarDisponibilidadeTamanhos();
  atualizarDisponibilidadeCores();
  resolverVariacao();

  // ─── Zoom na foto principal ────────────────────────────────────────────────
  const zoomWrap = document.getElementById('galeria-zoom-wrap');
  const fotoPrincipal = document.getElementById('foto-principal');
  if (zoomWrap && fotoPrincipal) {
    zoomWrap.addEventListener('mousemove', (e) => {
      const rect = zoomWrap.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      fotoPrincipal.style.transformOrigin = `${x}% ${y}%`;
    });
    zoomWrap.addEventListener('mouseleave', () => {
      fotoPrincipal.style.transformOrigin = '50% 50%';
    });
  }
});
