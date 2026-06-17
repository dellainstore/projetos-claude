document.addEventListener('DOMContentLoaded', () => {
  const configEl = document.getElementById('checkout-confirmacao-config');
  if (!configEl) return;

  let config = null;
  try {
    config = JSON.parse(configEl.textContent || '{}');
  } catch (_) {
    return;
  }

  if (!config.pix_pagseguro || !config.pix_numero || !config.status_url) return;

  const timerEl = document.getElementById('pix-timer');
  const statusEl = document.getElementById('pix-status-bloco');
  const qrcodeAtivoEl = document.getElementById('pix-qrcode-ativo');
  const expiradoEl = document.getElementById('pix-expirado');
  const btnVerificar = document.getElementById('btn-verificar-pix');
  const btnNovoPix = document.getElementById('btn-novo-pix');
  const qrcodeImg = document.getElementById('pix-qrcode-img');
  const payloadInput = document.getElementById('pix-payload-input');

  let segundosRestantes = parseInt(config.pix_timeout || 600, 10);
  let pollingAtivo = true;
  let pollingId = null;
  let timerId = null;

  function atualizarTimer() {
    if (!timerEl) return;
    const min = String(Math.floor(segundosRestantes / 60)).padStart(2, '0');
    const sec = String(segundosRestantes % 60).padStart(2, '0');
    timerEl.textContent = `${min}:${sec}`;
  }

  function expirarPix() {
    if (timerId) clearInterval(timerId);
    if (pollingId) clearInterval(pollingId);
    pollingAtivo = false;
    qrcodeAtivoEl?.style.setProperty('display', 'none');
    expiradoEl?.style.setProperty('display', 'block');
  }

  function marcarPago() {
    if (timerId) clearInterval(timerId);
    if (pollingId) clearInterval(pollingId);
    pollingAtivo = false;
    if (statusEl) {
      statusEl.innerHTML = '<span class="text-green-600 font-semibold"><i class="fas fa-check-circle"></i> Pagamento confirmado! Atualizando…</span>';
    }
    setTimeout(() => window.location.reload(), 1500);
  }

  async function consultarStatus() {
    const res = await fetch(config.status_url);
    return res.json();
  }

  async function verificarPix() {
    if (btnVerificar) btnVerificar.textContent = 'Verificando…';
    try {
      const dados = await consultarStatus();
      if (dados.status === 'pago') {
        marcarPago();
      } else if (btnVerificar) {
        btnVerificar.textContent = 'Verificar agora';
      }
    } catch (_) {
      if (btnVerificar) btnVerificar.textContent = 'Verificar agora';
    }
  }

  async function gerarNovoPix() {
    if (!config.gerar_url) return;
    if (btnNovoPix) {
      btnNovoPix.disabled = true;
      btnNovoPix.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando…';
    }

    try {
      const res = await fetch(config.gerar_url);
      const dados = await res.json();

      if (dados.status === 'ok') {
        if (dados.via !== 'pagseguro') {
          window.location.reload();
          return;
        }

        if (qrcodeImg) qrcodeImg.src = `data:image/png;base64,${dados.qrcode}`;
        if (payloadInput) payloadInput.value = dados.payload;

        segundosRestantes = parseInt(config.pix_timeout || 600, 10);
        pollingAtivo = true;
        atualizarTimer();
        qrcodeAtivoEl?.style.setProperty('display', 'block');
        expiradoEl?.style.setProperty('display', 'none');
        if (btnVerificar) btnVerificar.textContent = 'Verificar agora';

        if (timerId) clearInterval(timerId);
        if (pollingId) clearInterval(pollingId);
        iniciarTimer();
        iniciarPolling();
      } else if (btnNovoPix) {
        btnNovoPix.disabled = false;
        btnNovoPix.innerHTML = '<i class="fas fa-sync-alt"></i> Gerar novo QR Code';
      }
    } catch (_) {
      if (btnNovoPix) {
        btnNovoPix.disabled = false;
        btnNovoPix.innerHTML = '<i class="fas fa-sync-alt"></i> Gerar novo QR Code';
      }
    }
  }

  function iniciarTimer() {
    timerId = setInterval(() => {
      segundosRestantes -= 1;
      atualizarTimer();
      if (segundosRestantes <= 0) expirarPix();
    }, 1000);
  }

  function iniciarPolling() {
    pollingId = setInterval(async () => {
      if (!pollingAtivo) return;
      try {
        const dados = await consultarStatus();
        if (dados.status === 'pago') marcarPago();
      } catch (_) {}
    }, 30000);
  }

  btnVerificar?.addEventListener('click', verificarPix);
  btnNovoPix?.addEventListener('click', gerarNovoPix);

  atualizarTimer();
  iniciarTimer();
  iniciarPolling();
});
