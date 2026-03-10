#!/usr/bin/env python3
"""
CLI чат с ботом — работает в терминале
Использование:
    python cli_chat.py                     # интерактивный выбор бота
    python cli_chat.py --bot BOT_ID        # конкретный бот
    python cli_chat.py --bot BOT_ID --user 42  # конкретный юзер
"""

import sys
import argparse
import readline  # для истории ввода в терминале

from core.config import list_bots, load_config
from core.brain import Brain


# цвета для терминала
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def select_bot() -> dict:
    """Интерактивный выбор бота"""
    bots = list_bots()

    if not bots:
        print(f"{Colors.RED}❌ Нет ботов. Создайте через веб-панель: python app.py{Colors.RESET}")
        sys.exit(1)

    if len(bots) == 1:
        config = bots[0]
        print(f"{Colors.DIM}Единственный бот: {config['name']}{Colors.RESET}")
        return config

    print(f"\n{Colors.BOLD}🤖 Доступные боты:{Colors.RESET}\n")
    for i, bot in enumerate(bots, 1):
        provider = bot.get('provider', 'openrouter')
        print(f"  {Colors.CYAN}{i}{Colors.RESET}. {bot['name']}")
        print(f"     {Colors.DIM}Модель: {bot['model']} · via {provider}{Colors.RESET}")
        print()

    while True:
        try:
            choice = input(f"{Colors.YELLOW}Выберите бота (1-{len(bots)}): {Colors.RESET}").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(bots):
                return bots[idx]
        except (ValueError, EOFError):
            pass
        print(f"{Colors.RED}Неверный выбор{Colors.RESET}")


def create_brain(config: dict) -> Brain:
    """Создаёт мозг бота из конфига"""
    return Brain(
        bot_id=config["bot_id"],
        api_key=config["api_key"],
        model=config["model"],
        system_prompt=config["system_prompt"],
        max_history=config.get("max_history", 20),
        free_messages=config.get("free_messages", 999999),  # в CLI без лимита
        rag_top_k=config.get("rag_top_k", 3),
        provider=config.get("provider", "openrouter"),
        custom_base_url=config.get("custom_base_url", ""),
    )


def print_header(config: dict):
    """Красивая шапка"""
    provider = config.get('provider', 'openrouter')
    print()
    print(f"  {Colors.BOLD}{'═' * 50}{Colors.RESET}")
    print(f"  {Colors.BOLD}🤖 {config['name']}{Colors.RESET}")
    print(f"  {Colors.DIM}Модель: {config['model']}{Colors.RESET}")
    print(f"  {Colors.DIM}Провайдер: {provider}{Colors.RESET}")
    print(f"  {Colors.BOLD}{'═' * 50}{Colors.RESET}")
    print()
    print(f"  {Colors.DIM}Команды:{Colors.RESET}")
    print(f"  {Colors.DIM}  /clear  — очистить историю{Colors.RESET}")
    print(f"  {Colors.DIM}  /model  — сменить модель{Colors.RESET}")
    print(f"  {Colors.DIM}  /system — показать системный промпт{Colors.RESET}")
    print(f"  {Colors.DIM}  /multi  — многострочный ввод (закончить: \\end){Colors.RESET}")
    print(f"  {Colors.DIM}  /stats  — статистика{Colors.RESET}")
    print(f"  {Colors.DIM}  /quit   — выход{Colors.RESET}")
    print()


def get_multiline_input() -> str:
    """Многострочный ввод — заканчивается на \\end"""
    print(f"{Colors.DIM}  (многострочный режим — введите \\end чтобы отправить){Colors.RESET}")
    lines = []
    while True:
        try:
            line = input(f"{Colors.DIM}  ...│ {Colors.RESET}")
            if line.strip() == '\\end':
                break
            lines.append(line)
        except EOFError:
            break
    return '\n'.join(lines)


