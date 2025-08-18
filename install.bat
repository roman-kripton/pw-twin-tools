@echo off
chcp 65001 > nul
SETLOCAL EnableDelayedExpansion

:: Определение цветов
set ESC=[
set GREEN=%ESC%32m
set YELLOW=%ESC%33m
set RED=%ESC%31m
set BLUE=%ESC%34m
set MAGENTA=%ESC%35m
set CYAN=%ESC%36m
set WHITE=%ESC%37m
set RESET=%ESC%0m

echo %BLUE%Проверка и установка необходимых компонентов...%RESET%
echo.

:: 1. Проверка Python 3.11
echo %YELLOW%[1/4]%RESET% %CYAN%Проверка Python 3.11...%RESET%
python --version 2>nul | find "3.11" >nul
if %errorlevel% neq 0 (
    echo %RED%Python 3.11 не найден.%RESET% %GREEN%Устанавливаем...%RESET%
    winget install -e --id Python.Python.3.11
    echo %GREEN%Установка завершена. Пожалуйста, перезапустите скрипт.%RESET%
    pause
    exit /b
) else (
    echo %GREEN%Python 3.11 уже установлен.%RESET%
)

:: 2. Проверка Docker
echo %YELLOW%[2/4]%RESET% %CYAN%Проверка Docker...%RESET%
docker --version 2>nul
if %errorlevel% neq 0 (
    echo %RED%Docker не найден.%RESET% %GREEN%Устанавливаем...%RESET%
    winget install -e --id Docker.DockerDesktop
    echo %GREEN%Установка завершена. Запустите Docker Desktop и перезапустите скрипт.%RESET%
    pause
    exit /b
) else (
    echo %GREEN%Docker уже установлен.%RESET%
)

:: 3. Проверка Git
echo %YELLOW%[3/4]%RESET% %CYAN%Проверка Git...%RESET%
git --version 2>nul
if %errorlevel% neq 0 (
    echo %RED%Git не найден.%RESET% %GREEN%Устанавливаем...%RESET%
    winget install -e --id Git.Git
    echo %GREEN%Установка завершена. Пожалуйста, перезапустите скрипт.%RESET%
    pause
    exit /b
) else (
    echo %GREEN%Git уже установлен.%RESET%
)

:: 4. Клонирование/обновление репозитория
echo %YELLOW%[4/4]%RESET% %CYAN%Работа с репозиторием...%RESET%
set REPO_URL=https://github.com/roman-kripton/pw-twin-tools.git
set REPO_DIR=pw-twin-tools

if exist "%REPO_DIR%" (
    echo %MAGENTA%Репозиторий найден.%RESET% %GREEN%Обновляем...%RESET%
    cd "%REPO_DIR%"
    git pull
    cd ..
) else (
    echo %MAGENTA%Репозиторий не найден.%RESET% %GREEN%Клонируем...%RESET%
    git clone %REPO_URL%
)

:: Установка зависимостей Python
echo %CYAN%Установка Python зависимостей...%RESET%
cd "%REPO_DIR%"
pip install -r requirements-for-acc-tools.txt

:: Запуск Docker Compose
echo %CYAN%Запуск Docker Compose...%RESET%
docker compose up -d --build

echo.
echo %GREEN%Все операции завершены успешно!%RESET%
pause