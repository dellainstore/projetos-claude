document.addEventListener('DOMContentLoaded', () => {
  const cepInput = document.getElementById('id_end_cep');
  const btnBuscar = document.getElementById('btn-buscar-cep');
  if (!cepInput) return;

  async function buscarCep(silencioso = true) {
    const cep = cepInput.value.replace(/\D/g, '');
    if (cep.length !== 8) return;
    if (btnBuscar) btnBuscar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
    try {
      const r = await fetch(`/carrinho/cep/${cep}/`);
      const d = await r.json();
      if (d.status === 'erro') {
        if (!silencioso) alert('CEP não encontrado.');
        return;
      }
      document.getElementById('id_end_logradouro').value = d.logradouro || '';
      document.getElementById('id_end_bairro').value = d.bairro || '';
      document.getElementById('id_end_cidade').value = d.cidade || '';
      document.getElementById('id_end_estado').value = d.estado || '';
      document.getElementById('campos-endereco').style.display = 'block';
      document.querySelector('[name="numero"]')?.focus();
    } catch (_) {
      if (!silencioso) alert('Erro ao buscar CEP.');
    } finally {
      if (btnBuscar) btnBuscar.innerHTML = '<i class="fas fa-magnifying-glass"></i> Buscar';
    }
  }

  cepInput.addEventListener('input', function () {
    let v = this.value.replace(/\D/g, '').slice(0, 8);
    if (v.length > 5) v = v.replace(/(\d{5})(\d{1,3})/, '$1-$2');
    this.value = v;
  });
  cepInput.addEventListener('blur', () => buscarCep(true));
  btnBuscar?.addEventListener('click', () => {
    const cep = cepInput.value.replace(/\D/g, '');
    if (cep.length !== 8) {
      alert('CEP inválido.');
      return;
    }
    buscarCep(false);
  });
});
