"""
Инструменты AI агента — выполнение shell команд
Режимы доступа:
  - sandbox: только workspace папка (безопасно для чат-ботов)
  - full: весь ПК (для персональных ассистентов)
  - project: папка проекта bot-factory
  - custom: указанные папки
"""

import os
import re
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("tools")

ROOT_DIR = Path(__file__).parent.parent
BOTS_DIR = ROOT_DIR / "bots"

CODE_TIMEOUT = 30
MAX_COMMAND_LENGTH = 10000
MAX_COMMANDS_PER_BATCH = 50

# ============================================================
#  ПРАВА
# ============================================================

DEFAULT_PERMISSIONS = {
    "execute_commands": True,
    "write_files": True,
    "delete_files": False,
    "network": False,
    "install_packages": False,
    "user_can_add_prompt": False,
    "user_can_add_knowledge": False,
    "user_can_clear_history": True,
}

# ВСЕГДА заблокировано — даже в full режиме
ALWAYS_BLOCKED = [
    'rm -rf /', 'rm -rf /*', 'mkfs', 'dd if=/dev/zero',
    'dd if=/dev/random', ':(){', 'shutdown', 'reboot',
    'poweroff', 'init 0', 'init 6', 'halt',
    'chmod -R 777 /', 'chown -R', '> /dev/sd',
    'fork()', ':(){ :|:& };:',
]

DELETE_COMMANDS = ['rm ', 'rmdir ', 'unlink ']
NETWORK_COMMANDS = ['curl ', 'wget ', 'ping ', 'ssh ', 'scp ', 'nc ', 'netcat ', 'nmap ']
INSTALL_COMMANDS = ['pip ', 'pip3 ', 'apt ', 'apt-get ', 'yum ', 'npm ', 'yarn ', 'brew ']


# ============================================================
#  ПАРСЕР КОМАНД
# ============================================================

def parse_commands(text: str) -> List[str]:
    """
    Извлекает команды из текста.
    Форматы:
        ```bash
        ls -la
        ```
        $ ls -la
    """
    if not text or not text.strip():
        return []

    commands = []

    # блоки ```bash```
    pattern = re.compile(
        r'```(?:bash|sh|shell|cmd|command|zsh)?\s*\n(.*?)```',
        re.DOTALL
    )
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        for line in block.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('$ '):
                    line = line[2:]
                if line:
                    commands.append(line)

    # строки с $ (fallback)
    if not commands:
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('$ '):
                cmd = line[2:].strip()
                if cmd:
                    commands.append(cmd)

    # лимит
    return commands[:MAX_COMMANDS_PER_BATCH]


# ============================================================
#  ИСПОЛНИТЕЛЬ
# ============================================================

