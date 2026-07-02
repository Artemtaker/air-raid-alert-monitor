#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_watcher.py
=================

Стежить за повітряною тривогою в м. Київ і змінює колір терміналу.

Як працює:
  1. Запускається з командного рядка (python alert_watcher.py).
  2. Періодично опитує (за замовчуванням кожні 15 секунд) офіційний API
     https://api.alerts.in.ua/ (потребує токен — див. розділ нижче). Якщо
     токена немає або основне джерело недоступне/перевантажене — переходить
     на безкоштовний публічний агрегатор https://ubilling.net.ua/aerialalerts/
     (проксує ті самі дані, токен не потрібен).
  3. Коли в Києві оголошується тривога — термінал стає червоним і
     виводиться повідомлення з типом загрози (повітряна тривога) та часом.
  4. Коли тривогу відбивають — колір терміналу повертається до звичайного.

Залежності:
  pip install requests colorama alerts-in-ua
  (alerts-in-ua потрібна лише для основного джерела; без неї скрипт працює
  через резервне джерело ubilling)

Запуск:
  python alert_watcher.py
  (зупинити: Ctrl+C — колір терміналу автоматично повернеться до звичайного)

Опційно можна задати іншу локацію через змінну середовища ALERT_LOCATION
(за замовчуванням "м. Київ"), наприклад:
  ALERT_LOCATION="Львівська область" python alert_watcher.py

Основне джерело (alerts.in.ua, через офіційний пакет alerts-in-ua):
  Потребує токен у змінній середовища ALERTS_IN_UA_TOKEN, яку зазвичай
  задає файл .env поряд зі скриптом (див. .env.example). Файл .env у
  .gitignore, тож токен не потрапляє в git. Без токена (або без пакета
  alerts-in-ua) скрипт автоматично працює лише через резервне джерело
  (ubilling).
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

try:
    from alerts_in_ua import Client as AlertsInUaClient
    from alerts_in_ua.errors import ApiError as AlertsInUaApiError, RateLimitError as AlertsInUaRateLimitError
    HAS_ALERTS_IN_UA = True
except ImportError:
    HAS_ALERTS_IN_UA = False
    # Бібліотека опційна: потрібна лише для основного джерела (alerts.in.ua).
    # Без неї (або без токена) скрипт просто працює через резервне джерело.


