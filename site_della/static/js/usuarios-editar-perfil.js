document.addEventListener('DOMContentLoaded', () => {
  const tel = document.querySelector('[name="telefone"]');
  if (tel) {
    tel.addEventListener('input', function () {
      let v = this.value.replace(/\D/g, '').slice(0, 11);
      if (v.length > 7) v = v.replace(/(\d{2})(\d{1})(\d{4})(\d{0,4}).*/, '($1) $2 $3-$4');
      else if (v.length > 3) v = v.replace(/(\d{2})(\d{1})(\d+)/, '($1) $2 $3');
      else if (v.length > 2) v = v.replace(/(\d{2})(\d+)/, '($1) $2');
      this.value = v;
    });
  }

  const data = document.querySelector('[name="data_nascimento"]');
  if (data) {
    data.addEventListener('input', function () {
      let v = this.value.replace(/\D/g, '').slice(0, 8);
      if (v.length > 4) v = v.replace(/(\d{2})(\d{2})(\d{0,4})/, '$1/$2/$3');
      else if (v.length > 2) v = v.replace(/(\d{2})(\d{0,2})/, '$1/$2');
      this.value = v;
    });
  }
});
