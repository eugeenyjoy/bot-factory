"""
Движок — управляет ботами
Веб-чат работает всегда, Telegram подключается опционально
"""

import asyncio
import threading
import logging
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice
from aiogram.filters import Command

from core.brain import Brain
from core.config import load_config, save_config, list_bots

# логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine")


class TelegramRunner:
    """Telegram-часть бота (опциональная)"""

    def __init__(self, config: dict, brain: Brain):
        self.config = config
        self.brain = brain
        self.bot_id = config["bot_id"]

        # aiogram бот и диспетчер
        self.bot = Bot(token=config["bot_token"])
        self.dp = Dispatcher()

        # поток
        self.thread = None
        self.loop = None
        self.is_running = False

        # хэндлеры
        self._register_handlers()

    def _register_handlers(self):
        """Регистрация Telegram обработчиков"""

        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            name = self.config["name"]
            await message.answer(
                f"Привет! Я {name} 👋\n\n"
                f"Просто напиши мне что угодно.\n\n"
                f"Команды:\n"
                f"/reset — очистить историю\n"
                f"/balance — сколько сообщений осталось\n"
                f"/buy — купить сообщения"
            )

        @self.dp.message(Command("reset"))
        async def cmd_reset(message: Message):
            self.brain.clear_chat(message.chat.id)
            await message.answer("🗑️ История очищена. Начнём сначала!")

        @self.dp.message(Command("balance"))
        async def cmd_balance(message: Message):
            remaining = self.brain.memory.get_remaining(
                message.from_user.id,
                self.brain.free_messages
            )
            user = self.brain.memory.get_or_create_user(message.from_user.id)

            if user["is_vip"]:
                await message.answer("👑 У тебя VIP — безлимит!")
            else:
                await message.answer(
                    f"📊 Осталось сообщений: {remaining}\n"
                    f"Использовано: {user['messages_used']}\n"
                    f"Куплено: {user['messages_bought']}\n\n"
                    f"/buy — купить ещё"
                )

        @self.dp.message(Command("buy"))
        async def cmd_buy(message: Message):
            price = self.config["stars_price"]
            msgs = self.config["messages_per_purchase"]
            await message.answer_invoice(
                title=f"📦 {msgs} сообщений",
                description=f"Пакет из {msgs} сообщений для {self.config['name']}",
                payload=f"buy_{msgs}",
                currency="XTR",
                prices=[LabeledPrice(label="Сообщения", amount=price)]
            )

        @self.dp.pre_checkout_query()
        async def pre_checkout(query: PreCheckoutQuery):
            await query.answer(ok=True)

        @self.dp.message(F.successful_payment)
        async def on_payment(message: Message):
            price = message.successful_payment.total_amount
            msgs = self.config["messages_per_purchase"]
            self.brain.add_purchased(
                user_id=message.from_user.id,
                messages=msgs,
                amount=price,
                source="telegram"
            )
            remaining = self.brain.memory.get_remaining(
                message.from_user.id,
                self.brain.free_messages
            )
            await message.answer(
                f"✅ Оплачено! +{msgs} сообщений\n"
                f"Баланс: {remaining} сообщений"
            )

        @self.dp.message(F.text)
        async def on_message(message: Message):
            # в группе реагируем только если упомянули или ответили
            if message.chat.type != "private":
                if not self.config.get("enable_groups", False):
                    return
                bot_info = await self.bot.get_me()
                bot_username = f"@{bot_info.username}"
                is_reply_to_bot = (
                    message.reply_to_message and
                    message.reply_to_message.from_user and
                    message.reply_to_message.from_user.id == bot_info.id
                )
                is_mention = bot_username.lower() in message.text.lower()
                if not is_reply_to_bot and not is_mention:
                    return

            result = self.brain.chat(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                message=message.text,
                user_name=message.from_user.first_name
            )

            if result["ok"]:
                await message.answer(result["reply"])
            elif result["error"] == "limit":
                price = self.config["stars_price"]
                msgs = self.config["messages_per_purchase"]
                remaining = result.get("remaining", 0)
                await message.answer(
                    f"📭 Лимит сообщений исчерпан!\n\n"
                    f"Осталось: {remaining}\n\n"
                    f"💎 Купить {msgs} сообщений за {price} ⭐:\n"
                    f"/buy — оплатить через Telegram Stars"
                )
            else:
                logger.error(f"Bot {self.bot_id} error: {result['error']}")
                await message.answer("⚠️ Ошибка. Попробуй ещё раз.")

    def start(self):
        """Запускает Telegram polling в отдельном потоке"""
        if self.is_running:
            return

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.is_running = True
            logger.info(f"🔵 Telegram started for bot {self.bot_id}")
            try:
                self.loop.run_until_complete(self.dp.start_polling(self.bot))
            except Exception as e:
                logger.error(f"Telegram bot {self.bot_id} crashed: {e}")
            finally:
                self.is_running = False

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        """Останавливает Telegram polling"""
        if not self.is_running:
            return
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.dp.stop_polling(), self.loop
            )
        self.is_running = False
        logger.info(f"🔴 Telegram stopped for bot {self.bot_id}")