def run_chat(config: dict, user_id: int = 1):
    """Главный цикл чата"""
    brain = create_brain(config)
    chat_id = user_id

    print_header(config)

    # приветствие
    if config.get("system_prompt"):
        prompt_preview = config["system_prompt"][:100]
        if len(config["system_prompt"]) > 100:
            prompt_preview += "..."
        print(f"  {Colors.DIM}💡 Промпт: {prompt_preview}{Colors.RESET}")
        print()

    while True:
        try:
            user_input = input(f"{Colors.GREEN}  Вы ▸ {Colors.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {Colors.DIM}👋 Пока!{Colors.RESET}\n")
            break

        if not user_input:
            continue

        # ============================
        # КОМАНДЫ
        # ============================

        if user_input.startswith('/'):
            cmd = user_input.lower().split()[0]

            if cmd in ('/quit', '/exit', '/q'):
                print(f"\n  {Colors.DIM}👋 Пока!{Colors.RESET}\n")
                break

            elif cmd == '/clear':
                brain.clear_chat(chat_id)
                print(f"  {Colors.YELLOW}🗑️  История очищена{Colors.RESET}\n")
                continue

            elif cmd == '/system':
                print(f"\n  {Colors.CYAN}📝 Системный промпт:{Colors.RESET}")
                for line in config["system_prompt"].split('\n'):
                    print(f"  {Colors.DIM}  {line}{Colors.RESET}")
                print()
                continue

            elif cmd == '/model':
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    new_model = parts[1].strip()
                    brain.update_model(new_model)
                    config["model"] = new_model
                    print(f"  {Colors.YELLOW}🔄 Модель: {new_model}{Colors.RESET}\n")
                else:
                    print(f"  {Colors.DIM}Текущая: {config['model']}{Colors.RESET}")
                    print(f"  {Colors.DIM}Использование: /model model-id{Colors.RESET}\n")
                continue

            elif cmd == '/multi':
                user_input = get_multiline_input()
                if not user_input.strip():
                    continue

            elif cmd == '/stats':
                stats = brain.get_stats()
                print(f"\n  {Colors.CYAN}📊 Статистика:{Colors.RESET}")
                print(f"  {Colors.DIM}  Юзеров: {stats.get('total_users', 0)}{Colors.RESET}")
                print(f"  {Colors.DIM}  Сообщений: {stats.get('total_messages', 0)}{Colors.RESET}")
                if stats.get('knowledge'):
                    k = stats['knowledge']
                    print(f"  {Colors.DIM}  База знаний: {k.get('total_files', 0)} файлов, {k.get('total_chunks', 0)} чанков{Colors.RESET}")
                print()
                continue

            elif cmd == '/help':
                print_header(config)
                continue

            else:
                print(f"  {Colors.RED}Неизвестная команда. /help для списка{Colors.RESET}\n")
                continue

        # ============================
        # ОТПРАВКА СООБЩЕНИЯ
        # ============================

        # индикатор думания
        print(f"  {Colors.DIM}  ⏳ Думаю...{Colors.RESET}", end='', flush=True)

        result = brain.chat(
            chat_id=chat_id,
            user_id=user_id,
            message=user_input,
            user_name="CLI User"
        )

        # стираем "Думаю..."
        print('\r' + ' ' * 40 + '\r', end='')

        if result["ok"]:
            reply = result["reply"]
            # печатаем ответ построчно с отступом
            print(f"  {Colors.BLUE}  🤖 ▸{Colors.RESET} ", end='')
            lines = reply.split('\n')
            print(lines[0])
            for line in lines[1:]:
                print(f"       {line}")
            print()
        else:
            error = result.get("error", "Unknown error")
            print(f"  {Colors.RED}  ❌ Ошибка: {error}{Colors.RESET}\n")


def main():
    parser = argparse.ArgumentParser(description='🤖 Bot Factory — CLI Chat')
    parser.add_argument('--bot', '-b', help='Bot ID')
    parser.add_argument('--user', '-u', type=int, default=1, help='User ID (default: 1)')
    parser.add_argument('--list', '-l', action='store_true', help='Показать список ботов')
    args = parser.parse_args()

    print(f"\n  {Colors.BOLD}🤖 Bot Factory — Terminal Chat{Colors.RESET}")

    # список ботов
    if args.list:
        bots = list_bots()
        if not bots:
            print(f"  {Colors.RED}Нет ботов{Colors.RESET}")
            return
        for bot in bots:
            p = bot.get('provider', 'openrouter')
            print(f"  • {bot['bot_id']} — {bot['name']} ({bot['model']}) via {p}")
        return

    # выбираем бота
    if args.bot:
        config = load_config(args.bot)
        if not config:
            print(f"  {Colors.RED}❌ Бот {args.bot} не найден{Colors.RESET}")
            sys.exit(1)
    else:
        config = select_bot()

    # проверяем ключ
    if not config.get("api_key"):
        print(f"  {Colors.RED}❌ У бота нет API ключа{Colors.RESET}")
        sys.exit(1)

    # запускаем чат
    run_chat(config, user_id=args.user)


if __name__ == "__main__":
    main()