def load_dotenv(path: str) -> None:
    """Підвантажити KEY=VALUE з .env у os.environ (якщо ключ там ще не задано).

    Без зовнішньої залежності python-dotenv: формат гранично простий, файл —
    локальний і НЕ комітиться в git (див. .gitignore), тож секрети (токени
    API) сюди можна класти напряму, не боячись, що вони підуть на GitHub.
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Локація задається людською назвою (ключ у відповіді обох API), напр.
# "м. Київ".
LOCATION = os.environ.get("ALERT_LOCATION", "м. Київ")

# --- Основне джерело даних: офіційний API alerts.in.ua (через пакет alerts-in-ua) ---
# Потребує токен. Токен читається зі змінної середовища ALERTS_IN_UA_TOKEN,
# яку зазвичай задає файл .env поряд зі скриптом (є в .gitignore — не
# потрапляє в репозиторій).
ALERTS_IN_UA_TOKEN = os.environ.get("ALERTS_IN_UA_TOKEN")

# --- Резервне джерело: безкоштовний агрегатор ubilling.net.ua/aerialalerts ---
# Проксує ті самі дані (alerts.in.ua / ukrainealarm.com / канал "Повітряна
# тривога") і НЕ потребує токена чи реєстрації. Використовується
# автоматично, якщо основне джерело недоступне/перевантажене (429), або
# якщо ALERTS_IN_UA_TOKEN взагалі не задано.
API_URL = "https://ubilling.net.ua/aerialalerts/"

PRIMARY_SOURCE_ENABLED = bool(ALERTS_IN_UA_TOKEN and HAS_ALERTS_IN_UA)

POLL_INTERVAL_SECONDS = 15  # API дозволяє ~2 запити/сек, цього більш ніж достатньо
REQUEST_TIMEOUT = 8

# При 429 (сервер перевантажений, типово під час масових тривог по країні)
# чекаємо довше і збільшуємо паузу експоненційно, щоб не "добивати" сервер
# частими повторами; після успішного запиту пауза повертається до звичайної.
RATE_LIMIT_BACKOFF_START = 30
RATE_LIMIT_BACKOFF_MAX = 300


class RateLimitedError(Exception):
    """Сервер відповів 429 Too Many Requests."""

# Резервне джерело (ubilling) віддає лише сам факт тривоги (alertnow), без
# підтипу загрози, тож для нього завжди показуємо загальну категорію.
ALERT_REASON = "Повітряна тривога"

# Основне джерело (alerts.in.ua) віддає реальний підтип загрози (alert_type)
# — перекладаємо його на людську назву для екрана й статус-рядка.
ALERT_TYPE_NAMES = {
    "air_raid": "Повітряна тривога",
    "artillery_shelling": "Загроза артобстрілу",
    "urban_fights": "Вуличні бої",
    "nuclear": "Загроза ядерної небезпеки",
    "chemical": "Хімічна небезпека",
}

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


def render_alert_screen(reason: str, detail: str = None) -> None:
    """Червоний екран із великим текстом тривоги, відцентрованим по вікну.

    detail — додаткова корисна інформація (нотатки, район, час початку тощо),
    показується звичайним (не збільшеним) рядком під основним текстом.
    """
    cols, rows = shutil.get_terminal_size((80, 25))

    # Усі рядки — великі (подвійна висота й ширина) і центруються однаково,
    # тож стоять рівно один під одним по спільній вертикальній осі.
    lines = ["ТРИВОГА", reason, LOCATION, now_str()]

    content_rows = len(lines) * 2          # кожен великий рядок займає 2 рядки екрана
    extra_rows = 2 if detail else 0        # порожній рядок + сам рядок деталей
    top_pad = max(0, (rows - content_rows - extra_rows) // 2)

    parts = [ANSI_RED_BG + ANSI_WHITE_FG]
    parts.extend([""] * top_pad)           # порожні (червоні) рядки зверху для центру
    for line in lines:
        big = _center_big_line(line, cols)
        parts.append("\033#3" + big)       # верхня половина великих літер
        parts.append("\033#4" + big)       # нижня половина
    if detail:
        detail = detail[:cols]
        pad = max(0, (cols - len(detail)) // 2)
        parts.append("")
        parts.append(" " * pad + detail)
    sys.stdout.write("\r\n".join(parts))
    sys.stdout.flush()


_alerts_in_ua_client = None


def _get_alerts_in_ua_client():
    """Клієнт alerts_in_ua.Client, створений один раз (кешує ETag між опитуваннями)."""
    global _alerts_in_ua_client
    if _alerts_in_ua_client is None:
        _alerts_in_ua_client = AlertsInUaClient(token=ALERTS_IN_UA_TOKEN)
    return _alerts_in_ua_client


def _fetch_status_alerts_in_ua():
    """Опитує основне джерело — офіційна бібліотека alerts_in_ua (потребує токен).

    На відміну від компактного API, get_active_alerts() віддає повні дані по
    кожній тривозі (тип загрози, район, нотатки, час початку), тож reason і
    detail тут значно інформативніші, ніж у резервного джерела.

    RateLimitError/ApiError бібліотеки перетворюються на наші власні винятки
    (RateLimitedError/ValueError), щоб основний цикл обробляв їх однаково
    незалежно від того, яке джерело відповіло.
    """
    try:
        alerts = _get_alerts_in_ua_client().get_active_alerts()
    except AlertsInUaRateLimitError as exc:
        raise RateLimitedError(str(exc)) from exc
    except AlertsInUaApiError as exc:
        raise ValueError(str(exc)) from exc

    active_alerts = [
        alert for alert in alerts.get_alerts_by_location_title(LOCATION)
        if not alert.is_finished()
    ]
    if not active_alerts:
        return False, None, None

    # Кілька одночасних загроз для локації (напр. повітряна тривога +
    # загроза артобстрілу) — показуємо всі, без повторів.
    reason = " + ".join(dict.fromkeys(
        ALERT_TYPE_NAMES.get(alert.alert_type, alert.alert_type) for alert in active_alerts
    ))

    detail_parts = []
    started_times = [alert.started_at for alert in active_alerts if alert.started_at]
    if started_times:
        detail_parts.append("з " + min(started_times).strftime("%H:%M:%S"))
    raions = sorted({alert.location_raion for alert in active_alerts if alert.location_raion})
    if raions:
        detail_parts.append("район: " + ", ".join(raions))
    notes = sorted({alert.notes for alert in active_alerts if alert.notes})
    if notes:
        detail_parts.append("; ".join(notes))
    detail = " · ".join(detail_parts) if detail_parts else None

    return True, reason, detail


def _fetch_status_ubilling():
    """Опитує резервне джерело — ubilling.net.ua/aerialalerts (без токена).

    Агрегатор віддає лише сам факт тривоги (alertnow), без підтипу загрози
    чи будь-яких додаткових даних, тож detail завжди None.
    """
    response = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429:
        # Сервер перевантажений (типово під час масових тривог по всій
        # країні) — сигналізуємо про це окремим типом винятку, щоб основний
        # цикл почекав довше, а не одразу повторював запит.
        raise RateLimitedError("429 Too Many Requests — сервер тимчасово обмежує запити")
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
        return True, ALERT_REASON, None
    return False, None, None


def fetch_alert_status():
    """
    Повертає кортеж (active: bool, reason: str | None, detail: str | None)
    для локації LOCATION.

    reason — людська назва причини тривоги. Основне джерело (alerts.in.ua)
    дає реальний підтип загрози (повітряна тривога / загроза артобстрілу /
    вуличні бої тощо); резервне (ubilling) — лише загальну категорію.
    detail — додаткова інформація (район, час початку, нотатки), доступна
    лише від основного джерела; від резервного завжди None.

    Якщо задано ALERTS_IN_UA_TOKEN і встановлено бібліотеку alerts_in_ua —
    спочатку опитує основне джерело (alerts.in.ua); якщо воно недоступне чи
    перевантажене, переходить на резервне (ubilling). Без токена/бібліотеки
    одразу йде на резервне джерело.
    """
    if not PRIMARY_SOURCE_ENABLED:
        return _fetch_status_ubilling()
    try:
        return _fetch_status_alerts_in_ua()
    except (RateLimitedError, requests.RequestException, KeyError, ValueError) as primary_exc:
        try:
            return _fetch_status_ubilling()
        except Exception:
            raise primary_exc


def print_status_line(alert_active: bool, reason: str = None, detail: str = None, error: str = None) -> None:
    if error:
        print(f"[{now_str()}] Помилка опитування API: {error}")
        return
    if alert_active:
        state = f"ТРИВОГА ({reason})" if reason else "ТРИВОГА"
        if detail:
            state += f" — {detail}"
    else:
        state = "немає тривоги"
    print(f"[{now_str()}] {LOCATION}: {state}")


def main() -> None:
    enable_windows_ansi()
    print(f"Моніторинг тривоги для локації: {LOCATION}")
    if ALERTS_IN_UA_TOKEN and not HAS_ALERTS_IN_UA:
        print(
            "УВАГА: ALERTS_IN_UA_TOKEN задано, але бібліотека 'alerts-in-ua' не "
            "встановлена (pip install alerts-in-ua) — працюємо лише через резервне джерело."
        )
    active_source = "https://api.alerts.in.ua/ (через alerts_in_ua.Client)" if PRIMARY_SOURCE_ENABLED else API_URL
    print(f"Опитування кожні {POLL_INTERVAL_SECONDS} с. Джерело: {active_source}")
    if PRIMARY_SOURCE_ENABLED:
        print(f"Резервне джерело (на випадок збою): {API_URL}")
    print("Зупинити: Ctrl+C\n")

    if AUTOHIDE:
        # Дати вікну з'явитись і одразу згорнути — далі його підніме лише тривога.
        sys.stdout.flush()
        time.sleep(0.3)
        minimize_window()

    previous_alert_state = False  # вважаємо, що на старті тривоги немає
    first_poll = True             # статус без змін друкуємо лише при першому опитуванні
    rate_limit_backoff = RATE_LIMIT_BACKOFF_START

    try:
        while True:
            try:
                alert_active, reason, detail = fetch_alert_status()
            except RateLimitedError as exc:
                print_status_line(False, error=f"{exc} — пауза {rate_limit_backoff} с")
                time.sleep(rate_limit_backoff)
                rate_limit_backoff = min(rate_limit_backoff * 2, RATE_LIMIT_BACKOFF_MAX)
                continue
            except (requests.RequestException, KeyError, ValueError) as exc:
                print_status_line(False, error=str(exc))
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            rate_limit_backoff = RATE_LIMIT_BACKOFF_START  # успішний запит — скинути бекоф

            # Тривога почалась
            if alert_active and not previous_alert_state:
                set_alert_colors()
                set_tab_alert(True)                   # підсвітити саму вкладку
                render_alert_screen(reason, detail)   # великий текст по центру + деталі
                show_window()                          # підняти вікно на передній план

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
                    print_status_line(alert_active, reason=reason, detail=detail)

            previous_alert_state = alert_active
            first_poll = False
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        set_tab_alert(False)
        reset_colors()
        print("\nЗупинено користувачем. Колір терміналу відновлено.")


if __name__ == "__main__":
    main()
