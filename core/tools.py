"""
Инструменты AI агента — выполнение shell команд
Режимы доступа:
  - sandbox: только workspace папка (безопасно для чат-ботов)
  - full: весь ПК (для персональных ассистентов)
  - custom: указанные папки
"""

import os
import re
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("tools")

ROOT_DIR = Path(__file__).parent.parent
BOTS_DIR = ROOT_DIR / "bots"

CODE_TIMEOUT = 30

# ============================================================
#  ПРАВА
# ============================================================

DEFAULT_PERMISSIONS = {
    "execute_commands": True,
    "write_files": True,
    "delete_files": False,
    "network": False,
    "install_packages": False,
}

# ВСЕГДА заблокировано — даже в full режиме
ALWAYS_BLOCKED = [
    'rm -rf /', 'rm -rf /*', 'mkfs', 'dd if=/dev/zero',
    'dd if=/dev/random', ':(){', 'shutdown', 'reboot',
    'poweroff', 'init 0', 'init 6',
    'chmod -R 777 /', 'chown -R', '> /dev/sd',
]

DELETE_COMMANDS = ['rm ', 'rmdir ', 'unlink ']
NETWORK_COMMANDS = ['curl ', 'wget ', 'ping ', 'ssh ', 'scp ', 'nc ', 'netcat ', 'nmap ']
INSTALL_COMMANDS = ['pip ', 'pip3 ', 'apt ', 'apt-get ', 'yum ', 'npm ', 'yarn ', 'brew ']


# ============================================================
#  ПАРСЕР КОМАНД
# ============================================================

def parse_commands(text: str) -> list:
    """
    Извлекает команды из текста.
    Форматы:
        ```bash
        ls -la
        ```
        $ ls -la
    """
    commands = []

    # блоки ```bash```
    pattern = re.compile(r'```(?:bash|sh|shell|cmd|command|zsh)?\s*\n(.*?)```', re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        for line in block.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('$ '):
                    line = line[2:]
                commands.append(line)

    # строки с $
    if not commands:
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('$ '):
                commands.append(line[2:])

    return commands


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
        self.access_mode = access_mode

        # workspace — всегда существует
        self.workspace = BOTS_DIR / f"bot_{bot_id}" / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # рабочая директория зависит от режима
        if working_directory and Path(working_directory).exists():
            self.cwd = Path(working_directory)
        elif access_mode == "full":
            self.cwd = Path.home()
        elif access_mode == "project":
            self.cwd = ROOT_DIR
        else:
            self.cwd = self.workspace

        self.permissions = {**DEFAULT_PERMISSIONS}
        if permissions:
            self.permissions.update(permissions)

        # дополнительные разрешённые папки
        self.allowed_paths = []
        if allowed_paths:
            for p in allowed_paths:
                rp = Path(p).resolve()
                if rp.exists():
                    self.allowed_paths.append(str(rp))

        self.blocked_paths = []
        if blocked_paths:
            self.blocked_paths = blocked_paths

    def check_command(self, command: str) -> str:
        """Проверяет безопасность. Возвращает ошибку или None"""
        cmd_lower = command.lower().strip()

        for blocked in ALWAYS_BLOCKED:
            if blocked in cmd_lower:
                return f"🚫 Заблокировано: опасная операция"

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

        # проверяем заблокированные пути
        for bp in self.blocked_paths:
            if bp in command:
                return f"🚫 Доступ к {bp} запрещён"

        # в sandbox режиме блокируем cd за пределы workspace
        if self.access_mode == "sandbox":
            if 'cd /' in cmd_lower or 'cd ~' in cmd_lower or 'cd ..' in cmd_lower:
                return "🚫 В sandbox режиме нельзя выходить за рабочую папку"

        return None

    def execute_command(self, command: str) -> dict:
        """Выполняет одну команду"""
        error = self.check_command(command)
        if error:
            return {"command": command, "error": error}

        try:
            env = {**os.environ, 'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8'}

            # в sandbox ограничиваем HOME
            if self.access_mode == "sandbox":
                env['HOME'] = str(self.workspace)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=CODE_TIMEOUT,
                cwd=str(self.cwd),
                env=env,
            )

            return {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout[:15000] if result.stdout else "",
                "stderr": result.stderr[:5000] if result.stderr else "",
            }

        except subprocess.TimeoutExpired:
            return {"command": command, "error": f"Таймаут ({CODE_TIMEOUT}с)"}
        except Exception as e:
            return {"command": command, "error": str(e)}

    def execute_commands(self, commands: list) -> list:
        """Выполняет список команд"""
        results = []
        for cmd in commands:
            result = self.execute_command(cmd)
            results.append(result)
            logger.info(f"🔧 {self.bot_id}: $ {cmd} → exit={result.get('exit_code', '?')}")
        return results

    def format_results(self, results: list) -> str:
        """Форматирует для модели"""
        parts = []
        for r in results:
            cmd = r.get("command", "?")
            if r.get("error"):
                parts.append(f"$ {cmd}\n❌ {r['error']}")
            else:
                output = ""
                if r.get("stdout"):
                    output += r["stdout"]
                if r.get("stderr"):
                    output += f"\nSTDERR: {r['stderr']}"
                if not output.strip():
                    output = "(ok, нет вывода)"
                parts.append(f"$ {cmd}\n{output.strip()}")
        return "\n\n".join(parts)

    def get_info(self) -> dict:
        file_count = sum(1 for _ in self.workspace.rglob('*') if _.is_file())
        ws_size = sum(f.stat().st_size for f in self.workspace.rglob('*') if f.is_file())
        return {
            "access_mode": self.access_mode,
            "working_directory": str(self.cwd),
            "workspace": str(self.workspace),
            "files": file_count,
            "size_bytes": ws_size,
            "permissions": self.permissions,
        }