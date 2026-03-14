"""
Мозг бота — AI + терминал
Модель пишет bash команды в ```bash``` блоках, мы выполняем
"""

import json
import logging
from pathlib import Path
from openai import OpenAI
from core.memory import Memory
from core.rag import RAG
from core.config import AI_PROVIDERS
from core.tools import ToolExecutor, parse_commands, ROOT_DIR

logger = logging.getLogger("brain")

# сколько раз модель может вызвать команды за один запрос
# каждый раунд = вызов API (расход токенов), поэтому ограничиваем
DEFAULT_MAX_ROUNDS = 15


class Brain:

    def __init__(self, bot_id: str, api_key: str, model: str,
                 system_prompt: str, max_history: int = 20,
                 free_messages: int = 20, rag_top_k: int = 3,
                 provider: str = "openrouter", custom_base_url: str = "",
                 tool_permissions: dict = None, allowed_paths: list = None,
                 blocked_paths: list = None, tools_enabled: bool = True,
                 access_mode: str = "sandbox", working_directory: str = "",
                 max_tool_rounds: int = DEFAULT_MAX_ROUNDS):

        self.bot_id = bot_id
        self.model = model
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.free_messages = free_messages
        self.rag_top_k = rag_top_k
        self.provider = provider
        self.tools_enabled = tools_enabled
        self.max_tool_rounds = max_tool_rounds

        if provider == "custom" and custom_base_url:
            base_url = custom_base_url
        elif provider in AI_PROVIDERS:
            base_url = AI_PROVIDERS[provider]["base_url"]
        else:
            base_url = AI_PROVIDERS["openrouter"]["base_url"]

        self.ai_client = OpenAI(base_url=base_url, api_key=api_key)
        self.memory = Memory(bot_id)
        self._rag = None

        self.tool_executor = ToolExecutor(
            bot_id=bot_id,
            permissions=tool_permissions,
            access_mode=access_mode,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            working_directory=working_directory,
        )

    @property
    def rag(self) -> RAG:
        if self._rag is None:
            self._rag = RAG(self.bot_id)
        return self._rag

    def chat(self, chat_id: int, user_id: int, message: str,
             user_name: str = None) -> dict:

        if not self.memory.can_send(user_id, self.free_messages):
            remaining = self.memory.get_remaining(user_id, self.free_messages)
            return {"ok": False, "error": "limit", "remaining": remaining}

        history = self.memory.get_history(chat_id, self.max_history)
        facts = self.memory.get_facts(user_id)

        knowledge_context = ""
        if self._rag and self._rag.chunks:
            knowledge_context = self._rag.get_context(message, top_k=self.rag_top_k)

        system = self._build_system_prompt(user_name, facts, knowledge_context)

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            reply, tool_log = self._call_ai(messages)

            if not reply or reply.strip() == "":
                reply = "🤔 Пустой ответ."

            self.memory.save_message(chat_id, user_id, "user", message)
            self.memory.save_message(chat_id, user_id, "assistant", reply)
            self.memory.use_message(user_id)

            remaining = self.memory.get_remaining(user_id, self.free_messages)
            result = {"ok": True, "reply": reply, "remaining": remaining}
            if tool_log:
                result["tools_used"] = tool_log
            return result

        except Exception as e:
            logger.error(f"AI error for bot {self.bot_id}: {e}")
            return {"ok": False, "error": str(e)}

    def _call_ai(self, messages: list) -> tuple:
        tool_log = []
        formatted = ""

        for round_num in range(self.max_tool_rounds):
            response = self.ai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.7
            )

            reply = response.choices[0].message.content or ""
            if not reply and hasattr(response.choices[0].message, 'refusal'):
                reply = response.choices[0].message.refusal or ""

            # если tools выключены — возвращаем как есть
            if not self.tools_enabled:
                return reply, tool_log

            # парсим команды
            commands = parse_commands(reply)

            if not commands:
                return reply, tool_log

            # выполняем
            logger.info(f"🔧 Bot {self.bot_id} round {round_num+1}: {len(commands)} cmds")
            results = self.tool_executor.execute_commands(commands)
            formatted = self.tool_executor.format_results(results)

            for r in results:
                tool_log.append({
                    "command": r.get("command"),
                    "exit_code": r.get("exit_code"),
                    "error": r.get("error"),
                })

            messages.append({"role": "assistant", "content": reply})

            if round_num >= self.max_tool_rounds - 2:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Результаты:\n```\n{formatted}\n```\n\n"
                        f"Дай ФИНАЛЬНЫЙ ответ. Больше НЕ пиши команд."
                    )
                })
            else:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Результаты:\n```\n{formatted}\n```\n\n"
                        f"Ответь пользователю. Если нужно ещё — пиши ```bash``` блоки."
                    )
                })
            continue

        # последний ответ модели
        try:
            response = self.ai_client.chat.completions.create(
                model=self.model, messages=messages,
                max_tokens=4096, temperature=0.7
            )
            return response.choices[0].message.content or formatted, tool_log
        except:
            return f"Выполнено {len(tool_log)} команд.\n```\n{formatted}\n```", tool_log

    def _build_system_prompt(self, user_name=None, facts=None,
                              knowledge_context=""):
        parts = [self.system_prompt]

        if self.tools_enabled:
            cwd = self.tool_executor.cwd
            mode = self.tool_executor.access_mode
            perms = self.tool_executor.permissions

            mode_desc = {
                "sandbox": f"Песочница: {self.tool_executor.workspace}",
                "full": f"Полный доступ к системе. Домашняя папка: {Path.home()}",
                "project": f"Папка проекта: {ROOT_DIR}",
                "custom": f"Указанные папки",
            }

            parts.append(f"""

🔧 ТЕРМИНАЛ
У тебя есть реальный доступ к терминалу Linux.
Режим: {mode_desc.get(mode, mode)}
Рабочая директория: {cwd}

Чтобы выполнить команды — пиши в блоке:
```bash
команда
Примеры:

Bash

ls -la
Bash

echo "hello" > file.txt && cat file.txt
Bash

pwd && df -h && uname -a
Права: {'✅ запись' if perms.get('write_files') else '❌ запись'} | {'✅ удаление' if perms.get('delete_files') else '❌ удаление'} | {'✅ сеть' if perms.get('network') else '❌ сеть'} | {'✅ пакеты' if perms.get('install_packages') else '❌ пакеты'}

ПРАВИЛА:

ВСЕГДА используй реальные команды для работы с файлами и системой

НИКОГДА не выдумывай содержимое — читай через cat

НИКОГДА не говори что нет доступа — он ЕСТЬ

Можешь комбинировать команды через && и |

После получения результатов — объясни пользователю что получилось
""")

        if facts:
            parts.append(f"\nФакты о пользователе:\n" + "\n".join(f"- {f}" for f in facts))
        if user_name:
            parts.append(f"\nИмя: {user_name}")
        if knowledge_context:
            parts.append(f"\n📚 БАЗА ЗНАНИЙ:\n{knowledge_context}")

        return "\n".join(parts)
    #============================
    #УПРАВЛЕНИЕ
    #============================
    def clear_chat(self, chat_id: int):
        self.memory.clear_history(chat_id)

    def clear_user(self, user_id: int):
        self.memory.reset_user(user_id)

    def clear_all(self):
        self.memory.reset_all()

    def set_vip(self, user_id: int, is_vip: bool):
        self.memory.set_vip(user_id, is_vip)

    def add_purchased(self, user_id: int, messages: int, amount: int, source: str):
        self.memory.add_purchased(user_id, messages, amount, source)

    def get_users(self) -> list:
        return self.memory.get_all_users()

    def get_stats(self) -> dict:
        stats = self.memory.get_stats()
        if self._rag:
            stats["knowledge"] = self._rag.get_info()
            stats["tools"] = self.tool_executor.get_info()
            stats["tools"]["enabled"] = self.tools_enabled
        return stats

    def update_model(self, model: str):
        self.model = model

    def update_prompt(self, prompt: str):
        self.system_prompt = prompt

    def update_free_limit(self, limit: int):
        self.free_messages = limit

    def update_max_history(self, limit: int):
        self.max_history = limit

    def update_tool_permissions(self, permissions: dict):
        self.tool_executor.permissions.update(permissions)

    def set_tools_enabled(self, enabled: bool):
        self.tools_enabled = enabled