# ⚡ Quick Start - Multi-Agent Development System

## 🎯 Швидкий старт за 5 хвилин

### 1. Запустіть всі сервіси

```bash
cd /home/vokov/multi-agent-dev-system/agent-dev
docker-compose -f docker-compose-production.yml up -d
```

### 2. Налаштуйте Vibe Kanban для MCP

```bash
./scripts/setup-vibe-kanban-mcp.sh
```

### 3. Перевірте систему

```bash
./scripts/check-mcp-health.sh
```

### 4. Відкрийте Vibe Kanban

```
http://localhost:3001
```

---

## 📚 Що далі?

### Для повної інструкції:
👉 [VIBE_KANBAN_MCP_SETUP.md](./VIBE_KANBAN_MCP_SETUP.md)

### Основні ендпоінти:
- **Vibe Kanban:** http://localhost:3001
- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9091
- **Gemini Proxy:** http://localhost:8080

---

## 🤖 Доступні AI Агенти

| Агент | Використовуй для | Модель |
|-------|------------------|--------|
| 🎭 Claude Code Orchestrator | Складні multi-step задачі, оркестрація | MCP |
| ⚡ Gemini Flash 2.0 | Швидкий coding, рефакторинг | gemini-2.0-flash-exp |
| 🧠 Gemini Flash Thinking | Складні алгоритми, debugging | gemini-2.0-flash-thinking |
| 📚 Gemini Pro 1.5 | Великий контекст, документація | gemini-1.5-pro |
| 💻 Qwen 2.5 Coder | Спеціалізований coding | qwen-2.5-coder-32b |

---

## 🛠️ Корисні команди

### Перезапуск сервісів
```bash
docker-compose -f docker-compose-production.yml restart
```

### Перегляд логів
```bash
# Всі сервіси
docker-compose -f docker-compose-production.yml logs -f

# Конкретний сервіс
docker logs -f vibe-kanban
docker logs -f gemini-proxy
```

### Зупинка системи
```bash
docker-compose -f docker-compose-production.yml down
```

### Повна очистка (ОБЕРЕЖНО!)
```bash
docker-compose -f docker-compose-production.yml down -v
```

---

## 🔍 Troubleshooting

### Vibe Kanban не запускається
```bash
docker logs vibe-kanban
docker restart vibe-kanban
```

### Gemini Proxy не працює
```bash
curl http://localhost:8080/health
docker logs gemini-proxy
```

### MCP конфігурація не застосувалась
```bash
./scripts/setup-vibe-kanban-mcp.sh
docker restart vibe-kanban
```

---

## 📖 Документація

- [Повна інструкція Vibe Kanban](./VIBE_KANBAN_MCP_SETUP.md)
- [Конфігурація системи](./config.yaml)
- [MCP конфігурація](./vibe-kanban-mcp-config.json)
- [GitHub репозиторій](https://github.com/maxfraieho/claude-mcp-multi-agent)

---

**Готово! Починайте роботу з AI агентами через Vibe Kanban! 🚀**
