"""
Bot Factory — Установка
Работает на Windows, Linux, macOS
Запуск: python setup/setup.py (из корня проекта)
"""

import subprocess
import sys
import os
import platform

def run(cmd):
    """Выполняет команду"""
    print(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def main():
    system = platform.system()
    
    # определяем корень проекта (на уровень выше от setup/)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    print("=" * 50)
    print("  🤖 Bot Factory — Установка")
    print(f"  Система: {system}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Папка: {project_root}")
    print("=" * 50)
    print()

    # проверяем Python
    if sys.version_info < (3, 9):
        print("❌ Нужен Python 3.9+")
        print("   https://www.python.org/downloads/")
        input("\nНажми Enter...")
        sys.exit(1)

    # проверяем requirements.txt
    if not os.path.exists("requirements.txt"):
        print("❌ Не найден requirements.txt")
        print("   Запусти из корня проекта: python setup/setup.py")
        input("\nНажми Enter...")
        sys.exit(1)

    # определяем пути
    venv_dir = os.path.join(project_root, "venv")
    
    if system == "Windows":
        pip = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        pip = os.path.join(venv_dir, "bin", "pip")

    # создаём venv
    if not os.path.exists(venv_dir):
        print("[1/3] Создаю виртуальное окружение...")
        if not run(f"{sys.executable} -m venv venv"):
            print("❌ Не удалось создать venv")
            input("\nНажми Enter...")
            sys.exit(1)
    else:
        print("[1/3] Виртуальное окружение уже есть ✓")

    # обновляем pip
    print("[2/3] Обновляю pip...")
    run(f"{pip} install --upgrade pip")

    # ставим зависимости
    print("[3/3] Устанавливаю зависимости (2-5 минут)...")
    if not run(f"{pip} install -r requirements.txt"):
        print("❌ Ошибка установки")
        input("\nНажми Enter...")
        sys.exit(1)

    # готово
    print()
    print("=" * 50)
    print("  ✅ Установка завершена!")
    print("=" * 50)
    print()
    
    if system == "Windows":
        print("  Запуск: setup\\start.bat")
    else:
        print("  Запуск: bash setup/start.sh")
    print("  Потом открой: http://localhost:8000")
    print()
    input("Нажми Enter...")

if __name__ == "__main__":
    main()
