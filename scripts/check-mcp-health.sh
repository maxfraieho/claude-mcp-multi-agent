#!/bin/bash
# Перевірка здоров'я Multi-Agent MCP системи

echo "🔍 Перевірка Multi-Agent MCP System Health..."
echo ""

# Кольори для виводу
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функція перевірки сервісу
check_service() {
    local name=$1
    local port=$2
    local endpoint=$3

    if curl -sf "http://localhost:${port}${endpoint}" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ ${name}${NC} - Running on port ${port}"
        return 0
    else
        echo -e "${RED}❌ ${name}${NC} - Not accessible on port ${port}"
        return 1
    fi
}

# Функція перевірки Docker контейнера
check_container() {
    local name=$1

    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        local status=$(docker inspect --format='{{.State.Health.Status}}' ${name} 2>/dev/null || echo "no-health")
        if [ "$status" = "healthy" ]; then
            echo -e "${GREEN}✅ ${name}${NC} - Container healthy"
        elif [ "$status" = "no-health" ]; then
            echo -e "${YELLOW}⚠️  ${name}${NC} - Container running (no health check)"
        else
            echo -e "${YELLOW}⚠️  ${name}${NC} - Container status: ${status}"
        fi
        return 0
    else
        echo -e "${RED}❌ ${name}${NC} - Container not running"
        return 1
    fi
}

echo "📦 Docker Containers:"
echo "-------------------"
check_container "vibe-kanban"
check_container "gemini-proxy"
check_container "postgres"
check_container "redis"
check_container "vault"
check_container "grafana"
check_container "prometheus"
echo ""

echo "🌐 Service Endpoints:"
echo "--------------------"
check_service "Vibe Kanban" "3001" "/"
check_service "Gemini Proxy" "8080" "/health"
check_service "Grafana" "3000" "/api/health"
check_service "Prometheus" "9091" "/-/healthy"
check_service "Vault" "8200" "/v1/sys/health"
check_service "PostgreSQL" "5432" "" 2>/dev/null && echo -e "${GREEN}✅ PostgreSQL${NC} - Running on port 5432" || echo -e "${YELLOW}⚠️  PostgreSQL${NC} - Port check not available (use psql to verify)"
echo ""

echo "🤖 MCP Configuration:"
echo "--------------------"
if [ -f "/home/vokov/multi-agent-dev-system/agent-dev/vibe-kanban/.mcp.json" ]; then
    echo -e "${GREEN}✅ .mcp.json${NC} - Configuration file exists"

    # Перевірка executors
    executors=$(cat /home/vokov/multi-agent-dev-system/agent-dev/vibe-kanban/.mcp.json | grep -c '"type"')
    echo -e "${GREEN}   ${executors} executors configured${NC}"
else
    echo -e "${RED}❌ .mcp.json${NC} - Configuration file missing"
fi
echo ""

echo "📊 Quick Stats:"
echo "--------------"
echo "Docker containers running: $(docker ps | wc -l) / $(docker ps -a | wc -l) total"
echo "Gemini Proxy uptime: $(curl -s http://localhost:8080/health 2>/dev/null | grep -o '"uptime_seconds":[0-9.]*' | cut -d: -f2 | xargs printf "%.0f seconds\n" 2>/dev/null || echo "N/A")"
echo ""

echo "🔗 Quick Links:"
echo "--------------"
echo "Vibe Kanban:  http://localhost:3001"
echo "Grafana:      http://localhost:3000 (admin/admin)"
echo "Prometheus:   http://localhost:9091"
echo "Gemini Proxy: http://localhost:8080/health"
echo ""

echo "✨ System check complete!"
