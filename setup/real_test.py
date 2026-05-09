import asyncio
import aiohttp
import time

BASE_URL = "http://localhost:8000"

async def test_api():
    async with aiohttp.ClientSession() as session:
        
        # 1. Получить список ботов
        async with session.get(f"{BASE_URL}/api/bots") as r:
            print(f"GET /api/bots: {r.status}")
            if r.status == 200:
                bots = await r.json()
                print(f"   Найдено ботов: {len(bots) if isinstance(bots, list) else bots}")
        
        # 2. Получить список моделей
        async with session.get(f"{BASE_URL}/api/models") as r:
            print(f"GET /api/models: {r.status}")
        
        # 3. Получить провайдеров
        async with session.get(f"{BASE_URL}/api/providers") as r:
            print(f"GET /api/providers: {r.status}")
        
        # 4. Главная страница
        async with session.get(f"{BASE_URL}/") as r:
            print(f"GET /: {r.status}")

async def load_test(num_users=10, requests_per_user=20):
    """Симуляция нескольких пользователей"""
    
    async def user_session(user_id):
        async with aiohttp.ClientSession() as session:
            for i in range(requests_per_user):
                # Случайные запросы к разным эндпоинтам
                endpoints = [
                    "/api/bots",
                    "/api/models", 
                    "/api/providers",
                    "/",
                ]
                for endpoint in endpoints:
                    try:
                        async with session.get(f"{BASE_URL}{endpoint}") as r:
                            pass  # Просто делаем запрос
                    except Exception as e:
                        print(f"Ошибка: {e}")
    
    print(f"\nЗапускаю нагрузку: {num_users} пользователей x {requests_per_user} итераций")
    print(f"Всего запросов: {num_users * requests_per_user * 4}")
    print("Смотри docker stats в другом терминале!\n")
    
    start = time.time()
    
    tasks = [user_session(i) for i in range(num_users)]
    await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    total_requests = num_users * requests_per_user * 4
    
    print(f"\nГотово!")
    print(f"Время: {elapsed:.2f} сек")
    print(f"RPS: {total_requests / elapsed:.1f} запросов/сек")

async def main():
    print("=== Проверка API ===\n")
    await test_api()
    
    print("\n=== Нагрузочный тест ===")
    await load_test(num_users=50, requests_per_user=50)

if __name__ == "__main__":
    asyncio.run(main())