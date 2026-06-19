#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_watcher.py
=================

Стежить за повітряною тривогою в м. Київ і змінює колір терміналу.

Як працює:
  1. Запускається з командного рядка (python alert_watcher.py).
  2. Періодично опитує (за замовчуванням кожні 10 секунд) безкоштовний
     публічний агрегатор https://ubilling.net.ua/aerialalerts/ — він проксує
     дані з alerts.in.ua / ukrainealarm.com / каналу "Повітряна тривога" і
     НЕ потребує реєстрації чи API-токена.
  3. Коли в Києві оголошується тривога — термінал стає червоним і
     виводиться повідомлення з типом загрози (повітряна тривога) та часом.
  4. Коли тривогу відбивають — колір терміналу повертається до звичайного.

Залежності:
  pip install requests colorama

Запуск:
  python alert_watcher.py
  (зупинити: Ctrl+C — колір терміналу автоматично повернеться до звичайного)

Опційно можна задати іншу локацію через змінну середовища ALERT_LOCATION
(за замовчуванням "м. Київ"), наприклад:
  ALERT_LOCATION="Львівська область" python alert_watcher.py
"""

import os
import sys
import time
import datetime

try:
    import requests
except ImportError:
    sys.exit(
        "Не знайдено бібліотеку 'requests'.\n"
        "Встановіть її командою:  pip install requests colorama"
    )

try:
    import colorama
    colorama.init()
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    # На сучасних Windows-терміналах (Windows Terminal, PowerShell 7+) ANSI
    # коди працюють і без colorama, тож просто продовжуємо без неї.

API_URL = "https://ubilling.net.ua/aerialalerts/"
LOCATION = os.environ.get("ALERT_LOCATION", "м. Київ")
POLL_INTERVAL_SECONDS = 10  # API дозволяє ~2 запити/сек, цього більш ніж достатньо
REQUEST_TIMEOUT = 8

# Якщо ALERT_AUTOHIDE=1 (режим автозапуску) — вікно тримається згорнутим і
# саме розгортається лише під час тривоги, після відбою згортається назад.
AUTOHIDE = os.environ.get("ALERT_AUTOHIDE") == "1"

ANSI_RED_BG = "\033[41m"
ANSI_WHITE_FG = "\033[97m"
ANSI_RESET = "\033[0m"


def enable_windows_ansi() -> None:
    """Увімкнути підтримку ANSI escape-кодів у старих консолях Windows (cmd.exe)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def _get_console_hwnd():
    """Дескриптор вікна консолі (працює лише в класичному conhost на Windows)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        return None


def minimize_window() -> None:
    """Згорнути вікно консолі (в режимі AUTOHIDE)."""
    hwnd = _get_console_hwnd()
    if not hwnd:
        return
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except Exception:
        pass


def show_window() -> None:
    """Розгорнути вікно, винести на передній план і блимнути (під час тривоги)."""
    hwnd = _get_console_hwnd()
    if not hwnd:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)        # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.FlashWindow(hwnd, True)
    except Exception:
        pass


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def set_alert_colors() -> None:
    """Зробити термінал червоним і очистити екран, щоб колір заповнив усе вікно."""
    sys.stdout.write(ANSI_RED_BG + ANSI_WHITE_FG)
    sys.stdout.flush()
    clear_screen()
    sys.stdout.write(ANSI_RED_BG + ANSI_WHITE_FG)
    sys.stdout.flush()


def reset_colors() -> None:
    """Повернути термінал до звичайного вигляду."""
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()
    clear_screen()
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()


def fetch_alert_status() -> bool:
    """
    Повертає True, якщо у вказаній локації (LOCATION) зараз активна тривога.
    Кидає виняток при мережевій помилці — обробляється у основному циклі.
    """
    response = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    states = data.get("states", {})
    location_data = states.get(LOCATION)
    if location_data is None:
        raise KeyError(
            f"Локацію '{LOCATION}' не знайдено у відповіді API. "
            f"Доступні локації: {', '.join(states.keys())}"
        )
    return bool(location_data.get("alertnow", False))


def print_status_line(alert_active: bool, error: str = None) -> None:
    if error:
        print(f"[{now_str()}] Помилка опитування API: {error}")
        return
    state = "ТРИВОГА" if alert_active else "немає тривоги"
    print(f"[{now_str()}] {LOCATION}: {state}")


def main() -> None:
    enable_windows_ansi()
    print(f"Моніторинг тривоги для локації: {LOCATION}")
    print(f"Опитування кожні {POLL_INTERVAL_SECONDS} с. Джерело: {API_URL}")
    print("Зупинити: Ctrl+C\n")

    if AUTOHIDE:
        # Дати вікну з'явитись і одразу згорнути — далі його підніме лише тривога.
        sys.stdout.flush()
        time.sleep(0.3)
        minimize_window()

    previous_alert_state = False  # вважаємо, що на старті тривоги немає

    try:
        while True:
            try:
                alert_active = fetch_alert_status()
            except (requests.RequestException, KeyError, ValueError) as exc:
                print_status_line(False, error=str(exc))
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Тривога почалась
            if alert_active and not previous_alert_state:
                set_alert_colors()
                print(f"!!! ПОВІТРЯНА ТРИВОГА — {LOCATION} !!!")
                print(f"Початок: {now_str()}")
                sys.stdout.flush()
                show_window()  # підняти вікно на передній план

            # Відбій тривоги
            elif not alert_active and previous_alert_state:
                reset_colors()
                print(f"Відбій тривоги — {LOCATION}")
                print(f"Час: {now_str()}")
                sys.stdout.flush()
                if AUTOHIDE:
                    minimize_window()  # сховати назад до наступної тривоги

            # Без змін статусу — просто лог у консоль (колір лишається як є)
            else:
                print_status_line(alert_active)

            previous_alert_state = alert_active
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        reset_colors()
        print("\nЗупинено користувачем. Колір терміналу відновлено.")


if __name__ == "__main__":
    main()
