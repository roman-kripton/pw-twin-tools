"""
Модуль мониторинга аккаунтов Perfect World.
Отвечает за:
- Проверку статуса марафона
- Активацию промокодов
- Сбор информации о персонажах
- Взаимодействие через Selenium
"""

import asyncio
import re
import pickle
import os
import time
import threading
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Импорты Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.common.exceptions import NoSuchElementException

from requests.exceptions import ConnectionError as RequestsConnectionError

# Импорты Telegram
import telegram
from telegram.error import TelegramError

# Импорты для планировщика
import schedule

# Локальные импорты
from models import Database

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log'),
        logging.StreamHandler()
    ]
)

class MarathonMonitor:
    """Класс для мониторинга аккаунтов Perfect World."""

    def __init__(self, headless: bool = True):
        """
        Инициализация монитора.
        
        Args:
            headless: Флаг запуска браузера в headless-режиме
        """
        self.cookies_dir = os.path.join('app', 'cookies')  # Директория для хранения куков
        self.headless = headless  # Режим работы браузера
        os.makedirs(self.cookies_dir, exist_ok=True)
        self.running = False  # Флаг работы монитора
        self.selenium_url = os.getenv('SELENIUM_URL', 'http://selenium:4444/wd/hub')  # URL Selenium
        self.db = Database(os.getenv('DATABASE_URL'))  # Подключение к БД
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  # Токен Telegram бота
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')  # ID чата Telegram
        self.is_checking = False  # Флаг выполнения проверки
        # URL страницы марафона (из настроек или по умолчанию)
        self.marathon_url = self.db.get_setting('marathon_url', 'https://pwonline.ru/supermarathon2.php')
        
        self.ensure_selenium_ready()  # Проверка доступности Selenium
        logger.info(f"Selenium URL: {self.selenium_url}")

    # =============================================
    # Методы уведомлений
    # =============================================
    
    def send_telegram_notification(self, message: str) -> None:
        """
        Отправка уведомления в Telegram.
        
        Args:
            message: Текст сообщения для отправки
        """
        if not self.bot_token or not self.chat_id:
            return
        
        async def async_send():
            """Асинхронная отправка сообщения."""
            try:
                bot = telegram.Bot(token=self.bot_token)
                await bot.send_message(
                    chat_id=self.chat_id, 
                    text=self.escape_markdown_v2(message),
                    parse_mode="MarkdownV2"
                )
            except TelegramError as e:
                logger.error(f"Ошибка отправки в Telegram: {e}")
        
        try:
            asyncio.run(async_send())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(async_send())

    def _send_grouped_reports(self, groups: dict, total_accounts: int, expiring_gifts: dict) -> None:
        """Отправляет отчеты по группам с учетом ограничений Telegram."""
        # Общая статистика
        success = sum(len(g['success']) for g in groups.values())
        errors = sum(len(g['errors']) for g in groups.values())
        
        header = (
            "\n"
            "📊 ОТЧЕТ О ПРОВЕРКЕ АККАУНТОВ\n"
            "────────────────────────────\n"
            f"🔹 Всего проверено: {total_accounts}\n"
            f"✅ Успешно: {success}\n"
            f"❌ Ошибки: {errors}\n"
        )

        self.send_telegram_notification(header)
        
        # Отправляем данные по группам
        for group_name, group_data in groups.items():
            if not any(group_data.values()):  # Пропускаем пустые группы
                continue
                
            message_parts = []
            message_parts.append(f"\n🏷️ ГРУППА: {group_name.upper()}\n```")
            
            # Добавляем успешные проверки
            if group_data['success']:
                message_parts.append("\n✅ УСПЕШНО:\n" + "\n".join(group_data['success']))
            
            # Добавляем изменения
            if group_data['changes']:
                message_parts.append("\n🎯 ИЗМЕНЕНИЯ:")
                for change in group_data['changes']:
                    if len("\n".join(message_parts) + "\n" + change) > 3500:  # Лимит Telegram
                        message_parts.append("\n```")
                        self.send_telegram_notification("\n".join(message_parts))
                        message_parts = [f"```\n🏷️ ГРУППА: {group_name.upper()} (продолжение)\n"]
                    message_parts.append("\n" + change)
            
            # Добавляем ошибки
            if group_data['errors']:
                message_parts.append("\n⚠️ ОШИБКИ:\n" + "\n".join(group_data['errors']))
            
            message_parts.append("\n```")
            full_message = "\n".join(message_parts)
            
            # Разбиваем слишком длинные сообщения
            if len(full_message) > 4096:  # Максимальный размер сообщения в Telegram
                parts = []
                current_part = []
                current_length = 0
                
                for line in message_parts:
                    line_length = len(line) + 1  # +1 для символа новой строки
                    if current_length + line_length > 4000:  # Оставляем запас
                        parts.append("\n".join(current_part))
                        current_part = []
                        current_length = 0
                    current_part.append(line)
                    current_length += line_length
                
                if current_part:
                    parts.append("\n".join(current_part))
                
                for part in parts:
                    self.send_telegram_notification(part)
                    time.sleep(1)  # Задержка между сообщениями
            else:
                self.send_telegram_notification(full_message)

        # Отправляем уведомления об истекающих подарках
        if expiring_gifts:
            gifts_message = ["```\n🎁 ПОДАРКИ СКОРО ИСТЕКАЮТ:"]
            for username, gifts in expiring_gifts.items():
                gifts_message.append(f"\n👤 {username}:")
                for gift in gifts:
                    gifts_message.append(f"  • {gift['name']} (до {gift['expires']})")
            gifts_message.append("```")
            self.send_telegram_notification("\n".join(gifts_message))

    def escape_markdown_v2(self, text: str) -> str:
        # Сначала экранируем все спецсимволы
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        escaped = []
        i = 0
        n = len(text)
        
        while i < n:
            # Пропускаем валидные блоки кода ```
            if text.startswith('```', i):
                escaped.append('```')
                i += 3
                # Ищем закрывающие ```
                end = text.find('```', i)
                if end == -1:
                    escaped.append(text[i:])
                    break
                escaped.append(text[i:end])
                escaped.append('```')
                i = end + 3
            else:
                char = text[i]
                if char in escape_chars:
                    escaped.append(f'\\{char}')
                else:
                    escaped.append(char)
                i += 1
        
        return ''.join(escaped)
    # =============================================
    # Методы работы с Selenium
    # =============================================
    
    def ensure_selenium_ready(self) -> None:
        """Ожидание готовности Selenium сервера."""
        timeout = 600000000000000000  # Максимальное время ожидания (сек)
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.selenium_url}/status")
                if response.json().get('value', {}).get('ready'):
                    logger.info("Selenium Grid готов к работе")
                    return
            except RequestsConnectionError:
                logger.warning("Ожидание доступности Selenium...")
                time.sleep(5)
        
        raise ConnectionError("Selenium не стал доступен за отведенное время")

    def get_driver(self) -> WebDriver:
        """
        Создание и настройка веб-драйвера.
        
        Returns:
            Настроенный экземпляр WebDriver
            
        Raises:
            ConnectionError: При невозможности подключиться к Selenium
        """
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        max_attempts = 5  # Максимальное количество попыток
        attempt = 0
        
        while attempt < max_attempts:
            try:
                driver = webdriver.Remote(
                    command_executor=self.selenium_url,
                    options=chrome_options
                )
                driver.set_page_load_timeout(30)  # Таймаут загрузки страницы
                driver.implicitly_wait(10)  # Неявное ожидание элементов
                return driver
            except WebDriverException as e:
                logger.error(f"Ошибка создания драйвера: {str(e)}")
                attempt += 1
                time.sleep(2)
        
        raise ConnectionError(f"Не удалось подключиться к Selenium после {max_attempts} попыток")
    
    # =============================================
    # Методы парсинга данных
    # =============================================
    
    @staticmethod
    def parse_progress(progress_str: str) -> Tuple[int, int, float]:
        """
        Парсинг строки прогресса.
        
        Args:
            progress_str: Строка прогресса в формате "X/Y"
            
        Returns:
            Кортеж (текущее значение, максимум, процент)
        """
        try:
            x, y = map(int, progress_str.split('/'))
            return (x, y, (x/y)*100)
        except (ValueError, ZeroDivisionError):
            return (0, 1, 0)

    @staticmethod
    def parse_character_info(char_text: str) -> Optional[Dict[str, Any]]:
        """
        Парсинг информации о персонаже.
        
        Args:
            char_text: Текст с информацией о персонаже
            
        Returns:
            Словарь с данными персонажа или None
        """
        try:
            # Формат: "ИмяПерсонажа (Класс, уровень: XX)"
            match = re.match(r'^(.+?)\s*\((.+?),\s*уровень:\s*(\d+)\)$', char_text)
            if match:
                return {
                    "name": match.group(1).strip(),
                    "class": match.group(2).strip(),
                    "level": int(match.group(3))
                }
            return {
                "name": char_text.strip(),
                "class": None,
                "level": None
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга персонажа: {e}")
            return None

    def _get_progress_bar(self, percent: float) -> str:
        """Генерирует текстовый progress-bar.
        
        Args:
            percent: Процент выполнения (0-100)
            
        Returns:
            Строка с progress-bar
        """
        filled = '█'
        empty = '░'
        width = 10  # Ширина progress-bar
        logger.info(percent)
        logger.info(int(round(percent / 100 * width)))
        filled_count = int(round(percent / 100 * width))        
        logger.info(filled * filled_count + empty * (width - filled_count))
        return filled * filled_count + empty * (width - filled_count)
    
    def _parse_gift_date(self, date_text: str) -> Optional[datetime]:
        """Парсит дату из строки подарка."""
        try:
            # Формат: "(до 20:31 16.07.2025)"
            date_str = date_text.replace("(до ", "").replace(")", "")
            return datetime.strptime(date_str, "%H:%M %d.%m.%Y")
        except Exception as e:
            logger.error(f"Ошибка парсинга даты '{date_text}': {e}")
            return None
    # =============================================
    # Методы сбора данных
    # =============================================
    
    def get_marathon_data(self, driver: WebDriver, username: str) -> List[Dict[str, Any]]:
        """
        Сбор данных о марафоне для аккаунта.
        
        Args:
            driver: Экземпляр WebDriver
            username: Имя аккаунта
            
        Returns:
            Список задач марафона
        """
        try:
            # Сначала собираем информацию о персонажах
            self.collect_characters_info(driver, username)
            
            # Возвращаемся на страницу марафона
            driver.get(self.marathon_url)
            
            # Ожидаем загрузки страницы
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@class='season_marathon']/div"))
            )
            
            tasks = []
            marathon_divs = driver.find_elements(By.XPATH, "//div[@class='season_marathon']/div")
            
            # Парсим каждую задачу
            for task_div in marathon_divs:
                try:
                    name = task_div.find_element(By.XPATH, ".//div[@class='info']/b").text
                    progress = task_div.find_element(By.XPATH, ".//div[@class='progress']").text
                    x, y, percent = self.parse_progress(progress)
                    tasks.append({
                        "name": name,
                        "progress": progress,
                        "x": x,
                        "y": y,
                        "percent": percent
                    })
                except Exception as e:
                    logger.error(f"Ошибка парсинга задания: {e}")
            
            return tasks
        except Exception as e:
            logger.error(f"Ошибка сбора данных марафона: {e}")
            return []

    def get_mdm_coins(self, driver: WebDriver) -> str:
        """
        Получение количества MDM монет.
        
        Args:
            driver: Экземпляр WebDriver
            
        Returns:
            Количество монет или "0" при ошибке
        """
        try:
            driver.get("https://pwonline.ru/chests2.php")
            coins_element = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, 
                    "//div[@class='chest_shop']/div[@class='shop_filter_block']/div[@class='points_info']/strong"))
            )
            return coins_element.text.strip()
        except Exception as e:
            logger.error(f"Ошибка получения MDM монет: {e}")
            return "0"

    def collect_characters_info(self, driver: WebDriver, username: str) -> None:
        """
        Сбор информации о персонажах аккаунта.
        
        Args:
            driver: Экземпляр WebDriver
            username: Имя аккаунта
        """

        # Проверка пустой корзины
        try:
            driver.get("https://pwonline.ru/promo_items.php")
            time.sleep(2)  # Краткая пауза для загрузки
            empty_cart = driver.find_elements(By.XPATH, 
                "//div[@id='content_top']/h2[contains(text(), 'Ваша корзина с подарками пуста')]")
            if empty_cart:
                logger.info("Корзина пуста - пропускаем сбор персонажей")
                return
        except:
            pass  # Игнорируем ошибки проверки корзины

        try:            
            # Ожидаем загрузки селектора серверов
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//select[contains(@class, 'js-shard')]"))
                )
            except TimeoutException:
                logger.error("Селектор серверов не найден")
                return
                
            # Получаем список серверов
            server_select = driver.find_element(By.XPATH, 
                "//div[@class='char_selector']/select[@class='js-shard']")
            servers = [option.text for option in server_select.find_elements(By.TAG_NAME, "option") if option.text]
            
            characters = {}
            
            # Для каждого сервера получаем персонажей
            for server in servers:
                # Выбираем сервер
                for option in server_select.find_elements(By.TAG_NAME, "option"):
                    if option.text == server:
                        option.click()
                        break
                
                time.sleep(1)  # Пауза для загрузки персонажей
                
                # Получаем список персонажей
                char_select = driver.find_element(By.XPATH, 
                    "//div[@class='char_selector']/select[@class='js-char']")
                char_options = char_select.find_elements(By.TAG_NAME, "option")
                
                # Парсим информацию о персонажах
                for option in char_options:
                    if option.text:
                        char_info = self.parse_character_info(option.text)
                        if char_info:
                            characters.setdefault(server, []).append(char_info)
            
            # Сохраняем в базу данных
            if username and characters:
                self.db.save_account_characters(username, characters)           
        
            
        except Exception as e:
            logger.error(f"Ошибка сбора персонажей: {e}") 
            
    # =============================================
    # Методы проверки аккаунтов
    # =============================================
    
    def check_account(self, cookie_file: str, skip_check: bool = False) -> Dict[str, Any]:
        """
        Проверка статуса одного аккаунта.
        
        Args:
            cookie_file: Имя файла с куками
            skip_check: Пропуск проверки занятости
            
        Returns:
            Словарь с результатами проверки
            
        Raises:
            Exception: Если уже выполняется другая проверка
        """
        if not skip_check and self.is_checking:
            raise Exception("Уже выполняется другая проверка")
        
        try:
            self.is_checking = True
            username = cookie_file[:-4]  # Убираем расширение .pkl
            logger.info(f"Проверка аккаунта: {username}")

            # Загрузка куков из файла
            with open(os.path.join(self.cookies_dir, cookie_file), 'rb') as f:
                cookies = pickle.load(f)
            
            driver = self.get_driver()
            try:
                # Установка куков
                driver.get("https://pwonline.ru/")
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as e:
                        logger.warning(f"Ошибка добавления куки: {str(e)}")
                
                # Проверка авторизации
                driver.get("https://pwonline.ru/supermarathon2.php")
                if "Войти" in driver.title:
                    return {
                        "username": username,
                        "status": "error",
                        "message": "Ошибка авторизации"
                    }
                
                # Сбор данных
                tasks = self.get_marathon_data(driver, username)
                mdm_coins = self.get_mdm_coins(driver)
                
                if not tasks:
                    return {
                        "username": username,
                        "status": "error",
                        "message": "Не удалось получить данные марафона"
                    }
                
                # Сохранение в БД
                timestamp = datetime.now()
                self.db.save_account_data(username, last_success=timestamp, mdm_coins=mdm_coins)
                
                for task in tasks:
                    self.db.save_task_data(
                        username,
                        task['name'],
                        task['x'],
                        task['y'],
                        task['percent'],
                        timestamp
                    )
                # Проверяем подарки
                gifts = self._check_account_gifts(driver, username)
                    
                return {
                    "username": username,
                    "status": "success",
                    "mdm_coins": mdm_coins,
                    "tasks": tasks,
                    "gifts": gifts
                }
                
            finally:
                driver.quit()  # Всегда закрываем драйвер
                
        except Exception as e:
            logger.error(f"Ошибка проверки аккаунта {username}: {str(e)}")
            return {
                "username": username,
                "status": "error",
                "message": f"Ошибка загрузки куков: {str(e)}"
            }   
        finally:
            self.is_checking = False

    def check_all_accounts(self) -> None:
        """Проверка всех аккаунтов с сохраненными куками."""
        if self.is_checking:
            logger.warning("Попытка запуска при уже выполняющейся проверке")
            return
            
        try:
            logger.info("Запуск проверки всех аккаунтов")
            self.is_checking = True
            accounts_data = []
            cookie_files = [f for f in os.listdir(self.cookies_dir) if f.endswith('.pkl')]
            
            if not cookie_files:
                logger.warning("Не найдено файлов с куками")
                self.send_telegram_notification("⚠️ Нет файлов с куками для проверки")
                return
            
            # Получаем предыдущие данные с информацией о группах
            previous_data = {}
            groups = {}
            for username, alias, _, _, _, _, group_id, group_name, mdm_coins, tasks in self.db.get_accounts_with_tasks_and_groups():
                group_key = group_name or "Без группы"
                previous_data[username] = {
                    'alias': alias,
                    'group_id': group_id,
                    'group_name': group_key,
                    'mdm_coins': mdm_coins,
                    'tasks': {task[0]: (task[1], task[2]) for task in tasks} if tasks else {}
                }
                if group_key not in groups:
                    groups[group_key] = {
                        'success': [],
                        'errors': [],
                        'changes': []
                    }

            # Словарь для хранения истекающих подарков
            expiring_gifts = {}

            # Проверяем аккаунты
            for cookie_file in cookie_files:
                account_data = self.check_account(cookie_file, skip_check=True)
                accounts_data.append(account_data)
                
                username = account_data['username']
                prev_data = previous_data.get(username, {})
                group_name = prev_data.get('group_name', "Без группы")
                display_name = account_data.get('alias', username)
                
                if account_data['status'] != 'success':
                    groups[group_name]['errors'].append(
                        f"🔴 {display_name}: {account_data['message']}"
                    )
                    continue
                    
                groups[group_name]['success'].append(f"🟢 {display_name}")
                
                # Проверяем изменения
                changes = []
                current_mdm = account_data.get('mdm_coins', '0')
                prev_mdm = prev_data.get('mdm_coins', '0')
                if current_mdm != prev_mdm:
                    try:
                        diff = int(current_mdm) - int(prev_mdm)
                        changes.append(
                            f"💰 Монеты МДМ: {'🔼 +' if diff > 0 else '🔽 '}{abs(diff)} "
                            f"({prev_mdm} → {current_mdm})"
                        )
                    except ValueError:
                        changes.append(f"💰 Монеты МДМ: {current_mdm} (было {prev_mdm})")
                
                task_changes = []
                current_tasks = {task['name']: (task['x'], task['y']) for task in account_data.get('tasks', [])}
                prev_tasks = prev_data.get('tasks', {})
                
                for task_name, (current_x, current_y) in current_tasks.items():
                    if task_name in prev_tasks:
                        prev_x, prev_y = prev_tasks[task_name]
                        if current_x != prev_x or current_y != prev_y:
                            progress = current_x/current_y*100
                            progress_bar = self._get_progress_bar(progress)
                            diff = current_x - prev_x
                            task_changes.append(
                                f"    {progress_bar} {task_name}: "
                                f"{current_x}/{current_y} "
                                f"({'🔼 +' if diff > 0 else ''}{diff if diff != 0 else ''})"
                            )
                    else:
                        progress_bar = self._get_progress_bar(0)
                        task_changes.append(f"    {progress_bar} {task_name}: {current_x}/{current_y} (новое)")
                
                if task_changes:
                    changes.append("📝 Задания:\n" + "\n".join(task_changes))
                
                if changes:
                    groups[group_name]['changes'].append(
                        f"✨ {display_name} ({username}):\n" + 
                        "\n".join(changes)
                    )
                
                # Добавляем истекающие подарки в словарь
                if 'gifts' in account_data  and account_data['gifts']:
                    expiring_gifts[username] = account_data['gifts']
            
            # Формируем сообщения с учетом ограничений Telegram
            self._send_grouped_reports(groups, len(accounts_data), expiring_gifts)
            
            logger.info(f"Проверка завершена. Всего: {len(accounts_data)}")
        finally:
            self.is_checking = False

    # =============================================
    # Методы работы с промокодами
    # =============================================
    
    def activate_promo_code(self, promo_code: str, accounts: List[str]) -> Dict[str, int]:
        """
        Активация промокода для списка аккаунтов.
        
        Args:
            promo_code: Промокод для активации
            accounts: Список имен аккаунтов
            
        Returns:
            Словарь с результатами (успешно, ошибки)
        """
        activated = 0
        errors = 0
        global_promo_status = 'active'  # Глобальный статус промокода
        
        for username in accounts:
            if global_promo_status != 'active':
                # Промокод уже недействителен
                self.db.save_account_promo_code(username, promo_code, 'failed', 'promo_expired')
                errors += 1
                continue
                
            try:
                cookie_file = f"{username}.pkl"
                with open(os.path.join(self.cookies_dir, cookie_file), 'rb') as f:
                    cookies = pickle.load(f)
                
                driver = self.get_driver()
                try:
                    # Авторизация
                    driver.get("https://pwonline.ru/")
                    for cookie in cookies:
                        try:
                            driver.add_cookie(cookie)
                        except Exception as e:
                            logger.warning(f"Ошибка добавления куки: {str(e)}")
                    
                    # Активация промокода
                    driver.get(f"https://pw.mail.ru/pin.php?do=activate&game_account=1&pin={promo_code}")
                    
                    # Проверка результата
                    error_div = driver.find_elements(By.XPATH, 
                        "//div[@id='content_body']/div[@class='m_error']")
                    if error_div:
                        error_text = error_div[0].text
                        logger.error(f"Ошибка активации: {error_text}")
                        
                        if "Пин-код уже активирован" in error_text:
                            self.db.save_account_promo_code(username, promo_code, 'already_activated')
                            activated += 1
                        elif "Некорректный пин-код" in error_text:
                            self.db.save_promo_code_status(promo_code, 'invalid')
                            global_promo_status = 'invalid'
                            errors += 1
                        elif "Время действия пин-кода истекло" in error_text:
                            self.db.save_promo_code_status(promo_code, 'expired')
                            global_promo_status = 'expired'
                            errors += 1
                        else:
                            errors += 1
                    else:
                        # Успешная активация
                        self.db.save_account_promo_code(username, promo_code, 'success')
                        activated += 1
                finally:
                    driver.quit()
                    
            except Exception as e:
                logger.error(f"Ошибка активации для {username}: {str(e)}")
                errors += 1
        
        return {'activated': activated, 'errors': errors}

    def transfer_promo_to_game(self, driver, promo_code, character_name, server):
        try:
            # Здесь реализуйте логику перевода промокода в игру
            # Это будет зависеть от конкретного интерфейса игры
            pass
        except Exception as e:
            logger.error(f"Ошибка перевода промокода в игру: {str(e)}")

    def _check_account_gifts(self, driver: WebDriver, username: str) -> List[dict]:
        """Проверяет подарки аккаунта и возвращает список истекающих."""
        try:
            driver.get("https://pwonline.ru/promo_items.php")
            time.sleep(2)
            
            # Проверка пустой корзины
            empty_cart = driver.find_elements(By.XPATH,
                "//div[@id='content_top']/h2[contains(text(), 'Ваша корзина с подарками пуста')]")
            
            if empty_cart:
                return []
                
            # Собираем подарки
            gifts = []
            gift_elements = driver.find_elements(By.XPATH,
                "//div[@class='items_container']/form[@class='js-transfer-form']/div[@class='promo_container']//table[@class='promo_items']/tbody/tr")
            
            for gift in gift_elements:
                try:
                    # Используем относительные XPath выражения от текущего элемента gift
                    date_element = gift.find_element(By.XPATH, ".//span[@class='date_end']")
                    date_text = date_element.text.strip()
                    
                    label_element = gift.find_element(By.XPATH, ".//label")
                    name = label_element.text.replace(date_text, "").strip()
                    
                    # Парсим дату
                    expires = self._parse_gift_date(date_text)
                    if expires and (expires - datetime.now()).days <= 7:  # Только подарки с истекающим сроком
                        gifts.append({
                            'name': name,
                            'expires': date_text.replace("(до ", "").replace(")", "")
                        })
                except Exception as e:
                    logger.error(f"Ошибка парсинга подарка для {username}: {e}")
            
            return gifts
            
        except Exception as e:
            logger.error(f"Ошибка проверки подарков для {username}: {e}")
            return []
    # =============================================
    # Методы планировщика
    # =============================================
    
    def start_scheduled_monitoring(self) -> None:
        """Запуск периодического мониторинга."""
        if self.running:
            logger.info("Мониторинг уже запущен")
            return
            
        self.running = True
        self.check_all_accounts()  # Первая проверка сразу
        
        # Настройка расписания (каждые 30 минут)
        schedule.every(30).minutes.do(self.check_all_accounts)
        
        def schedule_loop():
            """Цикл выполнения запланированных задач."""
            while self.running:
                schedule.run_pending()
                time.sleep(1)
        
        # Запуск в отдельном потоке
        threading.Thread(target=schedule_loop, daemon=True).start()

    def stop_monitoring(self) -> None:
        """Остановка периодического мониторинга."""
        self.running = False
