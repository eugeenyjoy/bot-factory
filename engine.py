"""
Движок — управляет ботами
Веб-чат работает всегда, Telegram подключается опционально
python-telegram-bot — работает в потоках с собственным event loop
"""

import asyncio
import threading
import logging
from typing import Dict, Optional
from openai import Timeout

from core.brain import Brain
from core.config import load_config, save_config, list_bots

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("engine")

# текстовые расширения — единое место
TEXT_EXTS = {
    'txt', 'md', 'csv', 'json', 'html', 'xml', 'yml', 'yaml',
    'py', 'js', 'ts', 'css', 'log', 'ini', 'cfg', 'toml',
    'c', 'cpp', 'h', 'java', 'go', 'rs', 'rb', 'php', 'sh'
}


def _build_brain(config: dict) -> Brain:
    """Фабрика Brain — убирает дублирование"""
    return Brain(
        bot_id=config["bot_id"],
        api_key=config["api_key"],
        model=config["model"],
        system_prompt=config["system_prompt"],
        max_history=config.get("max_history", 20),
        free_messages=config.get("free_messages", 20),
        rag_top_k=config.get("rag_top_k", 3),
        provider=config.get("provider", "openrouter"),
        custom_base_url=config.get("custom_base_url", ""),
        tools_enabled=config.get("tools_enabled", True),
        tool_permissions=config.get("tool_permissions"),
        allowed_paths=config.get("allowed_paths"),
        blocked_paths=config.get("blocked_paths"),
        access_mode=config.get("access_mode", "sandbox"),
        working_directory=config.get("working_directory", ""),
        max_tool_rounds=config.get("max_tool_rounds", 15),
    )


