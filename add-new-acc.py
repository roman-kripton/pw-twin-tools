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

class AddAccountCookies:
    def __init__(self):
        self.driver = None
        self.cookies_dir = "cookies"
        os.makedirs(self.cookies_dir, exist_ok=True)
        
        # Глобальное отключение логов
        warnings.filterwarnings("ignore")
        LOGGER.setLevel(logging.WARNING)
        logging.basicConfig(level=logging.WARNING)
        os.environ['WDM_LOG_LEVEL'] = '0'
        os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
        
    def init_driver(self):
        options = ChromeOptions()
        
        # Максимальное подавление логов
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        options.add_argument("--silent")
        options.add_experimental_option('excludeSwitches', [
            'enable-logging',
            'enable-automation'
        ])
        
        # Отключение GPU и WebGL
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-webgl")
        options.add_argument("--disable-features=WebGL")
        
        # Другие настройки
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        
        # Для Windows - отключение консоли
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-component-update")
        
        self.driver = webdriver.Chrome(options=options)
        
        # Дополнительное подавление через DevTools
        self.driver.execute_cdp_cmd('Network.setBlockedURLs', {
            "urls": [
                "*://*.googleapis.com/*",
                "*://*.gstatic.com/*",
                "*://*.google.com/*"
            ]
        })
        self.driver.execute_cdp_cmd('Network.enable', {})
        
    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None
                
    def add_new_account(self):
        try:
            self.init_driver()
            self.driver.get("https://pwonline.ru")
            
            print("\n➡ Чистая сессия браузера готова")
            print("1. Выполните вход в аккаунт")
            print("2. Дождитесь полной загрузки страницы")
            input("3. Нажмите Enter для сохранения...\n")
            
            username = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='content_top_2']/h2/a/strong"))
            ).text.strip()
            
            cookies_path = os.path.join(self.cookies_dir, f"{username}.pkl")
            with open(cookies_path, 'wb') as file:
                pickle.dump(self.driver.get_cookies(), file)
                
            print(f"\n✅ Аккаунт {username} успешно сохранен")
            return True
            
        except Exception as e:
            print(f"\n❌ Ошибка: {str(e)[:100]}")
            return False
        finally:
            self.close_driver()

if __name__ == "__main__":
    manager = AddAccountCookies()
    
    while True:
        print("\n" + "="*40)
        print(" Менеджер аккаунтов PWOnline ".center(40))
        print("="*40)
        print("1. Добавить аккаунт")
        print("2. Выход\n")
        
        choice = input("Выбор: ").strip()
        
        if choice == "1":
            manager.add_new_account()
        elif choice == "2":
            break
        else:
            print("Некорректный ввод")