class BotInstance:
    """Один бот — мозг всегда работает, Telegram опционально"""

    def __init__(self, config: dict):
        self.config = config
        self.bot_id = config["bot_id"]

        # мозг — ВСЕГДА работает
        self.brain = Brain(
            bot_id=self.bot_id,
            api_key=config["api_key"],
            model=config["model"],
            system_prompt=config["system_prompt"],
            max_history=config["max_history"],
            free_messages=config["free_messages"],
            rag_top_k=config.get("rag_top_k", 3),
        )

        # telegram — ОПЦИОНАЛЬНО
        self.telegram = None

    def start_telegram(self) -> bool:
        """Подключает Telegram"""
        if not self.config.get("bot_token"):
            logger.warning(f"Bot {self.bot_id}: no telegram token")
            return False

        if self.telegram and self.telegram.is_running:
            return True

        self.telegram = TelegramRunner(self.config, self.brain)
        self.telegram.start()
        return True

    def stop_telegram(self):
        """Отключает Telegram"""
        if self.telegram:
            self.telegram.stop()
            self.telegram = None

    def reload_config(self, config: dict):
        """Обновляет настройки"""
        self.config = config
        self.brain.update_model(config["model"])
        self.brain.update_prompt(config["system_prompt"])
        self.brain.update_free_limit(config["free_messages"])
        self.brain.update_max_history(config["max_history"])
        logger.info(f"♻️ Bot {self.bot_id} config reloaded")


class Engine:
    """Управляет всеми ботами"""

    def __init__(self):
        self.instances: Dict[str, BotInstance] = {}

    def activate_bot(self, bot_id: str) -> bool:
        """Активирует бота (мозг работает, веб-чат доступен)"""
        if bot_id in self.instances:
            return True

        config = load_config(bot_id)
        if not config:
            logger.error(f"Config not found: {bot_id}")
            return False

        if not config.get("api_key"):
            logger.error(f"Bot {bot_id}: no api_key")
            return False

        instance = BotInstance(config)
        self.instances[bot_id] = instance

        config["is_running"] = True
        save_config(bot_id, config)

        logger.info(f"🟢 Bot {bot_id} ({config['name']}) activated")
        return True

    def deactivate_bot(self, bot_id: str) -> bool:
        """Деактивирует бота полностью"""
        if bot_id not in self.instances:
            return False

        # останавливаем telegram если был
        self.instances[bot_id].stop_telegram()
        del self.instances[bot_id]

        config = load_config(bot_id)
        if config:
            config["is_running"] = False
            save_config(bot_id, config)

        logger.info(f"🔴 Bot {bot_id} deactivated")
        return True

    def start_telegram(self, bot_id: str) -> bool:
        """Подключает Telegram к боту"""
        if bot_id not in self.instances:
            # сначала активируем
            if not self.activate_bot(bot_id):
                return False

        return self.instances[bot_id].start_telegram()

    def stop_telegram(self, bot_id: str) -> bool:
        """Отключает Telegram (мозг продолжает работать)"""
        if bot_id not in self.instances:
            return False
        self.instances[bot_id].stop_telegram()
        return True

    def reload_bot(self, bot_id: str) -> bool:
        """Перезагружает конфиг"""
        if bot_id not in self.instances:
            return False
        config = load_config(bot_id)
        if not config:
            return False
        self.instances[bot_id].reload_config(config)
        return True

    def get_status(self, bot_id: str) -> dict:
        """Статус бота"""
        config = load_config(bot_id)
        if not config:
            return None

        is_active = bot_id in self.instances
        tg_running = False
        stats = {}

        if is_active:
            instance = self.instances[bot_id]
            tg_running = instance.telegram is not None and instance.telegram.is_running
            stats = instance.brain.get_stats()

        return {
            "bot_id": bot_id,
            "name": config["name"],
            "is_active": is_active,
            "telegram_connected": tg_running,
            "has_token": bool(config.get("bot_token")),
            "model": config["model"],
            "stats": stats
        }

    def get_all_statuses(self) -> list:
        """Статусы всех ботов"""
        bots = list_bots()
        return [self.get_status(c["bot_id"]) for c in bots if self.get_status(c["bot_id"])]

    def start_all(self):
        """Автозапуск ботов при старте сервера"""
        for config in list_bots():
            if config.get("is_running", False):
                self.activate_bot(config["bot_id"])
                # если есть токен — подключаем telegram
                if config.get("bot_token") and config.get("enable_telegram", False):
                    self.start_telegram(config["bot_id"])

    def stop_all(self):
        """Останавливает всё"""
        for bot_id in list(self.instances.keys()):
            self.deactivate_bot(bot_id)

    def get_brain(self, bot_id: str) -> Brain:
        """Получить мозг бота"""
        if bot_id in self.instances:
            return self.instances[bot_id].brain
        return None