class TelegramRunner:
    """Telegram polling в отдельном потоке с собственным event loop"""

    def __init__(self, config: dict, brain: Brain):
        self.config = config
        self.brain = brain
        self.bot_id = config["bot_id"]
        self.token = config["bot_token"]

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app = None
        self.is_running = False

    def start(self):
        if self.is_running:
            logger.warning(f"TG {self.bot_id}: already running")
            return

        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"tg-{self.bot_id}"
        )
        self._thread.start()

    def stop(self):
        if not self.is_running:
            return

        self.is_running = False

        if self._loop and self._app:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._shutdown(), self._loop
                )
                future.result(timeout=10)
            except TimeoutError:
                logger.error(f"TG {self.bot_id}: shutdown timed out")
            except Exception as e:
                logger.error(f"TG {self.bot_id}: shutdown error: {type(e).__name__}: {e}")

        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning(f"TG {self.bot_id}: thread still alive after join")
            self._thread = None

        self._app = None
        logger.info(f"🔴 Telegram stopped for bot {self.bot_id}")

    def _run(self):
        """Запускается в отдельном потоке"""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._start_polling())
        except Exception as e:
            logger.error(f"TG {self.bot_id} crashed: {type(e).__name__}: {e}")
        finally:
            self.is_running = False
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.close()
                except Exception:
                    pass
            self._loop = None

    async def _start_polling(self):
        from telegram import Update
        from telegram.ext import (
            Application, MessageHandler, CommandHandler,
            PreCheckoutQueryHandler, filters, ContextTypes
        )

        self._app = Application.builder().token(self.token).build()
        brain = self.brain
        config = self.config

        # ======== ХЭНДЛЕРЫ ========

        async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            name = config["name"]
            await update.message.reply_text(
                f"Привет! Я {name} 👋\n\n"
                f"Просто напиши мне что угодно.\n\n"
                f"Команды:\n"
                f"/reset — очистить историю\n"
                f"/help — все команды\n"
                f"/balance — сколько сообщений осталось\n"
                f"/buy — купить сообщения"
            )

        async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            brain.clear_chat(update.effective_chat.id)
            await update.message.reply_text("🗑️ История очищена!")

        async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            try:
                remaining = brain.memory.get_remaining(
                    update.effective_user.id, brain.free_messages
                )
                user = brain.memory.get_or_create_user(update.effective_user.id)
                if user.get("is_vip"):
                    await update.message.reply_text("👑 VIP — безлимит!")
                else:
                    await update.message.reply_text(
                        f"📊 Осталось: {remaining}\n"
                        f"Использовано: {user['messages_used']}\n"
                        f"Куплено: {user['messages_bought']}\n\n"
                        f"/buy — купить ещё"
                    )
            except Exception as e:
                logger.error(f"TG balance error: {type(e).__name__}: {e}")
                await update.message.reply_text("⚠️ Ошибка получения баланса")

        async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            from telegram import LabeledPrice
            price = config.get("stars_price", 50)
            msgs = config.get("messages_per_purchase", 50)
            try:
                await update.message.reply_invoice(
                    title=f"📦 {msgs} сообщений",
                    description=f"Пакет из {msgs} сообщений",
                    payload=f"buy_{msgs}",
                    currency="XTR",
                    prices=[LabeledPrice(label="Сообщения", amount=price)]
                )
            except Exception as e:
                logger.error(f"TG buy error: {type(e).__name__}: {e}")
                await update.message.reply_text("⚠️ Ошибка создания платежа")

        async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.pre_checkout_query.answer(ok=True)

        async def on_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            try:
                payment = update.message.successful_payment
                msgs = config.get("messages_per_purchase", 50)
                brain.add_purchased(
                    user_id=update.effective_user.id,
                    messages=msgs,
                    amount=payment.total_amount,
                    source="telegram"
                )
                remaining = brain.memory.get_remaining(
                    update.effective_user.id, brain.free_messages
                )
                await update.message.reply_text(
                    f"✅ Оплачено! +{msgs} сообщений\nБаланс: {remaining}"
                )
            except Exception as e:
                logger.error(f"TG payment error: {type(e).__name__}: {e}")
                await update.message.reply_text("⚠️ Ошибка обработки платежа")

        async def cmd_generic(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            """Обработка /help, /prompt, /learn и т.д. через brain"""
            text = update.message.text or ""
            try:
                result = brain.chat(
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    message=text,
                    user_name=update.effective_user.first_name
                )
                reply = result.get("reply", "...")
            except Exception as e:
                logger.error(f"TG cmd error {self.bot_id}: {type(e).__name__}: {e}")
                reply = "⚠️ Ошибка обработки команды"
            await _send_long(update, reply)

        async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return

            # группы — реагируем только на упоминание/реплай
            if update.effective_chat.type != "private":
                if not config.get("enable_groups", False):
                    return
                try:
                    bot_info = await ctx.bot.get_me()
                    bot_username = f"@{bot_info.username}"
                    is_reply = (
                        update.message.reply_to_message
                        and update.message.reply_to_message.from_user
                        and update.message.reply_to_message.from_user.id == bot_info.id
                    )
                    is_mention = bot_username.lower() in update.message.text.lower()
                    if not is_reply and not is_mention:
                        return
                except Exception as e:
                    logger.error(f"TG group check error: {e}")
                    return

            try:
                await ctx.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )
            except Exception:
                pass

            try:
                result = brain.chat(
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    message=update.message.text,
                    user_name=update.effective_user.first_name
                )
            except Exception as e:
                logger.error(f"TG chat error {self.bot_id}: {type(e).__name__}: {e}")
                await update.message.reply_text("⚠️ Внутренняя ошибка. Попробуйте ещё раз.")
                return

            if result is None:
                await update.message.reply_text("⚠️ Нет ответа от AI")
                return

            if result.get("ok") is not False and result.get("reply"):
                await _send_long(update, result["reply"])
            elif result.get("error") == "limit":
                price = config.get("stars_price", 50)
                msgs = config.get("messages_per_purchase", 50)
                await update.message.reply_text(
                    f"📭 Лимит исчерпан!\n\n"
                    f"💎 /buy — купить {msgs} сообщений за {price} ⭐"
                )
            else:
                error_msg = result.get("error", "unknown")
                logger.warning(f"TG bot {self.bot_id} error response: {error_msg}")
                await update.message.reply_text(f"⚠️ Ошибка: {error_msg}")

        async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            """Загрузка файла как знания"""
            try:
                perms = brain.permissions
            except AttributeError:
                perms = {}

            if not perms.get("user_can_add_knowledge", False):
                await update.message.reply_text("🚫 Загрузка файлов отключена")
                return

            doc = update.message.document
            if not doc:
                return

            if doc.file_size and doc.file_size > 5 * 1024 * 1024:
                await update.message.reply_text("❌ Макс 5MB")
                return

            try:
                await ctx.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )
            except Exception:
                pass

            try:
                file = await ctx.bot.get_file(doc.file_id)
                data = await file.download_as_bytearray()

                filename = doc.file_name or "document.txt"
                ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'

                if ext not in TEXT_EXTS:
                    await update.message.reply_text(
                        f"❌ .{ext} не поддерживается.\n"
                        f"Поддерживаемые: {', '.join(sorted(TEXT_EXTS)[:10])}..."
                    )
                    return

                try:
                    text = bytes(data).decode('utf-8')
                except UnicodeDecodeError:
                    text = bytes(data).decode('cp1251', errors='ignore')

                if not text.strip():
                    await update.message.reply_text("❌ Файл пустой")
                    return

                display_name = f"👤 {filename}"
                chunks = brain.rag.add_text(display_name, text)
                logger.info(f"TG file upload {self.bot_id}: {filename} → {chunks} chunks")
                await update.message.reply_text(
                    f"✅ {filename} добавлен!\n📊 {chunks} чанков"
                )

            except Exception as e:
                logger.error(f"TG file upload {self.bot_id}: {type(e).__name__}: {e}")
                await update.message.reply_text(f"❌ Ошибка загрузки: {str(e)[:200]}")

        async def _send_long(update, text: str):
            """Отправка длинных сообщений (>4096)"""
            if not text:
                text = "..."
            try:
                if len(text) <= 4096:
                    await update.message.reply_text(text)
                else:
                    for i in range(0, len(text), 4096):
                        chunk = text[i:i + 4096]
                        await update.message.reply_text(chunk)
            except Exception as e:
                logger.error(f"TG send error: {type(e).__name__}: {e}")

        # ======== РЕГИСТРАЦИЯ ========

        self._app.add_handler(CommandHandler("start", cmd_start))
        self._app.add_handler(CommandHandler("reset", cmd_reset))
        self._app.add_handler(CommandHandler("balance", cmd_balance))
        self._app.add_handler(CommandHandler("buy", cmd_buy))
        self._app.add_handler(PreCheckoutQueryHandler(pre_checkout))

        for cmd in ["help", "prompt", "prompt_clear", "learn",
                     "knowledge", "stats", "clear"]:
            self._app.add_handler(CommandHandler(cmd, cmd_generic))

        self._app.add_handler(
            MessageHandler(filters.SUCCESSFUL_PAYMENT, on_payment)
        )
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
        )
        self._app.add_handler(
            MessageHandler(filters.Document.ALL, on_document)
        )

        # ======== ЗАПУСК ========

        try:
            await self._app.initialize()
            await self._app.start()
            
            self.is_running = True
            logger.info(f"🔵 Telegram started for bot {self.bot_id}")
            
            # ✅ с таймаутом и обработкой ошибок
            try:
                await asyncio.wait_for(
                    self._app.updater.start_polling(drop_pending_updates=True),
                    timeout=None  # Polling живёт долго
                )
            except asyncio.TimeoutError:
                logger.error(f"TG polling timeout {self.bot_id}")
            except Exception as e:
                logger.error(f"TG polling error {self.bot_id}: {e}")
            
            while self.is_running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"TG startup error {self.bot_id}: {type(e).__name__}: {e}")
        finally:
            self.is_running = False
            await self._shutdown()

    async def _shutdown(self):
        try:
            if self._app:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
                logger.info(f"TG {self.bot_id}: clean shutdown")
        except Exception as e:
            logger.error(f"TG shutdown {self.bot_id}: {type(e).__name__}: {e}")


