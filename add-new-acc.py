import os
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle

class AddAccaounCookies:
    def __init__(self):
        self.driver = None
        self.cookies_dir = "cookies"
        os.makedirs(self.cookies_dir, exist_ok=True)
        
    def init_driver(self):
        options = ChromeOptions()
        self.driver = webdriver.Chrome(options=options) # Автоматически использует Selenium Manager
        
    def close_driver(self):
        if self.driver:
            self.driver.quit()
            
    def save_cookies(self, username):
        cookies_path = os.path.join(self.cookies_dir, f"{username}.pkl")
        with open(cookies_path, 'wb') as file:
            pickle.dump(self.driver.get_cookies(), file)
        print(f"Куки сохранены для аккаунта: {username}")
            
    def add_new_account(self):
        self.init_driver()
        self.driver.get("https://pwonline.ru")
        input("Залогиньтесь вручную и нажмите Enter...")
        
        try:
            username_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='content_top_2']/h2/a/strong"))
            )
            username = username_element.text.strip()
            self.save_cookies(username)
        except Exception as e:
            print(f"Ошибка: {e}")
        self.close_driver()
                
    def run(self):
        self.add_new_account()

if __name__ == "__main__":
    addAccaoun = AddAccaounCookies()
    addAccaoun.run()