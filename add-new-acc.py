import os
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import warnings
import logging
from selenium.webdriver.remote.remote_connection import LOGGER

class PWOAccountManager:
    def __init__(self):
        self.driver = None
        self.cookies_dir = "app/cookies"
        os.makedirs(self.cookies_dir, exist_ok=True)
        self._setup_logging()
        
    def _setup_logging(self):
        """Настройка подавления логов и предупреждений"""
        warnings.filterwarnings("ignore")
        LOGGER.setLevel(logging.WARNING)
        logging.basicConfig(level=logging.WARNING)
        os.environ['WDM_LOG_LEVEL'] = '0'
        os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
    
    def init_driver(self):
        """Инициализация драйвера с настройками"""
        options = ChromeOptions()
        
        # Подавление логов и автоматизации
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        options.add_argument("--silent")
        options.add_experimental_option('excludeSwitches', [
            'enable-logging', 
            'enable-automation'
        ])
        
        # Оптимизация производительности
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-webgl")
        options.add_argument("--disable-features=WebGL")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-component-update")
        
        self.driver = webdriver.Chrome(options=options)
        
        # Блокировка ненужных запросов
        self.driver.execute_cdp_cmd('Network.setBlockedURLs', {
            "urls": ["*://*.googleapis.com/*", "*://*.gstatic.com/*", "*://*.google.com/*"]
        })
        self.driver.execute_cdp_cmd('Network.enable', {})
    
    def close_driver(self):
        """Корректное закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
    
    def check_accounts(self):
        """Проверка сохраненных аккаунтов"""
        try:
            cookie_files = [f for f in os.listdir(self.cookies_dir) if f.endswith('.pkl')]
            
            if not cookie_files:
                print("\n❌ Нет сохраненных аккаунтов для проверки")
                return False
                
            print(f"\nНайдено {len(cookie_files)} аккаунтов для проверки")
            
            for idx, cookie_file in enumerate(cookie_files, 1):
                self.init_driver()
                self.driver.get("https://pwonline.ru")
                
                # Загрузка куков
                cookies_path = os.path.join(self.cookies_dir, cookie_file)
                try:
                    with open(cookies_path, 'rb') as file:
                        cookies = pickle.load(file)
                    
                    for cookie in cookies:
                        self.driver.add_cookie(cookie)
                    
                    self.driver.refresh()
                    
                    try:
                        username = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, "//div[@id='content_top_2']/h2/a/strong"))
                        ).text.strip()
                        
                        print(f"\n✅ Аккаунт {username} (файл: {cookie_file})")
                        print("Страница успешно загружена. Проверьте состояние аккаунта.")
                    except Exception as e:
                        print(f"\n❌ Не удалось проверить аккаунт из файла {cookie_file}")
                        print(f"Ошибка: {str(e)[:100]}")
                    
                    input(f"\nНажмите Enter для продолжения ({idx}/{len(cookie_files)})...")
                
                except Exception as e:
                    print(f"\n❌ Ошибка при загрузке куков из {cookie_file}: {str(e)[:100]}")
                
                finally:
                    self.close_driver()
            
            return True
            
        except Exception as e:
            print(f"\n❌ Ошибка при проверке аккаунтов: {str(e)[:100]}")
            return False
    
    def add_new_account(self):
        """Добавление нового аккаунта"""
        try:
            self.init_driver()
            self.driver.get("https://pwonline.ru")
            
            print("\n➡ Чистая сессия браузера готова")
            print("1. Выполните вход в аккаунт")
            print("2. Дождитесь полной загрузки страницы")
            input("3. Нажмите Enter для сохранения...\n")
            
            try:
                username = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@id='content_top_2']/h2/a/strong"))
                ).text.strip()
                
                cookies_path = os.path.join(self.cookies_dir, f"{username}.pkl")
                with open(cookies_path, 'wb') as file:
                    pickle.dump(self.driver.get_cookies(), file)
                
                print(f"\n✅ Аккаунт {username} успешно сохранен")
                return True
            
            except Exception as e:
                print(f"\n❌ Не удалось получить данные аккаунта: {str(e)[:100]}")
                return False
                
        except Exception as e:
            print(f"\n❌ Ошибка: {str(e)[:100]}")
            return False
        finally:
            self.close_driver()

def main():
    manager = PWOAccountManager()
    
    while True:
        print("\n" + "="*40)
        print(" Менеджер аккаунтов PWOnline ".center(40))
        print("="*40)
        print("1. Добавить аккаунт")
        print("2. Проверить аккаунты")
        print("3. Выход\n")
        
        choice = input("Выбор: ").strip()
        
        if choice == "1":
            manager.add_new_account()
        elif choice == "2":
            manager.check_accounts()
        elif choice == "3":
            break
        else:
            print("Некорректный ввод")

if __name__ == "__main__":
    main()