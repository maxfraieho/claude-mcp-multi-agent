#!/usr/bin/env python3
"""
Multi-Agent Gemini Proxy Server with Advanced Features
Покращений проксі сервер з інтеграцією агентів, load balancing та моніторингом
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
import aiofiles
from dataclasses import dataclass
from collections import deque
import hashlib
import random

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask imports
try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Flask not available: {e}")
    FLASK_AVAILABLE = False

@dataclass
class GeminiToken:
    """Структура для токену Gemini"""
    key: str
    active: bool = True
    priority: int = 1
    last_used: float = 0.0
    usage_count: int = 0
    error_count: int = 0

class GeminiProxyServer:
    def __init__(self, config_path: str = "/app/config/config.yaml"):
        self.config = self.load_config(config_path)
        self.app = self.create_app()
        self.setup_routes()
        
        # Ініціалізуємо компоненти
        self.tokens = self.load_gemini_tokens()
        self.token_rotation = 0
        self.active_sessions = {}
        self.request_history = deque(maxlen=1000)
        self.metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0,
            'start_time': time.time()
        }
        
        # Load balancer для агентів
        self.agent_load_balancer = {
            'qwen': {'connections': 0, 'total_requests': 0, 'avg_response_time': 0.0},
            'gemini': {'connections': 0, 'total_requests': 0, 'avg_response_time': 0.0},
            'claude': {'connections': 0, 'total_requests': 0, 'avg_response_time': 0.0}
        }
        
        # Стартуємо фонові задачі
        asyncio.create_task(self.token_rotation_task())
        asyncio.create_task(self.metrics_collector())
        asyncio.create_task(self.health_checker())
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Завантаження конфігурації"""
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Не вдалося завантажити конфігурацію: {e}")
        
        return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Стандартна конфігурація"""
        return {
            'server': {'host': '0.0.0.0', 'port': 8080},
            'security': {'jwt_secret': 'demo-secret'},
            'cors': {'allowed_origins': ['http://localhost:3000']},
            'rate_limit': {'requests_per_minute': 100},
            'gemini': {'endpoint': 'https://generativelanguage.googleapis.com/v1beta'},
            'agents': {
                'qwen': {'endpoint': 'local'},
                'gemini': {'endpoint': 'local'},
                'claude': {'endpoint': 'local'}
            },
            'monitoring': {'metrics_enabled': True, 'metrics_port': 9090}
        }
    
    def create_app(self):
        """Створення Flask додатку"""
        if not FLASK_AVAILABLE:
            logger.error("Flask недоступний")
            logger.info("Переходимо на async-only режим")
            return None

        app = Flask(__name__)

        # CORS налаштування
        cors_origins = self.config.get('cors', {}).get('allowed_origins', ['*'])
        CORS(app, origins=cors_origins)

        return app
    
    def load_gemini_tokens(self) -> List[GeminiToken]:
        """Завантаження Gemini токенів"""
        tokens = []

        # Спочатку спробуємо завантажити з файлу
        tokens_file = self.config.get('gemini', {}).get('token_rotation', {}).get('tokens_file')
        logger.info(f"Шлях до файлу токенів з конфігурації: {tokens_file}")

        if tokens_file:
            logger.info(f"Перевірка існування файлу: {tokens_file}")
            if os.path.exists(tokens_file):
                logger.info(f"Файл існує, завантажуємо токени...")
                try:
                    with open(tokens_file, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            token_key = line.strip()
                            if token_key and not token_key.startswith('#'):
                                tokens.append(GeminiToken(
                                    key=token_key,
                                    priority=i
                                ))
                                logger.debug(f"Токен {i}: {token_key[:20]}...")
                    logger.info(f"✅ Завантажено {len(tokens)} токенів з файлу {tokens_file}")
                except Exception as e:
                    logger.error(f"Помилка завантаження токенів з файлу: {e}", exc_info=True)
            else:
                logger.warning(f"Файл токенів не існує: {tokens_file}")
        else:
            logger.warning("Шлях до файлу токенів не вказано в конфігурації")

        # Якщо токени не завантажені, використовуємо реальні токени з стандартного розташування
        if not tokens:
            fallback_path = "/app/secrets/gemini_tokens.txt"
            logger.warning(f"Використовуємо fallback шлях: {fallback_path}")
            if os.path.exists(fallback_path):
                try:
                    with open(fallback_path, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            token_key = line.strip()
                            if token_key and not token_key.startswith('#'):
                                tokens.append(GeminiToken(
                                    key=token_key,
                                    priority=i
                                ))
                    logger.info(f"✅ Завантажено {len(tokens)} токенів з fallback файлу")
                except Exception as e:
                    logger.error(f"Помилка завантаження з fallback: {e}")

        if not tokens:
            logger.error("❌ Не вдалося завантажити жодного токена!")

        return tokens
    
    async def token_rotation_task(self):
        """Фонова задача ротації токенів"""
        while True:
            try:
                await asyncio.sleep(30)  # Кожні 30 секунд
                
                # Перевіряємо стан токенів
                for token in self.tokens:
                    if token.error_count > 5:  # Якщо занадто багато помилок
                        token.active = False
                        logger.warning(f"Токен деактивовано через помилки: {token.key[:10]}...")
                
                # Якщо всі токени неактивні, спробуємо реактивувати їх
                if not any(token.active for token in self.tokens):
                    logger.warning("Всі токени неактивні, реактивуємо їх")
                    for token in self.tokens:
                        token.active = True
                        token.error_count = 0
                
            except Exception as e:
                logger.error(f"Помилка в token rotation task: {e}")
    
    async def metrics_collector(self):
        """Збір метрик"""
        while True:
            try:
                await asyncio.sleep(60)  # Кожну хвилину
                
                metrics_data = {
                    'timestamp': datetime.now().isoformat(),
                    'server_metrics': self.metrics.copy(),
                    'agents_metrics': self.agent_load_balancer.copy(),
                    'tokens_status': [
                        {
                            'key_prefix': token.key[:10] + '...',
                            'active': token.active,
                            'usage_count': token.usage_count,
                            'error_count': token.error_count,
                            'priority': token.priority
                        }
                        for token in self.tokens
                    ],
                    'active_sessions': len(self.active_sessions)
                }
                
                # Зберігаємо метрики
                metrics_file = '/app/data/proxy_metrics.json'
                os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
                
                async with aiofiles.open(metrics_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(metrics_data, ensure_ascii=False, indent=2))
                
            except Exception as e:
                logger.error(f"Помилка збору метрик: {e}")
    
    async def health_checker(self):
        """Перевірка здоров'я агентів"""
        while True:
            try:
                await asyncio.sleep(60)  # Кожну хвилину
                
                # Перевіряємо локальні агенти
                for agent_type in ['qwen', 'gemini', 'claude']:
                    try:
                        # Простий health check
                        result = await self.check_local_agent_health(agent_type)
                        self.agent_load_balancer[agent_type]['healthy'] = result
                        
                    except Exception as e:
                        logger.warning(f"Health check failed for {agent_type}: {e}")
                        self.agent_load_balancer[agent_type]['healthy'] = False
                
            except Exception as e:
                logger.error(f"Помилка health checker: {e}")
    
    async def check_local_agent_health(self, agent_type: str) -> bool:
        """Перевірка здоров'я локального агента"""
        try:
            if agent_type == 'qwen':
                process = await asyncio.create_subprocess_exec(
                    'which', 'qwen-cli',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            elif agent_type == 'gemini':
                process = await asyncio.create_subprocess_exec(
                    'which', 'gemini-cli',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            elif agent_type == 'claude':
                # Перевіряємо через MCP server
                process = await asyncio.create_subprocess_exec(
                    'node', '--version',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                return False
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            return process.returncode == 0
            
        except Exception:
            return False
    
    def get_next_token(self) -> Optional[GeminiToken]:
        """Отримання наступного активного токену"""
        active_tokens = [t for t in self.tokens if t.active]
        if not active_tokens:
            return None
        
        # Round-robin з урахуванням пріоритету
        start_idx = self.token_rotation % len(active_tokens)
        selected_token = active_tokens[start_idx]
        self.token_rotation = (self.token_rotation + 1) % len(active_tokens)
        
        # Оновлюємо статистику
        selected_token.usage_count += 1
        selected_token.last_used = time.time()
        
        return selected_token
    
    async def call_gemini_api(self, prompt: str, model: str = 'gemini-pro', **params) -> str:
        """Виклик Gemini API"""
        token = self.get_next_token()
        if not token:
            raise Exception("Немає доступних токенів")

        # Підготовка запиту до Gemini API
        endpoint = self.config.get('gemini', {}).get('endpoint', 'https://generativelanguage.googleapis.com/v1beta')
        timeout = self.config.get('gemini', {}).get('timeout', 60)

        api_url = f"{endpoint}/models/{model}:generateContent?key={token.key}"

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Gemini API error {response.status}: {error_text}")

                    result = await response.json()

                    # Витягуємо текст з відповіді
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            parts = candidate['content']['parts']
                            if len(parts) > 0 and 'text' in parts[0]:
                                response_text = parts[0]['text']
                                token.last_used = time.time()
                                token.usage_count += 1
                                return response_text

                    raise Exception("Некоректна відповідь від Gemini API")

        except Exception as e:
            token.error_count += 1
            logger.error(f"Помилка Gemini API: {e}")
            raise
    
    async def delegate_to_agent(self, agent_type: str, task: str, **parameters) -> Dict[str, Any]:
        """Делегування завдання агенту"""
        start_time = time.time()
        
        try:
            # Вибираємо агента через load balancer
            if agent_type not in self.agent_load_balancer:
                raise ValueError(f"Невідомий тип агента: {agent_type}")
            
            self.agent_load_balancer[agent_type]['connections'] += 1
            
            if agent_type == 'gemini':
                # Використовуємо Gemini API
                result = await self.call_gemini_api(task, **parameters)
                agent_name = "Gemini API"
            else:
                # Симуляція інших агентів
                await asyncio.sleep(0.2)  # Симуляція роботи агента
                result = f"Результат від {agent_type} агента для завдання: {task[:50]}..."
                agent_name = f"{agent_type.title()} Agent"
            
            execution_time = time.time() - start_time
            
            # Оновлюємо статистику load balancer
            lb_data = self.agent_load_balancer[agent_type]
            lb_data['connections'] -= 1
            lb_data['total_requests'] += 1
            lb_data['avg_response_time'] = (
                (lb_data['avg_response_time'] * (lb_data['total_requests'] - 1) + execution_time) 
                / lb_data['total_requests']
            )
            
            return {
                'success': True,
                'agent': agent_name,
                'agent_type': agent_type,
                'result': result,
                'execution_time': execution_time,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.agent_load_balancer[agent_type]['connections'] -= 1
            
            return {
                'success': False,
                'agent_type': agent_type,
                'error': str(e),
                'execution_time': execution_time,
                'timestamp': datetime.now().isoformat()
            }
    
    def setup_routes(self):
        """Налаштування маршрутів"""
        if not self.app:
            return
        
        app = self.app
        
        @app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'version': '2.0.0',
                'metrics': {
                    'total_requests': self.metrics['total_requests'],
                    'uptime_seconds': time.time() - self.metrics['start_time'],
                    'active_tokens': len([t for t in self.tokens if t.active]),
                    'active_sessions': len(self.active_sessions)
                }
            })
        
        @app.route('/api/gemini/generate', methods=['POST'])
        async def generate_text():
            """Генерація тексту через Gemini"""
            data = request.get_json()
            if not data or 'prompt' not in data:
                return jsonify({'error': 'Потрібен prompt'}), 400
            
            prompt = data['prompt']
            model = data.get('model', 'gemini-pro')
            
            start_time = time.time()
            self.metrics['total_requests'] += 1
            
            try:
                result = await self.call_gemini_api(prompt, model)
                execution_time = time.time() - start_time
                
                self.metrics['successful_requests'] += 1
                self.update_response_time(execution_time)
                
                return jsonify({
                    'text': result,
                    'model': model,
                    'execution_time': execution_time,
                    'timestamp': datetime.now().isoformat(),
                    'metadata': {
                        'tokens_used': len([t for t in self.tokens if t.last_used > start_time - 60])
                    }
                })
                
            except Exception as e:
                execution_time = time.time() - start_time
                self.metrics['failed_requests'] += 1
                
                return jsonify({
                    'error': str(e),
                    'execution_time': execution_time,
                    'timestamp': datetime.now().isoformat()
                }), 500
        
        
        @app.route('/v1/chat/completions', methods=['POST'])
        async def openai_chat_completions():
            """OpenAI-compatible chat completions endpoint"""
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request body is required'}), 400
            
            # Витягуємо параметри з OpenAI формату
            model = data.get('model', 'gemini-2.0-flash-exp')
            messages = data.get('messages', [])
            max_tokens = data.get('max_tokens', 2048)
            temperature = data.get('temperature', 0.7)
            
            if not messages:
                return jsonify({'error': 'messages array is required'}), 400
            
            # Конвертуємо messages в один prompt для Gemini
            # Gemini очікує просто текст, тому об'єднуємо всі повідомлення
            prompt_parts = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'system':
                    prompt_parts.append(f"System: {content}")
                elif role == 'user':
                    prompt_parts.append(f"User: {content}")
                elif role == 'assistant':
                    prompt_parts.append(f"Assistant: {content}")
                else:
                    prompt_parts.append(content)
            
            prompt = "\n".join(prompt_parts)
            
            # Виконуємо запит
            start_time = time.time()
            self.metrics['total_requests'] += 1
            
            try:
                # Викликаємо існуючий метод call_gemini_api
                result = await self.call_gemini_api(prompt, model=model)
                execution_time = time.time() - start_time
                
                self.metrics['successful_requests'] += 1
                self.update_response_time(execution_time)
                
                # Формуємо відповідь у OpenAI форматі
                response_id = f"chatcmpl-{hashlib.md5(str(time.time()).encode()).hexdigest()[:10]}"
                
                openai_response = {
                    "id": response_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": len(result.split()),
                        "total_tokens": len(prompt.split()) + len(result.split())
                    }
                }
                
                return jsonify(openai_response)
                
            except Exception as e:
                execution_time = time.time() - start_time
                self.metrics['failed_requests'] += 1
                
                # OpenAI error format
                return jsonify({
                    "error": {
                        "message": str(e),
                        "type": "server_error",
                        "param": None,
                        "code": None
                    }
                }), 500
        
        @app.route('/api/agents/delegate', methods=['POST'])
        async def delegate_to_agent_route():
            """Делегування завдання агенту"""
            data = request.get_json()
            if not data or 'agent_type' not in data or 'task' not in data:
                return jsonify({'error': 'Потрібні agent_type та task'}), 400
            
            agent_type = data['agent_type']
            task = data['task']
            parameters = data.get('parameters', {})
            
            result = await self.delegate_to_agent(agent_type, task, **parameters)
            
            if result['success']:
                return jsonify(result)
            else:
                return jsonify(result), 500
        
        @app.route('/api/agents/status', methods=['GET'])
        def get_agents_status():
            """Статус агентів"""
            status = {}
            for agent_type, data in self.agent_load_balancer.items():
                status[agent_type] = {
                    'healthy': data.get('healthy', True),
                    'active_connections': data['connections'],
                    'total_requests': data['total_requests'],
                    'avg_response_time': data['avg_response_time']
                }
            
            return jsonify({
                'agents': status,
                'timestamp': datetime.now().isoformat()
            })
        
        @app.route('/api/system/status', methods=['GET'])
        def get_system_status():
            """Загальний статус системи"""
            return jsonify({
                'server': {
                    'status': 'running',
                    'uptime_seconds': time.time() - self.metrics['start_time'],
                    'total_requests': self.metrics['total_requests'],
                    'success_rate': self.metrics['successful_requests'] / max(1, self.metrics['total_requests']),
                    'avg_response_time': self.metrics['avg_response_time']
                },
                'agents': self.agent_load_balancer,
                'tokens': {
                    'total': len(self.tokens),
                    'active': len([t for t in self.tokens if t.active]),
                    'inactive': len([t for t in self.tokens if not t.active])
                },
                'sessions': {
                    'active': len(self.active_sessions)
                },
                'timestamp': datetime.now().isoformat()
            })
        
        @app.route('/metrics', methods=['GET'])
        def get_metrics():
            """Prometheus-compatible metrics"""
            uptime = time.time() - self.metrics['start_time']
            success_rate = self.metrics['successful_requests'] / max(1, self.metrics['total_requests'])
            
            metrics_text = f"""# HELP gemini_proxy_requests_total Total number of requests
# TYPE gemini_proxy_requests_total counter
gemini_proxy_requests_total {self.metrics['total_requests']}

# HELP gemini_proxy_requests_successful Total number of successful requests
# TYPE gemini_proxy_requests_successful counter
gemini_proxy_requests_successful {self.metrics['successful_requests']}

# HELP gemini_proxy_requests_failed Total number of failed requests
# TYPE gemini_proxy_requests_failed counter
gemini_proxy_requests_failed {self.metrics['failed_requests']}

# HELP gemini_proxy_uptime_seconds Server uptime in seconds
# TYPE gemini_proxy_uptime_seconds counter
gemini_proxy_uptime_seconds {uptime}

# HELP gemini_proxy_success_rate Success rate (0-1)
# TYPE gemini_proxy_success_rate gauge
gemini_proxy_success_rate {success_rate}

# HELP gemini_proxy_avg_response_time Average response time in seconds
# TYPE gemini_proxy_avg_response_time gauge
gemini_proxy_avg_response_time {self.metrics['avg_response_time']}

# HELP gemini_proxy_active_tokens Number of active tokens
# TYPE gemini_proxy_active_tokens gauge
gemini_proxy_active_tokens {len([t for t in self.tokens if t.active])}

# HELP gemini_proxy_active_connections Number of active connections
# TYPE gemini_proxy_active_connections gauge
gemini_proxy_active_connections {sum(d['connections'] for d in self.agent_load_balancer.values())}
"""
            
            return metrics_text, 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}
    
    def update_response_time(self, response_time: float):
        """Оновлення середнього часу відповіді"""
        total_requests = self.metrics['total_requests']
        current_avg = self.metrics['avg_response_time']
        
        self.metrics['avg_response_time'] = (
            (current_avg * (total_requests - 1) + response_time) / total_requests
        )
    
    def run(self):
        """Запуск сервера"""
        if not self.app:
            logger.error("Flask додаток не створено")
            return
        
        host = self.config['server']['host']
        port = self.config['server']['port']
        
        logger.info(f"🚀 Запуск Multi-Agent Gemini Proxy Server на {host}:{port}")
        
        try:
            # Запуск через Gunicorn
            from gunicorn.app.wsgiapp import WSGIApplication
            
            class StandaloneApplication(WSGIApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()
                
                def load_config(self):
                    config = {
                        key: value for key, value in self.options.items()
                        if key in self.cfg.settings and value is not None
                    }
                    for key, value in config.items():
                        self.cfg.set(key.lower(), value)
                
                def load(self):
                    return self.application
            
            options = {
                'bind': f'{host}:{port}',
                'workers': 4,
                'worker_class': 'sync',
                'timeout': 60,
                'max_requests': 1000,
                'max_requests_jitter': 50,
                'preload_app': True,
                'accesslog': '/app/logs/gemini_proxy_access.log',
                'errorlog': '/app/logs/gemini_proxy_error.log',
                'loglevel': 'info'
            }
            
            StandaloneApplication(self.app, options).run()
            
        except Exception as e:
            logger.error(f"Помилка запуску сервера: {e}")
            # Fallback до простого запуску
            logger.info("Запуск через вбудований сервер Flask...")
            self.app.run(host=host, port=port, debug=False)

# CLI інтерфейс
async def main():
    """Головна функція"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Multi-Agent Gemini Proxy Server')
    parser.add_argument('--config', default='/app/config/config.yaml',
                       help='Шлях до конфігураційного файлу')
    parser.add_argument('--host', default='0.0.0.0', help='Хост для прив\'язки')
    parser.add_argument('--port', type=int, default=8080, help='Порт для прив\'язки')
    
    args = parser.parse_args()
    
    # Створюємо сервер
    server = GeminiProxyServer(args.config)
    
    # Оновлюємо конфігурацію
    server.config['server']['host'] = args.host
    server.config['server']['port'] = args.port
    
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("🛑 Сервер зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())