/**
 * Gerador dinâmico de parcelas — regras D'ELLA Instore
 *
 * - 1x–5x : sem juros  (parcela mínima R$ 150,00)
 * - 6x–12x: com juros  (TAXA_MENSAL_JUROS ao mês, parcela mínima R$ 150,00)
 * - Opções onde parcela < R$ 150,00 são ocultadas automaticamente
 *
 * Para ajustar a taxa: altere TAXA_MENSAL_JUROS abaixo (ex: 0.0249 = 2,49% a.m.)
 */

(function (global) {
  'use strict';

  var PARCELA_MINIMA   = 150.00;
  var MAX_SEM_JUROS    = 5;
  var MAX_PARCELAS     = 12;
  var TAXA_MENSAL_JUROS = 0.0249; // 2,49% a.m. — ajuste conforme contrato PagBank

  /**
   * Calcula o valor da parcela com juros (Price/SAC).
   * PMT = P * i / (1 - (1+i)^-n)
   */
  function calcPMT(total, n, taxa) {
    if (taxa === 0) return total / n;
    return total * taxa / (1 - Math.pow(1 + taxa, -n));
  }

  /**
   * Gera as options de parcelas e popula o <select> informado.
   * @param {HTMLSelectElement} selectEl  — elemento <select> a popular
   * @param {number}            total     — valor total do pedido (float)
   * @param {number}            [valorAtual] — valor já selecionado (int)
   */
  function gerarParcelas(selectEl, total, valorAtual) {
    if (!selectEl || !total || total <= 0) return;

    selectEl.innerHTML = '';

    var adicionou = false;

    for (var n = 1; n <= MAX_PARCELAS; n++) {
      var taxa       = n <= MAX_SEM_JUROS ? 0 : TAXA_MENSAL_JUROS;
      var pmt        = calcPMT(total, n, taxa);
      var totalPagar = pmt * n;

      if (pmt < PARCELA_MINIMA) continue;  // parcela abaixo do mínimo — oculta

      var label;
      if (n <= MAX_SEM_JUROS) {
        label = n + 'x de R$ ' + pmt.toFixed(2).replace('.', ',') + ' sem juros';
      } else {
        label = n + 'x de R$ ' + pmt.toFixed(2).replace('.', ',')
              + ' com juros (total R$ ' + totalPagar.toFixed(2).replace('.', ',') + ')';
      }

      var opt = document.createElement('option');
      opt.value       = String(n);
      opt.textContent = label;
      if (String(valorAtual) === String(n)) opt.selected = true;
      selectEl.appendChild(opt);
      adicionou = true;
    }

    // Fallback: se nenhuma parcela passou (pedido muito baixo), força 1x
    if (!adicionou) {
      var opt1 = document.createElement('option');
      opt1.value       = '1';
      opt1.textContent = '1x de R$ ' + total.toFixed(2).replace('.', ',') + ' sem juros';
      selectEl.appendChild(opt1);
    }
  }

  global.DellaParcelas = { gerarParcelas: gerarParcelas };

})(window);