class BotInstance:
    """Один бот — мозг + опциональный Telegram"""

    def __init__(self, config: dict):
        self.config = config
        self.bot_id = config["bot_id"]
        self.brain = _build_brain(config)
        self.telegram: Optional[TelegramRunner] = None

    def start_telegram(self) -> bool:
        token = self.config.get("bot_token", "").strip()
        if not token:
            logger.warning(f"Bot {self.bot_id}: no telegram token")
            return False

        if self.telegram and self.telegram.is_running:
            return True

        # остановить предыдущий если завис
        if self.telegram:
            self.telegram.stop()

        self.telegram = TelegramRunner(self.config, self.brain)
        self.telegram.start()
        return True

    def stop_telegram(self):
        if self.telegram:
            self.telegram.stop()
            self.telegram = None

    def reload_config(self, config: dict):
        old_provider = self.config.get("provider", "openrouter")
        old_key = self.config.get("api_key", "")
        old_base_url = self.config.get("custom_base_url", "")

        self.config = config

        new_provider = config.get("provider", "openrouter")
        new_key = config.get("api_key", "")
        new_base_url = config.get("custom_base_url", "")

        if (old_provider != new_provider or
                old_key != new_key or
                old_base_url != new_base_url):
            self.brain = _build_brain(config)
            logger.info(f"♻️ Bot {self.bot_id} provider changed: {old_provider} → {new_provider}")

            # перезапускаем telegram с новым brain
            if self.telegram and self.telegram.is_running:
                self.stop_telegram()
                self.start_telegram()
        else:
            self.brain.update_model(config["model"])
            self.brain.update_prompt(config["system_prompt"])
            self.brain.update_free_limit(config.get("free_messages", 20))
            self.brain.update_max_history(config.get("max_history", 20))

            if config.get("tool_permissions"):
                self.brain.update_tool_permissions(config["tool_permissions"])
            self.brain.set_tools_enabled(config.get("tools_enabled", True))

        logger.info(f"♻️ Bot {self.bot_id} config reloaded")


