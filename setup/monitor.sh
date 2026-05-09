#!/bin/bash

CONTAINER="setup_bot-factory_1"
LOG_FILE="stats_log.csv"

# Заголовок
echo "timestamp,cpu_percent,mem_usage_mb,mem_limit_mb,mem_percent" > $LOG_FILE

echo "Записываю статистику в $LOG_FILE"
echo "Нажми Ctrl+C чтобы остановить"
echo ""

while true; do
    STATS=$(docker stats --no-stream --format "{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" $CONTAINER 2>/dev/null)
    
    if [ -n "$STATS" ]; then
        # Парсим память (из "66.5MiB / 512MiB" → 66.5,512)
        CPU=$(echo $STATS | cut -d',' -f1 | tr -d '%')
        MEM_USAGE=$(echo $STATS | cut -d',' -f2 | cut -d'/' -f1 | tr -d ' MiB')
        MEM_LIMIT=$(echo $STATS | cut -d',' -f2 | cut -d'/' -f2 | tr -d ' MiB')
        MEM_PCT=$(echo $STATS | cut -d',' -f3 | tr -d '%')
        
        TIMESTAMP=$(date +%H:%M:%S)
        
        echo "$TIMESTAMP,$CPU,$MEM_USAGE,$MEM_LIMIT,$MEM_PCT" >> $LOG_FILE
        echo "$TIMESTAMP | CPU: ${CPU}% | RAM: ${MEM_USAGE}MB / ${MEM_LIMIT}MB (${MEM_PCT}%)"
    fi
    
    sleep 1
done