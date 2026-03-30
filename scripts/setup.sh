#!/usr/bin/env bash
# ─── ERPNext Semantic Finance — Setup Inicial ──────────────────────────────────
#
# Script para configurar e iniciar a stack completa.
# Detecta o provider de vector store (.env) e sobe os serviços adequados.
#
# Uso:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# ───────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ─── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── Helpers ──────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERRO]${NC}  $*"; }
die()     { error "$@"; exit 1; }

# ─── Diretórios ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/docker"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"

# ─── Pré-requisitos ──────────────────────────────────────────────────────────
check_prerequisites() {
    info "Verificando pré-requisitos..."

    command -v docker >/dev/null 2>&1 || die "Docker não encontrado. Instale: https://docs.docker.com/get-docker/"
    command -v docker compose >/dev/null 2>&1 || die "'docker compose' não disponível. Atualize o Docker."

    success "Docker e Docker Compose encontrados."
}

# ─── Arquivo .env ─────────────────────────────────────────────────────────────
ensure_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            info "Copiando .env.example → .env"
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            warn "Edite o arquivo .env com suas configurações antes de prosseguir."
            warn "Arquivo: $ENV_FILE"
        else
            die ".env.example não encontrado em $ENV_EXAMPLE"
        fi
    else
        success "Arquivo .env já existe."
    fi
}

# ─── Leitura de variável do .env ──────────────────────────────────────────────
read_env_var() {
    local var_name="$1"
    local default_value="${2:-}"
    local value

    value=$(grep -E "^${var_name}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs) || true

    if [ -z "$value" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}

# ─── Subir stack ──────────────────────────────────────────────────────────────
start_stack() {
    local provider="$1"

    info "Subindo a stack Docker Compose..."

    if [ "$provider" = "qdrant" ]; then
        info "Provider: Qdrant (self-hosted) — incluindo profile 'qdrant'"
        docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" --profile qdrant up -d
    else
        info "Provider: Pinecone (cloud) — sem serviço Qdrant local"
        docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" up -d
    fi

    success "Serviços iniciados."
}

# ─── Pull modelo Ollama ───────────────────────────────────────────────────────
pull_ollama_model() {
    local model
    model=$(read_env_var "OLLAMA_EMBEDDING_MODEL" "nomic-embed-text")

    info "Baixando modelo Ollama: $model (pode levar alguns minutos)..."
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" exec -T ollama ollama pull "$model" || {
        warn "Não foi possível baixar o modelo agora. Execute manualmente depois:"
        warn "  docker exec erpnext-ollama ollama pull $model"
    }
}

# ─── Validar Pinecone ─────────────────────────────────────────────────────────
validate_pinecone() {
    local api_key index_name

    api_key=$(read_env_var "PINECONE_API_KEY")
    index_name=$(read_env_var "PINECONE_INDEX_NAME")

    if [ -z "$api_key" ]; then
        die "PINECONE_API_KEY não definida no .env. Configure antes de continuar."
    fi

    if [ -z "$index_name" ]; then
        die "PINECONE_INDEX_NAME não definido no .env. Configure antes de continuar."
    fi

    success "Configuração Pinecone validada (index: $index_name)."
}

# ─── Aguardar ERPNext ─────────────────────────────────────────────────────────
wait_for_erpnext() {
    local max_attempts=40
    local attempt=1

    info "Aguardando ERPNext ficar saudável (até $((max_attempts * 15))s)..."

    while [ $attempt -le $max_attempts ]; do
        if docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" ps backend 2>/dev/null | grep -q "healthy"; then
            success "ERPNext backend está saudável!"
            return 0
        fi
        echo -ne "  Tentativa $attempt/$max_attempts...\r"
        sleep 15
        attempt=$((attempt + 1))
    done

    warn "ERPNext ainda não está saudável. Verifique com: docker compose -f $COMPOSE_DIR/docker-compose.yml ps"
    return 1
}

# ─── Criar site ERPNext ───────────────────────────────────────────────────────
create_erpnext_site() {
    local site_name db_password

    site_name=$(read_env_var "ERPNEXT_SITE_NAME" "mysite.localhost")
    db_password=$(read_env_var "MYSQL_ROOT_PASSWORD" "secret")

    info "Criando site ERPNext: $site_name"

    docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" exec -T backend bench new-site "$site_name" \
        --mariadb-root-password "$db_password" \
        --admin-password admin \
        --install-app erpnext \
        --no-mariadb-socket 2>/dev/null || {
        warn "Site pode já existir. Continuando..."
    }

    success "Site ERPNext configurado."
}

# ─── Instalar app semantic_finance ────────────────────────────────────────────
install_semantic_finance() {
    local site_name
    site_name=$(read_env_var "ERPNEXT_SITE_NAME" "mysite.localhost")

    info "Instalando app semantic_finance..."

    docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" exec -T backend bench get-app /home/frappe/frappe-bench/apps/semantic_finance 2>/dev/null || true
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$ENV_FILE" exec -T backend bench --site "$site_name" install-app semantic_finance 2>/dev/null || {
        warn "App semantic_finance pode já estar instalado ou o diretório não está montado."
        warn "Instale manualmente se necessário."
    }

    success "App semantic_finance processado."
}

# ─── Instruções finais ────────────────────────────────────────────────────────
show_final_instructions() {
    local provider="$1"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║       ERPNext Semantic Finance — Setup Concluído!           ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BLUE}ERPNext:${NC}     http://localhost:8080"
    echo -e "  ${BLUE}MCP Server:${NC}  http://localhost:8000"

    if [ "$provider" = "qdrant" ]; then
        echo -e "  ${BLUE}Qdrant:${NC}      http://localhost:6333/dashboard"
    fi

    echo -e "  ${BLUE}Ollama:${NC}      http://localhost:11434"
    echo ""
    echo -e "  ${YELLOW}Credenciais padrão ERPNext:${NC}"
    echo -e "    Usuário: Administrator"
    echo -e "    Senha:   admin"
    echo ""
    echo -e "  ${YELLOW}Próximos passos:${NC}"
    echo -e "    1. Acesse o ERPNext e configure a empresa"
    echo -e "    2. Gere API Key/Secret em Settings → API Access"
    echo -e "    3. Atualize ERPNEXT_API_KEY e ERPNEXT_API_SECRET no .env"
    echo -e "    4. Reinicie o MCP server: docker restart erpnext-mcp-server"
    echo ""

    if [ "$provider" = "qdrant" ]; then
        echo -e "  ${YELLOW}Indexação de documentos:${NC}"
        echo -e "    python scripts/batch_index.py --doctype 'Payment Entry'"
        echo ""
    fi
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  ERPNext Semantic Finance — Setup Inicial${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    check_prerequisites
    ensure_env_file

    # Detecta provider do .env
    local provider
    provider=$(read_env_var "VECTOR_STORE_PROVIDER" "qdrant")
    provider=$(echo "$provider" | tr '[:upper:]' '[:lower:]')

    info "Vector Store Provider detectado: $provider"

    # Validação específica por provider
    if [ "$provider" = "pinecone" ]; then
        validate_pinecone
    fi

    # Sobe a stack
    start_stack "$provider"

    # Pull do modelo Ollama (para ambos os providers)
    local embedding_provider
    embedding_provider=$(read_env_var "EMBEDDING_PROVIDER" "ollama")
    if [ "$embedding_provider" = "ollama" ]; then
        pull_ollama_model
    fi

    # Aguarda ERPNext
    wait_for_erpnext || true

    # Cria site e instala app
    create_erpnext_site
    install_semantic_finance

    # Instruções finais
    show_final_instructions "$provider"
}

main "$@"
