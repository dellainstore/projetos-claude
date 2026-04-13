#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_postgres.sh — Instala PostgreSQL e cria banco della_site
# Execute como: sudo bash scripts/setup_postgres.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "════════════════════════════════════════"
echo "  Della Instore — Setup PostgreSQL      "
echo "════════════════════════════════════════"
echo ""

# 1. Instala PostgreSQL
echo -e "${YELLOW}[1/5]${NC} Instalando PostgreSQL..."
apt-get update -q
apt-get install -y postgresql postgresql-contrib
echo -e "${GREEN}[OK]${NC} PostgreSQL instalado"

# 2. Inicia e habilita o serviço
echo -e "${YELLOW}[2/5]${NC} Iniciando serviço..."
systemctl start postgresql
systemctl enable postgresql
echo -e "${GREEN}[OK]${NC} Serviço ativo"

# 3. Solicita senha segura para o usuário do banco
echo ""
echo -e "${YELLOW}[3/5]${NC} Defina a senha do usuário della_user:"
read -s -p "Senha: " DB_PASS
echo ""
read -s -p "Confirme: " DB_PASS2
echo ""

if [ "$DB_PASS" != "$DB_PASS2" ]; then
    echo "Senhas não coincidem. Abortando."
    exit 1
fi

# 4. Cria usuário e banco
echo -e "${YELLOW}[4/5]${NC} Criando usuário e banco..."
sudo -u postgres psql << SQL
-- Cria usuário com senha
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'della_user') THEN
        CREATE ROLE della_user LOGIN PASSWORD '${DB_PASS}';
    ELSE
        ALTER ROLE della_user PASSWORD '${DB_PASS}';
    END IF;
END
\$\$;

-- Cria banco de produção
SELECT 'CREATE DATABASE della_site OWNER della_user ENCODING ''UTF8'' LC_COLLATE ''pt_BR.UTF-8'' LC_CTYPE ''pt_BR.UTF-8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'della_site')\gexec

-- Garante permissões
GRANT ALL PRIVILEGES ON DATABASE della_site TO della_user;
SQL
echo -e "${GREEN}[OK]${NC} Banco della_site criado"

# 5. Salva senha no .env (se existir)
ENV_FILE="/var/www/della-sistemas/projetos-claude/site_della/.env"
if [ -f "$ENV_FILE" ]; then
    sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=${DB_PASS}/" "$ENV_FILE"
    echo -e "${GREEN}[OK]${NC} .env atualizado com a senha do banco"
else
    echo ""
    echo -e "${YELLOW}Lembre de definir no .env:${NC}"
    echo "DB_PASSWORD=${DB_PASS}"
fi

echo ""
echo "════════════════════════════════════════"
echo -e "${GREEN}Setup concluído!${NC}"
echo ""
echo "Teste a conexão:"
echo "  psql -h localhost -U della_user -d della_site"
echo "════════════════════════════════════════"
echo ""
