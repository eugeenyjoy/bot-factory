#!/bin/bash

test_config() {
    MEM=$1
    CPU=$2
    
    echo "=========================================="
    echo "Тест: RAM=$MEM, CPU=$CPU"
    echo "=========================================="
    
    # Перезапуск с новыми лимитами
    docker-compose down 2>/dev/null
    
    docker run -d --rm \
        --name test-bot \
        --memory=$MEM \
        --cpus=$CPU \
        -p 8000:8000 \
        -v $(pwd)/../bots:/app/bots \
        setup_bot-factory
    
    sleep 3
    
    # Проверка что запустился
    if ! docker ps | grep -q test-bot; then
        echo "❌ Не запустился с RAM=$MEM"
        return 1
    fi
    
    # Нагрузка
    echo "Запускаю нагрузку..."
    ab -n 200 -c 10 http://localhost:8000/ 2>/dev/null | grep -E "(Requests per second|Time per request|Failed)"
    
    # Статистика
    echo "Потребление ресурсов:"
    docker stats --no-stream test-bot
    
    # Проверка OOM
    if docker inspect test-bot 2>/dev/null | grep -q '"OOMKilled": true'; then
        echo "❌ OOM Killed — памяти не хватило"
    else
        echo "✅ Работает стабильно"
    fi
    
    docker stop test-bot 2>/dev/null
    echo ""
}

# Тестируем разные конфигурации
test_config "128m" "0.5"
test_config "256m" "0.5"
test_config "256m" "1.0"
test_config "512m" "1.0"
test_config "512m" "2.0"