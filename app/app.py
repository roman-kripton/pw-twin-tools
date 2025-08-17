"""
Flask-приложение для мониторинга аккаунтов Perfect World.
Предоставляет веб-интерфейс для:
- Просмотра статуса аккаунтов
- Управления группами
- Активации промокодов
- Обновления данных вручную
"""
import json
import os
import threading
from datetime import datetime
from typing import Dict, List
import logging

from flask import Flask, flash, render_template, request, redirect
from monitor import MarathonMonitor
from models import Database

# Инициализация Flask-приложения
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Автоперезагрузка шаблонов
app.config['DATABASE_URL'] = os.getenv('DATABASE_URL')  # URL базы данных
logger = logging.getLogger(__name__)
# Инициализация подключения к БД
db = Database(app.config['DATABASE_URL'])

# Глобальная переменная для монитора
monitor = None

# =============================================
# Вспомогательные функции
# =============================================

def prepare_accounts_data() -> Dict[str, List[Dict]]:
    """
    Подготовка данных об аккаунтах, сгруппированных по группам.
    
    Returns:
        Словарь с группами и списками аккаунтов
    """
    # Получаем все группы из БД
    groups = db.get_all_groups()
    
    # Инициализируем словарь для данных
    accounts_data = {"Общая": []}  # Группа по умолчанию
    
    # Добавляем все группы из БД
    for group_id, group_name in groups:
        accounts_data[group_name] = []
    
    # Получаем все аккаунты
    account_rows = db.get_accounts()
    
    # Формируем данные для каждого аккаунта
    for row in account_rows:
        username, alias, last_success, server, use_promo, transfer_to_game, group_id, group_name, mdm_coins = row
        
        # Получаем задачи и персонажей аккаунта
        tasks = db.get_account_tasks(username)
        characters_data = db.get_account_characters(username)
        
        # Формируем информацию о персонажах
        characters = {}
        servers = set()
        for char_server, char_name, _, _ in characters_data:
            servers.add(char_server)
            characters.setdefault(char_server, []).append(char_name)

        # Базовые данные аккаунта
        account = {
            "username": username,
            "status": "success" if tasks else "error",  # Статус проверки
            "server": server,
            "mdm_coins": mdm_coins,
            "alias": alias,
            "use_promo": use_promo,
            "transfer_to_game": transfer_to_game,
            "servers": sorted(servers),  # Сортированный список серверов
            "characters": characters,  # Персонажи по серверам
            "last_success": last_success.strftime("%Y-%m-%d %H:%M:%S") if last_success else None
        }
        
        # Добавляем задачи, если есть
        if tasks:
            account["tasks"] = [{
                "name": task[0],
                "x": task[1],
                "y": task[2],
                "percent": task[3],
                "timestamp": task[4].strftime("%Y-%m-%d %H:%M:%S")
            } for task in tasks]
        else:
            account["message"] = "Нет данных о проверке"
        
        # Определяем группу аккаунта
        group = group_name if group_name else "Общая"
        accounts_data[group].append(account)
    
    # Удаляем пустые группы (кроме "Общей")
    for group_name in list(accounts_data.keys()):
        if group_name != "Общая" and not accounts_data[group_name]:
            del accounts_data[group_name]
    
    return accounts_data

# =============================================
# Обработчики маршрутов
# =============================================

@app.route('/')
def status_page():
    """
    Главная страница со статусом всех аккаунтов.
    
    Returns:
        Отрендеренный шаблон status.html
    """
    accounts_data = prepare_accounts_data()
    account_rows = db.get_accounts()
    
    return render_template(
        'status.html', 
        accounts_data=accounts_data,
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Время обновления
        aliases={row[0]: row[1] for row in account_rows if row[1]},  # Словарь алиасов
        groups=db.get_all_groups()  # Список групп
    )

@app.route('/update_group', methods=['POST'])
def update_group():
    """
    Обновление группы аккаунта.
    
    Returns:
        Перенаправление на главную страницу
    """
    username = request.form['username']
    group_id = request.form['group_id']
    
    try:
        # Преобразуем group_id в int или None
        group_id = int(group_id) if group_id != "null" else None
    except ValueError:
        group_id = None
    
    db.update_account_group(username, group_id)
    return redirect('/')