class ToolExecutor:
    """
    access_mode:
        "sandbox"  — только workspace (default, безопасно)
        "full"     — весь ПК, cwd = home dir
        "project"  — папка проекта bot-factory
        "custom"   — указанные в allowed_paths папки
    """

    def __init__(self, bot_id: str, permissions: dict = None,
                 access_mode: str = "sandbox",
                 allowed_paths: list = None, blocked_paths: list = None,
                 working_directory: str = ""):
        self.bot_id = bot_id

        # валидация access_mode
        valid_modes = {"sandbox", "full", "project", "custom"}
        self.access_mode = access_mode if access_mode in valid_modes else "sandbox"

        # workspace — всегда существует
        self.workspace = BOTS_DIR / f"bot_{bot_id}" / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # рабочая директория зависит от режима
        if working_directory:
            wd = Path(working_directory)
            if wd.exists() and wd.is_dir():
                self.cwd = wd
            else:
                logger.warning(
                    f"Working directory not found: {working_directory}, "
                    f"using default for {self.access_mode}"
                )
                self.cwd = self._default_cwd()
        else:
            self.cwd = self._default_cwd()

        # права
        self.permissions = {**DEFAULT_PERMISSIONS}
        if isinstance(permissions, dict):
            self.permissions.update(permissions)

        # разрешённые папки
        self.allowed_paths: List[str] = []
        if allowed_paths:
            for p in allowed_paths:
                try:
                    rp = Path(p).resolve()
                    if rp.exists():
                        self.allowed_paths.append(str(rp))
                except (OSError, ValueError) as e:
                    logger.warning(f"Invalid allowed path {p}: {e}")

        # заблокированные папки
        self.blocked_paths: List[str] = []
        if blocked_paths:
            self.blocked_paths = [
                str(p) for p in blocked_paths if isinstance(p, str)
            ]

    def _default_cwd(self) -> Path:
        """Возвращает дефолтную рабочую директорию по режиму"""
        if self.access_mode == "full":
            return Path.home()
        elif self.access_mode == "project":
            return ROOT_DIR
        else:
            return self.workspace

    def check_command(self, command: str) -> Optional[str]:
        """Проверяет безопасность. Возвращает ошибку или None"""
        if not command or not command.strip():
            return "🚫 Пустая команда"

        if len(command) > MAX_COMMAND_LENGTH:
            return f"🚫 Команда слишком длинная (макс {MAX_COMMAND_LENGTH})"

        cmd_lower = command.lower().strip()

        # ВСЕГДА заблокировано
        for blocked in ALWAYS_BLOCKED:
            if blocked in cmd_lower:
                logger.warning(
                    f"BLOCKED dangerous command from bot {self.bot_id}: {command[:100]}"
                )
                return "🚫 Заблокировано: опасная операция"

        # sudo с опасными командами
        if cmd_lower.startswith('sudo') and any(b in cmd_lower for b in ALWAYS_BLOCKED):
            return "🚫 Заблокировано: опасная операция"

        if not self.permissions.get("execute_commands", True):
            return "🚫 Выполнение команд отключено"

        if not self.permissions.get("write_files", True):
            write_indicators = ['>', '>>', ' tee ', 'cp ', 'mv ', 'mkdir ', 'touch ']
            for w in write_indicators:
                if w in cmd_lower:
                    return "🚫 Запись файлов отключена"

        if not self.permissions.get("delete_files", False):
            for d in DELETE_COMMANDS:
                if d in cmd_lower:
                    return "🚫 Удаление отключено"

        if not self.permissions.get("network", False):
            for n in NETWORK_COMMANDS:
                if n in cmd_lower:
                    return "🚫 Сетевые команды отключены"

        if not self.permissions.get("install_packages", False):
            for i in INSTALL_COMMANDS:
                if cmd_lower.startswith(i) or f'sudo {i}' in cmd_lower:
                    return "🚫 Установка пакетов отключена"

        # заблокированные пути
        for bp in self.blocked_paths:
            if bp in command:
                return f"🚫 Доступ к {bp} запрещён"

        # sandbox ограничения
        if self.access_mode == "sandbox":
            if 'cd /' in cmd_lower or 'cd ~' in cmd_lower:
                return "🚫 В sandbox режиме нельзя выходить за рабочую папку"
            # разрешаем cd .. только если не выходим за workspace
            if 'cd ..' in cmd_lower:
                return "🚫 В sandbox режиме нельзя выходить за рабочую папку"

        return None

    def execute_command(self, command: str) -> Dict:
        """Выполняет одну команду"""
        error = self.check_command(command)
        if error:
            return {"command": command, "error": error, "exit_code": -1}

        try:
            env = {**os.environ, 'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8'}

            # в sandbox ограничиваем HOME
            if self.access_mode == "sandbox":
                env['HOME'] = str(self.workspace)

            # проверяем что cwd существует
            cwd = str(self.cwd)
            if not Path(cwd).exists():
                cwd = str(self.workspace)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=CODE_TIMEOUT,
                cwd=cwd,
                env=env,
            )

            stdout = result.stdout[:15000] if result.stdout else ""
            stderr = result.stderr[:5000] if result.stderr else ""

            return {
                "command": command,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"Command timeout {self.bot_id}: {command[:100]}")
            return {
                "command": command,
                "error": f"⏱️ Таймаут ({CODE_TIMEOUT}с)",
                "exit_code": -1
            }
        except OSError as e:
            logger.error(f"OS error executing command {self.bot_id}: {e}")
            return {"command": command, "error": f"Ошибка ОС: {e}", "exit_code": -1}
        except Exception as e:
            logger.error(
                f"Command error {self.bot_id}: {type(e).__name__}: {e}"
            )
            return {
                "command": command,
                "error": f"Ошибка: {str(e)[:200]}",
                "exit_code": -1
            }

    def execute_commands(self, commands: List[str]) -> List[Dict]:
        """Выполняет список команд"""
        if not commands:
            return []

        # лимит
        commands = commands[:MAX_COMMANDS_PER_BATCH]

        results = []
        for cmd in commands:
            result = self.execute_command(cmd)
            results.append(result)
            exit_code = result.get('exit_code', '?')
            has_error = result.get('error', '')
            if has_error:
                logger.info(f"🔧 {self.bot_id}: $ {cmd[:80]} → ERROR: {has_error[:50]}")
            else:
                logger.info(f"🔧 {self.bot_id}: $ {cmd[:80]} → exit={exit_code}")

        return results

    def format_results(self, results: List[Dict]) -> str:
        """Форматирует результаты для AI модели"""
        if not results:
            return "(нет результатов)"

        parts = []
        for r in results:
            cmd = r.get("command", "?")
            if r.get("error"):
                parts.append(f"$ {cmd}\n❌ {r['error']}")
            else:
                output_parts = []
                if r.get("stdout"):
                    output_parts.append(r["stdout"])
                if r.get("stderr"):
                    output_parts.append(f"STDERR: {r['stderr']}")

                output = "\n".join(output_parts).strip()
                if not output:
                    output = "(ok, нет вывода)"

                exit_code = r.get("exit_code", 0)
                if exit_code != 0:
                    output += f"\n[exit code: {exit_code}]"

                parts.append(f"$ {cmd}\n{output}")

        return "\n\n".join(parts)

    def get_info(self) -> Dict:
        """Информация о workspace"""
        try:
            file_count = sum(
                1 for _ in self.workspace.rglob('*') if _.is_file()
            )
            ws_size = sum(
                f.stat().st_size for f in self.workspace.rglob('*')
                if f.is_file()
            )
        except (OSError, PermissionError) as e:
            logger.warning(f"Workspace scan error {self.bot_id}: {e}")
            file_count = 0
            ws_size = 0

        return {
            "access_mode": self.access_mode,
            "working_directory": str(self.cwd),
            "workspace": str(self.workspace),
            "files": file_count,
            "size_bytes": ws_size,
            "permissions": dict(self.permissions),
        }