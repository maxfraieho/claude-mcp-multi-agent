#!/bin/bash
# Швидке налаштування Vibe Kanban для роботи з MCP

set -e  # Exit on error

echo "🚀 Vibe Kanban MCP Setup Script"
echo "================================"
echo ""

# Кольори
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_DIR="/home/vokov/multi-agent-dev-system/agent-dev"
VIBE_DIR="${BASE_DIR}/vibe-kanban"
MCP_CONFIG="${BASE_DIR}/vibe-kanban-mcp-config.json"

# Крок 1: Перевірка передумов
echo -e "${BLUE}📋 Крок 1: Перевірка передумов${NC}"
echo "----------------------------"

# Перевірка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠️  Docker не знайдено. Встановіть Docker спочатку.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker встановлено${NC}"

# Перевірка docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}⚠️  docker-compose не знайдено. Встановіть docker-compose спочатку.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ docker-compose встановлено${NC}"

echo ""

# Крок 2: Перевірка запущених сервісів
echo -e "${BLUE}📦 Крок 2: Перевірка сервісів${NC}"
echo "----------------------------"

required_services=("vibe-kanban" "gemini-proxy" "postgres" "redis")
missing_services=()

for service in "${required_services[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
        echo -e "${GREEN}✅ ${service} запущено${NC}"
    else
        echo -e "${YELLOW}⚠️  ${service} не запущено${NC}"
        missing_services+=("$service")
    fi
done

if [ ${#missing_services[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Деякі сервіси не запущені. Запустити їх зараз? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Запуск сервісів через docker-compose..."
        cd "${BASE_DIR}"
        docker-compose -f docker-compose-production.yml up -d
        echo -e "${GREEN}✅ Сервіси запущено${NC}"
    else
        echo -e "${YELLOW}⚠️  Продовжуємо без запуску сервісів${NC}"
    fi
fi

echo ""

# Крок 3: Копіювання MCP конфігурації
echo -e "${BLUE}🔧 Крок 3: Налаштування MCP конфігурації${NC}"
echo "--------------------------------------"

if [ ! -f "$MCP_CONFIG" ]; then
    echo -e "${YELLOW}⚠️  Файл конфігурації не знайдено: ${MCP_CONFIG}${NC}"
    exit 1
fi

if [ ! -d "$VIBE_DIR" ]; then
    echo -e "${YELLOW}⚠️  Vibe Kanban директорія не знайдена: ${VIBE_DIR}${NC}"
    echo "Створюємо директорію..."
    mkdir -p "$VIBE_DIR"
fi

# Копіюємо конфігурацію
cp "$MCP_CONFIG" "${VIBE_DIR}/.mcp.json"
echo -e "${GREEN}✅ MCP конфігурація скопійована до ${VIBE_DIR}/.mcp.json${NC}"

# Показуємо налаштовані executors
echo ""
echo "Налаштовані AI агенти (executors):"
grep -o '"name": "[^"]*"' "${VIBE_DIR}/.mcp.json" | sed 's/"name": "//;s/"$//' | while read -r name; do
    echo "  • ${name}"
done

echo ""

# Крок 4: Перезапуск Vibe Kanban
echo -e "${BLUE}🔄 Крок 4: Перезапуск Vibe Kanban${NC}"
echo "--------------------------------"

if docker ps --format '{{.Names}}' | grep -q "^vibe-kanban$"; then
    echo "Перезапускаємо Vibe Kanban для застосування змін..."
    docker restart vibe-kanban

    # Чекаємо поки контейнер стане healthy
    echo "Очікування готовності контейнера..."
    for i in {1..30}; do
        if docker inspect --format='{{.State.Health.Status}}' vibe-kanban 2>/dev/null | grep -q "healthy"; then
            echo -e "${GREEN}✅ Vibe Kanban готовий до роботи${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""
else
    echo -e "${YELLOW}⚠️  Vibe Kanban не запущено. Запустіть вручну:${NC}"
    echo "   docker-compose -f docker-compose-production.yml up -d vibe-kanban"
fi

echo ""

# Крок 5: Перевірка здоров'я системи
echo -e "${BLUE}🏥 Крок 5: Перевірка здоров'я системи${NC}"
echo "-----------------------------------"

# Перевірка Vibe Kanban
if curl -sf http://localhost:3001 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Vibe Kanban доступний на http://localhost:3001${NC}"
else
    echo -e "${YELLOW}⚠️  Vibe Kanban ще не доступний${NC}"
fi

# Перевірка Gemini Proxy
if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Gemini Proxy працює${NC}"
else
    echo -e "${YELLOW}⚠️  Gemini Proxy недоступний${NC}"
fi

echo ""

# Підсумок
echo "================================"
echo -e "${GREEN}✨ Налаштування завершено!${NC}"
echo "================================"
echo ""
echo "📚 Наступні кроки:"
echo "  1. Відкрийте http://localhost:3001 в браузері"
echo "  2. Увійдіть через GitHub OAuth"
echo "  3. Створіть новий проект"
echo "  4. Додайте задачу та виберіть AI агента"
echo ""
echo "📖 Детальна інструкція:"
echo "  ${BASE_DIR}/VIBE_KANBAN_MCP_SETUP.md"
echo ""
echo "🔍 Перевірка системи:"
echo "  ${BASE_DIR}/scripts/check-mcp-health.sh"
echo ""
echo "🎯 Доступні AI агенти:"
echo "  • 🎭 Claude Code Orchestrator (рекомендовано)"
echo "  • ⚡ Gemini Flash 2.0"
echo "  • 🧠 Gemini Flash Thinking"
echo "  • 📚 Gemini Pro 1.5"
echo "  • 💻 Qwen 2.5 Coder (SSH)"
echo ""
echo "Успішної роботи! 🚀"