@app.route('/get_characters')
def get_characters():
    """
    Получение списка персонажей аккаунта на конкретном сервере.
    
    Returns:
        JSON с персонажами или ошибкой
    """
    username = request.args.get('username')
    server = request.args.get('server')
    
    if not username or not server:
        return json.dumps({"error": "Не указаны параметры"}), 400
    
    characters = db.get_account_characters_for_server(username, server)
    return json.dumps({
        "characters": [char[0] for char in characters]
    })

@app.route('/refresh_account', methods=['POST'])
def refresh_account():
    """
    Ручное обновление данных аккаунта.
    
    Returns:
        JSON с результатом обновления
    """
    username = request.form['username']
    
    # Проверяем, не выполняется ли уже проверка
    if monitor and monitor.is_checking:
        return json.dumps({
            "status": "error", 
            "message": "В данный момент выполняется другая проверка"
        }), 423
    
    try:
        cookie_file = f"{username}.pkl"
        if not os.path.exists(os.path.join(monitor.cookies_dir, cookie_file)):
            return json.dumps({
                "status": "error", 
                "message": "Файл с куками не найден"
            }), 404
        
        # Выполняем проверку
        account_data = monitor.check_account(cookie_file)
        return json.dumps({
            "status": "success",
            "data": account_data
        })
    except Exception as e:
        return json.dumps({
            "status": "error", 
            "message": str(e)
        }), 500
    
@app.route('/delete_account', methods=['POST'])
def delete_account():
    """
    Удаление аккаунта и связанных данных.
    
    Returns:
        Перенаправление на главную страницу
    """
    username = request.form['username']
    
    try:
        # Удаляем из БД в транзакции
        with db._get_connection() as conn:
            with conn.cursor() as cursor:
                # Сначала удаляем задачи
                cursor.execute("DELETE FROM tasks WHERE username = %s", (username,))
                # Затем сам аккаунт
                cursor.execute("DELETE FROM accounts WHERE username = %s", (username,))
                conn.commit()
        
        # Удаляем файл с куками
        cookie_file = os.path.join('app', 'cookies', f"{username}.pkl")
        if os.path.exists(cookie_file):
            os.remove(cookie_file)
        
        return redirect('/')
    except Exception as e:
        flash(f"Ошибка удаления аккаунта: {str(e)}", "error")
        return redirect('/')
    
@app.route('/update_account_setting', methods=['POST'])
def update_account_setting():
    """
    Обновление настроек аккаунта.
    
    Returns:
        JSON с результатом операции
    """
    try:
        username = request.form['username']
        field = request.form['field']
        value = request.form['value']
        
        db.update_account_setting(username, field, value)
        return json.dumps({"status": "success"})
    
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return json.dumps({"status": "error", "message": "Внутренняя ошибка сервера"}), 500

@app.route('/activate_promo', methods=['POST'])
def activate_promo():
    """
    Активация промокода для подходящих аккаунтов.
    
    Returns:
        JSON с результатом активации
    """
    promo_code = request.form['promo_code']
    if not promo_code:
        return json.dumps({
            "status": "error", 
            "message": "Промокод не может быть пустым"
        }), 400
    
    # Проверяем статус промокода
    promo_status = db.get_promo_code_status(promo_code)
    if promo_status == 'expired':
        return json.dumps({
            "status": "error", 
            "message": "Этот промокод уже истек"
        })
    elif promo_status == 'invalid':
        return json.dumps({
            "status": "error", 
            "message": "Этот промокод недействителен"
        })
    
    # Получаем аккаунты для активации
    accounts = db.get_accounts_for_promo_activation(promo_code)
    if not accounts:
        return json.dumps({
            "status": "error", 
            "message": "Нет аккаунтов для активации промокода"
        })
    
    try:
        # Запускаем активацию
        result = monitor.activate_promo_code(promo_code, accounts)
        return json.dumps({
            "status": "success",
            "activated": result['activated'],
            "errors": result['errors']
        })
    except Exception as e:
        return json.dumps({
            "status": "error", 
            "message": str(e)
        }), 500
    
