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
import shutil
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

# --- Джерело даних: безкоштовний агрегатор ubilling.net.ua/aerialalerts ---
# Проксує офіційні дані (alerts.in.ua / ukrainealarm.com / канал "Повітряна
# тривога") і НЕ потребує токена чи реєстрації. Локація задається людською
# назвою (ключ у відповіді), напр. "м. Київ" — токен не потрібен.
LOCATION = os.environ.get("ALERT_LOCATION", "м. Київ")
API_URL = "https://ubilling.net.ua/aerialalerts/"

POLL_INTERVAL_SECONDS = 10  # API дозволяє ~2 запити/сек, цього більш ніж достатньо
REQUEST_TIMEOUT = 8

# Агрегатор віддає лише сам факт тривоги (alertnow), без підтипу загрози,
# тож показуємо загальну категорію.
ALERT_REASON = "Повітряна тривога"

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
    # OSC 11 змінює САМ фон терміналу — за ним вкладка Windows Terminal (через
    # тему AlarmFollow) теж стає червоною. SGR 41 додатково фарбує клітинки.
    sys.stdout.write("\033]11;#CC0000\007")
    sys.stdout.write(ANSI_RED_BG + ANSI_WHITE_FG)
    sys.stdout.flush()
    clear_screen()
    sys.stdout.write(ANSI_RED_BG + ANSI_WHITE_FG)
    sys.stdout.flush()


def reset_colors() -> None:
    """Повернути термінал до звичайного вигляду."""
    sys.stdout.write("\033]111\007")   # повернути фон терміналу до типового
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()
    clear_screen()
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()


def set_tab_alert(active: bool) -> None:
    """Підсвітити саму вкладку Windows Terminal і змінити її заголовок."""
    if active:
        # ConEmu OSC 9;4 зі станом "помилка" (2) — Windows Terminal малює
        # червоний індикатор прямо у вкладці та на іконці в панелі задач.
        sys.stdout.write("\033]9;4;2;100\007")
        sys.stdout.write(f"\033]0;🔴 ТРИВОГА — {LOCATION}\007")
    else:
        sys.stdout.write("\033]9;4;0;0\007")                 # прибрати індикатор
        sys.stdout.write(f"\033]0;Alert Watcher — {LOCATION}\007")
    sys.stdout.flush()


def _center_big_line(text: str, cols: int) -> str:
    """Відцентрувати рядок для подвійної ширини (кожен символ = 2 клітинки)."""
    cap = max(1, cols // 2)            # скільки символів влазить у подвійній ширині
    text = text[:cap]
    pad = (cap - len(text)) // 2
    return " " * pad + text + " " * (cap - pad - len(text))


def render_alert_screen(reason: str) -> None:
    """Червоний екран із великим текстом тривоги, відцентрованим по вікну."""
    cols, rows = shutil.get_terminal_size((80, 25))

    # Усі рядки — великі (подвійна висота й ширина) і центруються однаково,
    # тож стоять рівно один під одним по спільній вертикальній осі.
    lines = ["ТРИВОГА", reason, LOCATION, now_str()]

    content_rows = len(lines) * 2          # кожен великий рядок займає 2 рядки екрана
    top_pad = max(0, (rows - content_rows) // 2)

    parts = [ANSI_RED_BG + ANSI_WHITE_FG]
    parts.extend([""] * top_pad)           # порожні (червоні) рядки зверху для центру
    for line in lines:
        big = _center_big_line(line, cols)
        parts.append("\033#3" + big)       # верхня половина великих літер
        parts.append("\033#4" + big)       # нижня половина
    sys.stdout.write("\r\n".join(parts))
    sys.stdout.flush()


def fetch_alert_status():
    """
    Повертає кортеж (active: bool, reason: str | None) для локації LOCATION.
    reason — людська назва причини; агрегатор не дає підтипу, тож це завжди
    загальна категорія ALERT_REASON ("Повітряна тривога").
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

    if bool(location_data.get("alertnow", False)):
        return True, ALERT_REASON
    return False, None


def print_status_line(alert_active: bool, reason: str = None, error: str = None) -> None:
    if error:
        print(f"[{now_str()}] Помилка опитування API: {error}")
        return
    if alert_active:
        state = f"ТРИВОГА ({reason})" if reason else "ТРИВОГА"
    else:
        state = "немає тривоги"
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
    first_poll = True             # статус без змін друкуємо лише при першому опитуванні

    try:
        while True:
            try:
                alert_active, reason = fetch_alert_status()
            except (requests.RequestException, KeyError, ValueError) as exc:
                print_status_line(False, error=str(exc))
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Тривога почалась
            if alert_active and not previous_alert_state:
                set_alert_colors()
                set_tab_alert(True)              # підсвітити саму вкладку
                render_alert_screen(reason)      # великий текст по центру
                show_window()                    # підняти вікно на передній план

            # Відбій тривоги
            elif not alert_active and previous_alert_state:
                set_tab_alert(False)             # прибрати підсвітку вкладки
                reset_colors()
                print(f"Відбій тривоги — {LOCATION}")
                print(f"Час: {now_str()}")
                sys.stdout.flush()
                if AUTOHIDE:
                    minimize_window()  # сховати назад до наступної тривоги

            # Без змін статусу — друкуємо лише перший раз, далі мовчимо
            else:
                if first_poll:
                    print_status_line(alert_active, reason=reason)

            previous_alert_state = alert_active
            first_poll = False
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        set_tab_alert(False)
        reset_colors()
        print("\nЗупинено користувачем. Колір терміналу відновлено.")


if __name__ == "__main__":
    main()
