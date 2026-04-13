#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# check_security.sh — Verificação de segurança pré-deploy
# Execute antes de qualquer git push ou deploy:
#   bash scripts/check_security.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo -e "${GREEN}[OK]${NC} $desc"
    else
        echo -e "${RED}[ERRO]${NC} $desc"
        ERRORS=$((ERRORS + 1))
    fi
}

warn() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

echo ""
echo "════════════════════════════════════════════"
echo "  Della Instore — Verificação de Segurança  "
echo "════════════════════════════════════════════"
echo ""

# 1. .env não está sendo rastreado pelo git
if git ls-files --error-unmatch .env > /dev/null 2>&1; then
    check ".env NÃO está no git" "fail"
    echo -e "       ${RED}CRÍTICO: remova com: git rm --cached .env${NC}"
else
    check ".env NÃO está no git" "ok"
fi

# 2. .env.example existe (template sem valores reais)
if [ -f ".env.example" ]; then
    check ".env.example existe" "ok"
else
    check ".env.example existe" "fail"
fi

# 3. .env está no .gitignore
if grep -q "^\.env$" .gitignore 2>/dev/null; then
    check ".env está no .gitignore" "ok"
else
    check ".env está no .gitignore" "fail"
fi

# 4. Nenhum arquivo .env.* (exceto .example) no git
if git ls-files | grep -E "^\.env\." | grep -v "\.example$" > /dev/null 2>&1; then
    check "Nenhum .env.* rastreado" "fail"
    echo -e "       ${RED}Arquivo(s) encontrado(s): $(git ls-files | grep '\.env\.' | grep -v '\.example$')${NC}"
else
    check "Nenhum .env.* rastreado" "ok"
fi

# 5. SECRET_KEY não está hardcoded em nenhum arquivo Python
if grep -r "SECRET_KEY\s*=\s*['\"][^c]" --include="*.py" . --exclude-dir=venv 2>/dev/null | grep -v "config(" | grep -v "#" > /dev/null; then
    check "SECRET_KEY não está hardcoded" "fail"
else
    check "SECRET_KEY não está hardcoded" "ok"
fi

# 6. DEBUG não está True em production.py
if grep -q "^DEBUG\s*=\s*True" core/settings/production.py 2>/dev/null; then
    check "DEBUG=False em production.py" "fail"
else
    check "DEBUG=False em production.py" "ok"
fi

# 7. ALLOWED_HOSTS não contém '*'
if grep -r "ALLOWED_HOSTS.*\*" --include="*.py" core/settings/production.py 2>/dev/null > /dev/null; then
    check "ALLOWED_HOSTS sem wildcard '*'" "fail"
else
    check "ALLOWED_HOSTS sem wildcard '*'" "ok"
fi

# 8. Senhas de banco não hardcoded
if grep -rn "DB_PASSWORD\s*=\s*['\"]" --include="*.py" . --exclude-dir=venv 2>/dev/null | grep -v "config(" | grep -v "#" > /dev/null; then
    check "Senha do banco não hardcoded" "fail"
else
    check "Senha do banco não hardcoded" "ok"
fi

# 9. Pasta media/ não está sendo commitada
if git ls-files media/ 2>/dev/null | grep -v ".gitkeep" > /dev/null; then
    warn "Arquivos em media/ rastreados pelo git (verifique se não há imagens de prod)"
else
    check "media/ não está no git" "ok"
fi

# 10. requirements.txt existe e está atualizado
if [ -f "requirements.txt" ]; then
    check "requirements.txt existe" "ok"
else
    check "requirements.txt existe" "fail"
fi

echo ""
echo "────────────────────────────────────────────"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}Tudo certo! Deploy seguro para prosseguir.${NC}"
else
    echo -e "${RED}$ERRORS problema(s) encontrado(s). Corrija antes do deploy!${NC}"
    exit 1
fi

echo ""