@app.route('/transfer_gifts', methods=['POST'])
def transfer_gifts():
    """Передача подарков для одного аккаунта."""
    username = request.form['username']
    
    if not username:
        logger.error(f"Не указано имя пользователя")
        return json.dumps({"status": "error", "message": "Не указано имя пользователя"}), 400
    
    try:
        if monitor and monitor.is_checking:           
            logger.error(f"{username} - В данный момент выполняется другая проверка")
            return json.dumps({
                "status": "error", 
                "message": "В данный момент выполняется другая проверка"
            }), 423
        
        cookie_file = f"{username}.pkl"
        if not os.path.exists(os.path.join(monitor.cookies_dir, cookie_file)):            
            logger.error(f"{username} - Файл с куками не найден")
            return json.dumps({
                "status": "error", 
                "message": "Файл с куками не найден"
            }), 404
        
        result = monitor.transfer_gifts_to_game(cookie_file)
        if result.get('status') == 'error':
            logger.error(result.get('message'))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({
            "status": "error", 
            "message": str(e)
        }), 500

@app.route('/transfer_all_gifts', methods=['POST'])
def transfer_all_gifts():
    """Передача подарков для всех аккаунтов."""
    try:
        if monitor and monitor.is_checking:
            return json.dumps({
                "status": "error", 
                "message": "В данный момент выполняется другая проверка"
            }), 423
        
        cookie_files = [f for f in os.listdir(monitor.cookies_dir) if f.endswith('.pkl')]
        transferred = 0
        errors = 0
        
        for cookie_file in cookie_files:
            try:
                result = monitor.transfer_gifts_to_game(cookie_file)
                
                if result.get('status') == 'success':
                    transferred += 1
                elif result.get('status') != 'skip':
                    logger.error(result.get('message'))
                    errors += 1
            except Exception as e:
                errors += 1
                print(f"Ошибка передачи подарков для {cookie_file}: {e}")
        
        return json.dumps({
            "status": "success",
            "transferred": transferred,
            "errors": errors
        })
    except Exception as e:
        return json.dumps({
            "status": "error", 
            "message": str(e)
        }), 500   
@app.route('/create_group', methods=['POST'])
def create_group():
    """
    Создание новой группы.
    
    Returns:
        Перенаправление на главную страницу
    """
    group_name = request.form['group_name']
    if group_name and group_name != "Общая":
        db.create_group(group_name)
    return redirect('/')

@app.route('/delete_group', methods=['POST'])
def delete_group():
    """
    Удаление группы.
    
    Returns:
        Перенаправление на главную страницу
    """
    group_id = request.form['group_id']
    if group_id:
        db.delete_group(group_id)
    return redirect('/')

@app.route('/update_alias', methods=['POST'])
def update_alias():
    """
    Обновление алиаса аккаунта.
    
    Returns:
        Перенаправление на главную страницу
    """
    username = request.form['username']
    alias = request.form['alias'] or None  # Пустой алиас преобразуем в None
    
    # Получаем текущий group_id для сохранения
    account_rows = db.get_accounts()
    current_group_id = None
    for row in account_rows:
        if row[0] == username:
            current_group_id = row[3]
            break
    
    # Сохраняем с сохранением текущей группы
    db.save_account_data(username, alias=alias)
    return redirect('/')

# =============================================
# Запуск приложения
# =============================================

def run_monitor():
    """Запуск монитора в отдельном потоке."""
    global monitor
    monitor = MarathonMonitor(headless=False)
    monitor.start_scheduled_monitoring()

if __name__ == '__main__':
    # Запускаем монитор только в основном процессе (не в релоадере)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        monitor_thread = threading.Thread(target=run_monitor, daemon=True)
        monitor_thread.start()
    
    # Запуск Flask-приложения
    app.run(host='0.0.0.0', port=5009)