class Engine:
    """Управляет всеми ботами"""

    def __init__(self):
        self.instances: Dict[str, BotInstance] = {}
        self._lock = threading.Lock()
        # ✅ Лимит на параллельные Telegram polling'и
        self._max_telegram_threads = 50
        self._active_telegram_threads = 0

    def activate_bot(self, bot_id: str) -> bool:
        with self._lock:
            if bot_id in self.instances:
                return True

            config = load_config(bot_id)
            if not config:
                logger.error(f"Config not found: {bot_id}")
                return False

            if not config.get("api_key"):
                logger.error(f"Bot {bot_id}: no api_key")
                return False

            try:
                instance = BotInstance(config)
            except Exception as e:
                logger.error(f"Failed to create bot {bot_id}: {type(e).__name__}: {e}")
                return False

            self.instances[bot_id] = instance

            config["is_running"] = True
            save_config(bot_id, config)

            logger.info(f"🟢 Bot {bot_id} ({config['name']}) activated")
            return True

    def deactivate_bot(self, bot_id: str) -> bool:
        with self._lock:
            if bot_id not in self.instances:
                return False

            try:
                self.instances[bot_id].stop_telegram()
            except Exception as e:
                logger.error(f"Error stopping telegram {bot_id}: {e}")

            del self.instances[bot_id]

            config = load_config(bot_id)
            if config:
                config["is_running"] = False
                save_config(bot_id, config)

            logger.info(f"🔴 Bot {bot_id} deactivated")
            return True

    def start_telegram(self, bot_id: str) -> bool:
        with self._lock:
            # ✅ Проверка лимита потоков
            if self._active_telegram_threads >= self._max_telegram_threads:
                logger.error(f"Max Telegram threads reached ({self._max_telegram_threads})")
                return False
            
            if bot_id not in self.instances:
                if not self.activate_bot(bot_id):
                    return False
            
            success = self.instances[bot_id].start_telegram()
            if success:
                self._active_telegram_threads += 1
            return success

    def stop_telegram(self, bot_id: str) -> bool:
        if bot_id not in self.instances:
            return False
        with self._lock:
            if self._active_telegram_threads > 0:
                self._active_telegram_threads -= 1
        self.instances[bot_id].stop_telegram()
        return True

    def reload_bot(self, bot_id: str) -> bool:
        if bot_id not in self.instances:
            return False
        config = load_config(bot_id)
        if not config:
            return False
        self.instances[bot_id].reload_config(config)
        return True

    def get_status(self, bot_id: str) -> dict:
        config = load_config(bot_id)
        if not config:
            return None

        is_active = bot_id in self.instances
        tg_running = False
        stats = {}

        if is_active:
            instance = self.instances[bot_id]
            tg_running = (
                instance.telegram is not None
                and instance.telegram.is_running
            )
            try:
                stats = instance.brain.get_stats()
            except Exception as e:
                logger.error(f"Stats error {bot_id}: {e}")

        return {
            "bot_id": bot_id,
            "name": config["name"],
            "is_active": is_active,
            "telegram_connected": tg_running,
            "has_token": bool(config.get("bot_token", "").strip()),
            "model": config["model"],
            "provider": config.get("provider", "openrouter"),
            "stats": stats
        }

    def get_all_statuses(self) -> list:
        bots = list_bots()
        result = []
        for c in bots:
            status = self.get_status(c["bot_id"])
            if status:
                result.append(status)
        return result

    def start_all(self):
        for config in list_bots():
            if config.get("is_running", False):
                self.activate_bot(config["bot_id"])
                if (config.get("bot_token", "").strip()
                        and config.get("enable_telegram", False)):
                    self.start_telegram(config["bot_id"])

    def stop_all(self):
        for bot_id in list(self.instances.keys()):
            self.deactivate_bot(bot_id)

    def get_brain(self, bot_id: str) -> Optional[Brain]:
        instance = self.instances.get(bot_id)
        return instance.brain if instance else None