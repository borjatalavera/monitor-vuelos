from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')

try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.get("https://www.turismocity.com.ar/vuelos-baratos-a-MAD-desde-EZE")
    time.sleep(10) # wait for render
    html = driver.page_source
    with open("page_source.html", "w", encoding='utf-8') as f:
        f.write(html)
    print("Page fetched.")
    driver.quit()
except Exception as e:
    print(f"Error: {e}")
