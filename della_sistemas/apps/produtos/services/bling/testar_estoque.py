import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.produtos.services.business.product_map import get_id_produto_by_sku  # noqa: E402
from apps.produtos.services.bling.stock import salvar_lancamento_estoque  # noqa: E402

sku = input("SKU para testar: ").strip()
delta_txt = input("Delta (ex: 1): ").strip()
delta = int(delta_txt) if delta_txt else 1

id_produto = get_id_produto_by_sku(sku)
if not id_produto:
    raise RuntimeError("Não achei o SKU no variants_cache. Rode Reconstruir Variações primeiro.")

tipo = "E" if delta >= 0 else "S"
quantidade = abs(delta)

print("idProduto encontrado:", id_produto)
print("tipoOperacao:", tipo)
print("quantidade:", quantidade)

resp = salvar_lancamento_estoque(
    id_produto=id_produto,
    quantidade=quantidade,
    tipo_operacao=tipo,
    observacoes="Teste ajuste estoque via sistema"
)

print("OK:", resp)
