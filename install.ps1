#Requires -Version 5.1
<#
  install.ps1 - інсталятор команди "alarm" (монітор повітряної тривоги).

  Що робить:
    1. Копіює файли застосунку в %USERPROFILE%\bin
    2. Додає цю папку в PATH користувача
    3. Перевіряє наявність Python
    4. За потреби встановлює бібліотеку requests

  Запуск:
    - подвійний клік по install.bat   (найпростіше)
    - або: powershell -ExecutionPolicy Bypass -File install.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "=== Встановлення команди 'alarm' ===" -ForegroundColor Cyan

# --- 1. Папки ---
$source = $PSScriptRoot
$target = Join-Path $env:USERPROFILE "bin"
$files  = @("alert_watcher.py", "alarm.cmd", "run_alert_watcher.bat", "alarm_background.bat", "README.txt")

if (-not (Test-Path $target)) {
    New-Item -ItemType Directory -Path $target | Out-Null
    Write-Host "Створено папку: $target"
}

# --- 2. Копіювання файлів (якщо запускаємось не з самої папки bin) ---
if ($source -and ((Resolve-Path $source).Path -ne (Resolve-Path $target).Path)) {
    foreach ($f in $files) {
        $src = Join-Path $source $f
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $target $f) -Force
            Write-Host "Скопійовано: $f"
        } else {
            Write-Host "УВАГА: поряд з інсталятором немає файлу $f" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "Файли вже у '$target' - копіювання не потрібне."
}

# --- 3. Додати папку в PATH користувача ---
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$target*") {
    $newPath = if ([string]::IsNullOrEmpty($userPath)) { $target } else { $userPath.TrimEnd(';') + ";" + $target }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Додано '$target' до PATH користувача." -ForegroundColor Green
} else {
    Write-Host "'$target' вже є в PATH."
}

# --- 3b. Автозапуск при старті Windows (фоновий, згорнутий режим) ---
Write-Host "`n--- Налаштування автозапуску ---"
$startup   = [Environment]::GetFolderPath("Startup")
$lnkPath   = Join-Path $startup "Alarm - Air Raid Monitor.lnk"
$targetBat = Join-Path $target "alarm_background.bat"

# Прибрати старий ярлик (видиме вікно), якщо лишився від ручного налаштування.
$oldLnk = Join-Path $startup "run_alert_watcher.bat - Ярлик.lnk"
if (Test-Path $oldLnk) { Remove-Item $oldLnk -Force }

if (Test-Path $targetBat) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnkPath)
    $sc.TargetPath       = $targetBat
    $sc.WorkingDirectory = $target
    $sc.WindowStyle      = 7   # запускати згорнутим
    $sc.Description       = "Air raid alert monitor (Kyiv)"
    $sc.Save()
    Write-Host "Автозапуск налаштовано (фоновий режим)." -ForegroundColor Green
} else {
    Write-Host "УВАГА: alarm_background.bat не знайдено - автозапуск пропущено." -ForegroundColor Yellow
}

# --- 4. Перевірка Python ---
Write-Host "`n--- Перевірка Python ---"
$pythonOk = $false
try {
    $ver = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "Python знайдено: $ver" -ForegroundColor Green; $pythonOk = $true }
} catch {}

if (-not $pythonOk) {
    Write-Host "Python НЕ знайдено!" -ForegroundColor Red
    Write-Host "Встанови Python 3 з https://python.org" -ForegroundColor Yellow
    Write-Host "(обов'язково постав галочку 'Add Python to PATH'), потім запусти інсталятор ще раз."
    return
}

# --- 5. Перевірка / встановлення requests ---
Write-Host "`n--- Перевірка бібліотеки requests ---"
& python -c "import requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Встановлюю requests, colorama та alerts-in-ua..."
    & python -m pip install requests colorama alerts-in-ua
} else {
    Write-Host "requests вже встановлено." -ForegroundColor Green
}

# --- 5b. Перевірка / встановлення alerts-in-ua (основне джерело) ---
Write-Host "`n--- Перевірка бібліотеки alerts-in-ua ---"
& python -c "import alerts_in_ua" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Встановлюю alerts-in-ua (основне джерело тривог)..."
    & python -m pip install alerts-in-ua
} else {
    Write-Host "alerts-in-ua вже встановлено." -ForegroundColor Green
}

Write-Host "`n=== Готово! ===" -ForegroundColor Cyan
Write-Host "Відкрий НОВЕ вікно терміналу і набери команду:  alarm"
