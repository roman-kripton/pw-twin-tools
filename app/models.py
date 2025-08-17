from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2 import sql
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
class Database:
    def __init__(self, connection_string: str):
        """Инициализация подключения к базе данных.
        
        Args:
            connection_string (str): Строка подключения к PostgreSQL
        """
        self.conn_string = connection_string
        self._init_db()

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # =============================================
                    # Группы аккаунтов
                    # Хранит категории для группировки аккаунтов
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS groups (
                            id SERIAL PRIMARY KEY,               -- Автоинкрементный ID группы
                            name VARCHAR(255) UNIQUE NOT NULL,   -- Уникальное название группы
                            created_at TIMESTAMP DEFAULT NOW()   -- Дата создания (автоматически)
                        )
                    """)

                    # =============================================
                    # Аккаунты пользователей
                    # Основная таблица с информацией о пользователях
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS accounts (
                            username VARCHAR(255) PRIMARY KEY,  -- Логин (уникальный идентификатор)
                            alias VARCHAR(255),                 -- Псевдоним (необязательный)
                            group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL, -- Связь с группой
                            last_success TIMESTAMP,             -- Последняя успешная активность
                            server VARCHAR(50),                 -- Игровой сервер
                            use_promo BOOLEAN DEFAULT FALSE,    -- Флаг использования промокодов
                            transfer_to_game BOOLEAN DEFAULT FALSE, -- Флаг перевода наград
                            mdm_coins VARCHAR(20) DEFAULT NULL   -- Баланс монет
                        )
                    """)

                    # =============================================
                    # Промокоды
                    # Хранит все промокоды и их статусы
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS promo_codes (
                            code VARCHAR(255) PRIMARY KEY,       -- Код промокода (уникальный)
                            status VARCHAR(50) NOT NULL,        -- Статус: active/expired/invalid
                            added_at TIMESTAMP DEFAULT NOW()    -- Дата добавления
                        )
                    """)

                    # =============================================
                    # Активации промокодов
                    # Отслеживает какие аккаунты какие коды активировали
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS account_promo_codes (
                            username VARCHAR(255) REFERENCES accounts(username) ON DELETE CASCADE,
                            promo_code VARCHAR(255) REFERENCES promo_codes(code) ON DELETE CASCADE,
                            status VARCHAR(50) NOT NULL,        -- Результат активации
                            activated_at TIMESTAMP DEFAULT NOW(),-- Время активации
                            PRIMARY KEY (username, promo_code)   -- Уникальная пара пользователь-код
                        )
                    """)

                    # =============================================
                    # Персонажи аккаунтов
                    # Список персонажей, принадлежащих аккаунтам
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS account_characters (
                            username VARCHAR(255) REFERENCES accounts(username) ON DELETE CASCADE,
                            server VARCHAR(255) NOT NULL,        -- Игровой сервер
                            character_name VARCHAR(255) NOT NULL,-- Имя персонажа
                            class_name VARCHAR(255),             -- Класс персонажа
                            level INTEGER,                       -- Уровень персонажа
                            PRIMARY KEY (username, server, character_name) -- Уникальный персонаж
                        )
                    """)

                    # =============================================
                    # Задания марафона
                    # Прогресс выполнения задач для аккаунтов
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS tasks (
                            id SERIAL PRIMARY KEY,               -- Уникальный ID записи
                            username VARCHAR(255) REFERENCES accounts(username) ON DELETE CASCADE,
                            task_name VARCHAR(255),              -- Название задания
                            current INTEGER,                     -- Текущий прогресс
                            total INTEGER,                       -- Требуемый прогресс
                            percent FLOAT,                       -- Процент выполнения
                            timestamp TIMESTAMP                  -- Время обновления
                        )
                    """)

                    # =============================================
                    # Настройки системы
                    # Хранит ключ-значение параметров системы
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS settings (
                            key VARCHAR(255) PRIMARY KEY,        -- Ключ параметра
                            value TEXT                          -- Значение параметра
                        )
                    """)

                    # =============================================
                    # Таблица подарков
                    # Хранит все подарки аккаунтов
                    # =============================================
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS account_gifts (
                            id SERIAL PRIMARY KEY,
                            username VARCHAR(255) REFERENCES accounts(username) ON DELETE CASCADE,
                            gift_name VARCHAR(255) NOT NULL,
                            expires TIMESTAMP NOT NULL,
                            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Создаём общую группу по умолчанию
                    cursor.execute("""
                        INSERT INTO groups (name)
                        VALUES ('Общая')
                        ON CONFLICT (name) DO NOTHING
                    """)

                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
            raise

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Создает и возвращает новое подключение к базе данных.
        
        Returns:
            psycopg2.extensions.connection: Объект подключения
        """
        return psycopg2.connect(self.conn_string)
    
    # =============================================
    # Методы для работы с группами
    # =============================================
    def create_group(self, group_name: str) -> int:
        """Создает новую группу аккаунтов.
        
        Args:
            group_name (str): Название группы
            
        Returns:
            int: ID созданной группы
            
        Raises:
            Exception: Если произошла ошибка при создании
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO groups (name)
                        VALUES (%s)
                        RETURNING id
                    """, (group_name,))
                    group_id = cursor.fetchone()[0]
                    conn.commit()
                    return group_id
        except Exception as e:
            logger.error(f"Ошибка создания группы {group_name}: {e}")
            raise

    def delete_group(self, group_id: int) -> None:
        """Удаляет группу аккаунтов.
        
        Args:
            group_id (int): ID группы для удаления
            
        Raises:
            Exception: Если произошла ошибка при удалении
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM groups WHERE id = %s", (group_id,))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка удаления группы {group_id}: {e}")
            raise

    def get_all_groups(self) -> List[tuple]:
        """Получает список всех групп.
        
        Returns:
            List[tuple]: Список кортежей (id, name)
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, name FROM groups ORDER BY name")
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка групп: {e}")
            return []

    # =============================================
    # Методы для работы с аккаунтами
    # =============================================
    def save_account_data(self, username, alias=None, last_success=None, server=None, 
                        use_promo=None, transfer_to_game=None, group_id=None, mdm_coins=None):
        """
        Сохраняет или обновляет данные аккаунта
        Args:
            username: Логин аккаунта (обязательный)
            alias: Псевдоним персонажа
            last_success: Время последней успешной проверки
            server: Название сервера
            use_promo: Использовать промокоды
            transfer_to_game: Переводить награды в игру
            group_id: ID группы
            mdm_coins: Кол-во МДМ монет
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Проверяем существование аккаунта
                    cursor.execute("""
                        SELECT alias, last_success, server, use_promo, transfer_to_game, group_id, mdm_coins 
                        FROM accounts WHERE username = %s
                    """, (username,))
                    result = cursor.fetchone()

                    # Устанавливаем значения по умолчанию для новых аккаунтов
                    defaults = {
                        'alias': alias,
                        'last_success': last_success,
                        'server': server,
                        'use_promo': use_promo if use_promo is not None else None,
                        'transfer_to_game': transfer_to_game if transfer_to_game is not None else None,
                        'group_id': group_id,
                        'mdm_coins': mdm_coins
                    }

                    # Для существующих аккаунтов сохраняем текущие значения, если новые не указаны
                    if result:
                        current_data = {
                            'alias': result[0],
                            'last_success': result[1],
                            'server': result[2],
                            'use_promo': result[3],
                            'transfer_to_game': result[4],
                            'group_id': result[5],
                            'mdm_coins': result[6]
                        }
                        
                        # Обновляем только те поля, для которых переданы новые значения
                        for key in defaults:
                            if defaults[key] is None:
                                defaults[key] = current_data[key]
                    

                    # Сохраняем/обновляем данные
                    cursor.execute("""
                        INSERT INTO accounts 
                            (username, alias, last_success, server, use_promo, transfer_to_game, group_id, mdm_coins)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (username) DO UPDATE SET
                            alias = EXCLUDED.alias,
                            last_success = EXCLUDED.last_success,
                            server = EXCLUDED.server,
                            use_promo = EXCLUDED.use_promo,
                            transfer_to_game = EXCLUDED.transfer_to_game,
                            group_id = EXCLUDED.group_id,
                            mdm_coins = EXCLUDED.mdm_coins
                    """, (
                        username,
                        defaults['alias'],
                        defaults['last_success'],
                        defaults['server'],
                        defaults['use_promo'],
                        defaults['transfer_to_game'],
                        defaults['group_id'],
                        defaults['mdm_coins']
                    ))
                    
                    conn.commit()
                    logger.info(f"Данные аккаунта {username} успешно сохранены")
                    return True
                    
        except Exception as e:
            logger.error(f"Ошибка сохранения данных аккаунта {username}: {e}", exc_info=True)
            return False

    def get_account_data(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает данные аккаунта.
        
        Args:
            username (str): Логин аккаунта
            
        Returns:
            Optional[Dict[str, Any]]: Словарь с данными или None если не найден
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT username, alias, server, use_promo, transfer_to_game
                        FROM accounts WHERE username = %s
                    """, (username,))
                    columns = [desc[0] for desc in cursor.description]
                    row = cursor.fetchone()
                    return dict(zip(columns, row)) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения данных аккаунта: {e}")
            return None

    def save_account_characters(self, username: str, characters_data: Dict[str, List[Dict]]) -> bool:
        """Сохраняет персонажей для указанного аккаунта.
        
        Args:
            username (str): Логин аккаунта
            characters_data (Dict): Данные персонажей в формате:
                {
                    'server1': [
                        {'name': 'char1', 'class': 'warrior', 'level': 50},
                        ...
                    ],
                    ...
                }
                
        Returns:
            bool: True если успешно, False при ошибке
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Создаем аккаунт если не существует
                    cursor.execute("""
                        INSERT INTO accounts (username)
                        VALUES (%s)
                        ON CONFLICT (username) DO NOTHING
                    """, (username,))

                    # Удаляем старых персонажей
                    cursor.execute("DELETE FROM account_characters WHERE username = %s", (username,))
                    
                    # Добавляем новых персонажей
                    data = [
                        (username, server, char["name"], char["class"], char["level"])
                        for server, chars in characters_data.items() 
                        for char in chars
                    ]
                    
                    if data:  # Только если есть данные для вставки
                        cursor.executemany("""
                            INSERT INTO account_characters 
                                (username, server, character_name, class_name, level)
                            VALUES (%s, %s, %s, %s, %s)
                        """, data)
                    
                    conn.commit()
                    logger.info(f"Сохранены персонажи для аккаунта {username}")
                    return True
        except Exception as e:
            logger.error(f"Ошибка сохранения персонажей для {username}. Данные: {characters_data}. Ошибка: {str(e)}")
            return False
        
    def get_account_characters(self, username: str) -> List[tuple]:
        """Получает список персонажей аккаунта.
        
        Args:
            username (str): Логин аккаунта
            
        Returns:
            List[tuple]: Список кортежей (server, character_name)
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT server, character_name, class_name, level 
                        FROM account_characters 
                        WHERE username = %s
                        ORDER BY server, character_name
                    """, (username,))
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения персонажей для {username}: {e}")
            return []    
    
    def get_character_info(self, username: str, server: str, character_name: str) -> str:
        """Получает информацию о персонаже в заданном формате.
        
        Args:
            username (str): Логин аккаунта
            server (str): Название сервера
            character_name (str): Имя персонажа
            
        Returns:
            str: Строка в формате 'username (class_name, уровень:level)'
                или пустая строка, если персонаж не найден
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT class_name, level 
                        FROM account_characters 
                        WHERE username = %s
                        AND server = %s
                        AND character_name = %s
                    """, (username, server, character_name))
                    result = cursor.fetchone()
                    
                    if result:
                        class_name, level = result
                        return f"{character_name} ({class_name}, уровень:{level})"
                    return ""
        except Exception as e:
            logger.error(f"Ошибка получения информации о персонаже {username}@{server}:{character_name}: {e}")
            return ""

    def get_account_characters_for_server(self, username: str, server: str) -> List[tuple]:
            """Получает персонажей аккаунта на конкретном сервере.
            
            Args:
                username (str): Логин аккаунта
                server (str): Игровой сервер
                
            Returns:
                List[tuple]: Список имен персонажей
            """
            try:
                with self._get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT character_name 
                            FROM account_characters 
                            WHERE username = %s AND server = %s
                            ORDER BY character_name
                        """, (username, server))
                        return cursor.fetchall()
            except Exception as e:
                logger.error(f"Ошибка получения персонажей для {username} на сервере {server}: {e}")
                return []        

    def get_accounts(self) -> List[tuple]:
        """Получает список всех аккаунтов с информацией о группах.
        
        Returns:
            List[tuple]: Список кортежей с данными аккаунтов
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT a.username, a.alias, a.last_success, a.server, 
                               a.use_promo, a.transfer_to_game, a.group_id, 
                               g.name, a.mdm_coins
                        FROM accounts a
                        LEFT JOIN groups g ON a.group_id = g.id
                        ORDER BY COALESCE(g.name, 'Общая'), a.username
                    """)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка аккаунтов: {e}")
            return []
        
    def update_account_group(self, username: str, group_id: Optional[int]) -> None:
        """Обновляет группу для аккаунта.
        
        Args:
            username (str): Логин аккаунта
            group_id (Optional[int]): ID группы или None
            
        Raises:
            Exception: При ошибке обновления
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE accounts
                        SET group_id = %s
                        WHERE username = %s
                    """, (group_id, username))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления группы для {username}: {e}")
            raise            

    def update_account_setting(self, username: str, field: str, value: Any) -> bool:
        """Обновляет настройку аккаунта.
        
        Args:
            username (str): Логин аккаунта
            field (str): Поле для обновления
            value (Any): Новое значение
            
        Returns:
            bool: True если успешно, False при ошибке
            
        Raises:
            ValueError: Если поле недопустимо
        """
        valid_fields = ['server', 'use_promo', 'transfer_to_game', 'alias']
        if field not in valid_fields:
            raise ValueError(f"Недопустимое поле: {field}")
        
        # Преобразование строковых булевых значений
        if field in ['use_promo', 'transfer_to_game'] and isinstance(value, str):
            value = value.lower() == 'true'

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("UPDATE accounts SET {} = %s WHERE username = %s").format(
                            sql.Identifier(field)
                        ),
                        (value, username)
                    )
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления настройки {field} для {username}: {e}")
            return False       

    # =============================================
    # Методы для работы с промокодами
    # =============================================
    def get_promo_code_status(self, promo_code: str) -> Optional[str]:
        """Получает статус промокода.
        
        Args:
            promo_code (str): Код промокода
            
        Returns:
            Optional[str]: Статус или None если не найден
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT status FROM promo_codes WHERE code = %s
                    """, (promo_code,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения статуса промокода {promo_code}: {e}")
            return None

    def save_promo_code_status(self, promo_code: str, status: str) -> None:
        """Сохраняет или обновляет статус промокода.
        
        Args:
            promo_code (str): Код промокода
            status (str): Новый статус
            
        Raises:
            Exception: При ошибке сохранения
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO promo_codes (code, status)
                        VALUES (%s, %s)
                        ON CONFLICT (code) DO UPDATE SET status = EXCLUDED.status
                    """, (promo_code, status))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения статуса промокода {promo_code}: {e}")
            raise

    def save_account_promo_code(self, username: str, promo_code: str, 
                              status: str, message: Optional[str] = None) -> None:
        """Сохраняет информацию об активации промокода аккаунтом.
        
        Args:
            username (str): Логин аккаунта
            promo_code (str): Код промокода
            status (str): Статус активации
            message (Optional[str]): Дополнительное сообщение
            
        Raises:
            Exception: При ошибке сохранения
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO account_promo_codes 
                            (username, promo_code, status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (username, promo_code) DO UPDATE SET 
                            status = EXCLUDED.status,
                            activated_at = NOW()
                    """, (username, promo_code, status))
                    conn.commit()
        except Exception as e:
            logger.error(f"""Ошибка сохранения активации промокода {promo_code} 
                          для {username}: {e}""")
            raise

    def get_accounts_for_promo_activation(self, promo_code: str) -> List[str]:
        """Получает аккаунты для активации промокода.
        
        Args:
            promo_code (str): Код промокода
            
        Returns:
            List[str]: Список логинов аккаунтов
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT a.username 
                        FROM accounts a
                        WHERE a.use_promo = TRUE
                        AND NOT EXISTS (
                            SELECT 1 FROM account_promo_codes apc
                            WHERE apc.username = a.username AND apc.promo_code = %s
                        )
                    """, (promo_code,))
                    return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения аккаунтов для промокода {promo_code}: {e}")
            return []
        
    def save_account_gifts(self, username: str, gifts: List[dict]) -> None:
        """Сохраняет информацию о подарках аккаунта."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Удаляем старые подарки
                    cursor.execute("DELETE FROM account_gifts WHERE username = %s", (username,))
                    
                    # Добавляем новые
                    for gift in gifts:
                        cursor.execute(
                            "INSERT INTO account_gifts (username, gift_name, expires) VALUES (%s, %s, %s)",
                            (username, gift['name'], gift['expires'])
                        )
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения подарков для {username}: {e}")

    def get_expiring_gifts(self, days: int = 3) -> Dict[str, List[dict]]:
        """Получает подарки с истекающим сроком."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT username, gift_name, expires 
                        FROM account_gifts 
                        WHERE expires <= (CURRENT_DATE + INTERVAL '%s days')
                        ORDER BY username, expires
                    """, (days,))
                    
                    result = {}
                    for username, name, expires in cursor.fetchall():
                        result.setdefault(username, []).append({
                            'name': name,
                            'expires': expires.strftime("%H:%M %d.%m.%Y")
                        })
                    return result
        except Exception as e:
            logger.error(f"Ошибка получения истекающих подарков: {e}")
            return {}

    # =============================================
    # Методы для работы с задачами
    # =============================================
    def save_task_data(self, username: str, task_name: str, current: int, 
                      total: int, percent: float, timestamp: datetime) -> bool:
        """Сохраняет данные о выполнении задачи.
        
        Args:
            username (str): Логин аккаунта
            task_name (str): Название задачи
            current (int): Текущий прогресс
            total (int): Общий требуемый прогресс
            percent (float): Процент выполнения
            timestamp (datetime): Время проверки
            
        Returns:
            bool: True если успешно, False при ошибке
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Проверяем существование аккаунта
                    cursor.execute("SELECT 1 FROM accounts WHERE username = %s", (username,))
                    if not cursor.fetchone():
                        logger.error(f"Аккаунт {username} не существует")
                        return False

                    # Проверяем изменился ли прогресс
                    cursor.execute("""
                        SELECT current, total FROM tasks 
                        WHERE username = %s AND task_name = %s
                        ORDER BY timestamp DESC LIMIT 1
                    """, (username, task_name))
                    
                    existing = cursor.fetchone()
                    if existing and existing[0] == current and existing[1] == total:
                        logger.debug(f"Прогресс задачи {task_name} не изменился")
                        return True

                    # Сохраняем новую запись
                    cursor.execute("""
                        INSERT INTO tasks 
                            (username, task_name, current, total, percent, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (username, task_name, current, total, percent, timestamp))
                    
                    conn.commit()
                    logger.info(f"Сохранены данные задачи {task_name} для {username}")
                    return True
                    
        except Exception as e:
            logger.error(f"""Ошибка сохранения задачи {task_name} 
                          для {username}: {e}""", exc_info=True)
            return False

    def get_account_tasks(self, username: str) -> List[tuple]:
        """Получает последние статусы задач для аккаунта.
        
        Args:
            username (str): Логин аккаунта
            
        Returns:
            List[tuple]: Список задач с последними статусами
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT ON (task_name) 
                            task_name, current, total, percent, timestamp
                        FROM tasks
                        WHERE username = %s
                        ORDER BY task_name, timestamp DESC
                    """, (username,))
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения задач для {username}: {e}")
            return [] 
        
    def get_accounts_with_tasks_and_groups(self) -> List[tuple]:
        """Получение данных аккаунтов с задачами и информацией о группах."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            a.username, 
                            a.alias, 
                            a.last_success, 
                            a.server, 
                            a.use_promo, 
                            a.transfer_to_game, 
                            a.group_id, 
                            g.name, 
                            a.mdm_coins,
                            (
                                SELECT array_agg(
                                    ARRAY[t.task_name, t.current::text, t.total::text]
                                ) 
                                FROM tasks t 
                                WHERE t.username = a.username
                            ) as tasks
                        FROM accounts a
                        LEFT JOIN groups g ON a.group_id = g.id
                        ORDER BY COALESCE(g.name, 'Общая'), a.username
                    """)
                    result = []
                    for row in cursor.fetchall():
                        # Преобразуем массив задач в Python-объект
                        tasks = []
                        if row[9]:  # tasks field
                            for task in row[9]:
                                try:
                                    # Преобразуем current и total в int
                                    task_name = task[0]
                                    current = int(task[1])
                                    total = int(task[2])
                                    tasks.append((task_name, current, total))
                                except (ValueError, IndexError) as e:
                                    logger.error(f"Ошибка преобразования задачи: {task}, ошибка: {e}")
                        
                        result.append(row[:9] + (tasks,))
                    return result
        except Exception as e:
            logger.error(f"Ошибка получения данных аккаунтов: {e}")
            return []
        
    # =============================================
    # Методы для работы с настройками
    # =============================================
    def get_setting(self, key: str, default: Optional[Any] = None) -> Any:
        """Получает значение настройки.
        
        Args:
            key (str): Ключ настройки
            default (Optional[Any]): Значение по умолчанию
            
        Returns:
            Any: Значение настройки или default если не найдено
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT value FROM settings WHERE key = %s
                    """, (key,))
                    result = cursor.fetchone()
                    return result[0] if result else default
        except Exception as e:
            logger.error(f"Ошибка получения настройки {key}: {e}")
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """Устанавливает значение настройки.
        
        Args:
            key (str): Ключ настройки
            value (Any): Значение настройки
            
        Raises:
            Exception: При ошибке сохранения
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO settings (key, value)
                        VALUES (%s, %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, (key, value))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения настройки {key}: {e}")
            raise