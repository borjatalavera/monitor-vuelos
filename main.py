import os
import json
import requests
import re
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Cargar variables de entorno para desarrollo local
load_dotenv()

def send_telegram_message(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("Error: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados.")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def create_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def extract_price(text):
    # Extrae solo los dígitos de un string como "a partir de $ 1.343.054"
    digits = re.sub(r'[^\d]', '', text)
    if digits:
        return int(digits)
    return None

def main():
    # Cargar configuración
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Error: config.json no encontrado.")
        return

    origin = config['origin']
    destinations = config['destinations']
    threshold = config['price_threshold']
    currency = config.get('currency', 'ARS')

    # Cargar estado anterior (cache)
    state_file = 'state.json'
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
        except:
            state = {}

    new_state = state.copy()

    print("Iniciando Selenium WebDriver...")
    driver = create_driver()

    try:
        for dest in destinations:
            url = f"https://www.turismocity.com.ar/vuelos-baratos-a-{dest}-desde-{origin}"
            route_id = f"{origin}-{dest}-Tendencia"
            print(f"\nConsultando Turismocity: {origin} -> {dest}...")
            
            driver.get(url)
            
            try:
                # Esperar a que el selector de precio cargue
                # Intentamos con .best-price-amount o h1.title que tiene el precio visible
                price_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.best-price-amount, h1'))
                )
                price_text = price_element.text
                current_price = extract_price(price_text)
                
                if current_price:
                    print(f"  -> Mejor precio detectado para {dest}: {current_price} {currency} (Texto original: '{price_text}')")
                    
                    if current_price <= threshold:
                        last_price = state.get(route_id)
                        
                        # Alertar si bajó >2% o es nuevo
                        if last_price is None or current_price < (last_price * 0.98):
                            message = (
                                f"🔥 *¡OFERTA EN TENDENCIA DE TURISMOCITY!*\n\n"
                                f"📍 *Ruta:* {origin} ↔️ {dest}\n"
                                f"💰 *Precio Mínimo Detectado:* `{current_price:,} {currency}`\n\n"
                                f"🔗 *Ver Disponibilidad en Turismocity:* \n[Turismocity]({url})\n\n"
                                f"_[Último precio visto: {last_price} {currency} | Umbral: {threshold}]_"
                            )
                            send_telegram_message(message)
                        else:
                            print(f"    - Sin alerta: El precio no bajó un 2% (Actual: {current_price}, Anterior: {last_price})")
                    else:
                        print(f"    - Sin alerta: Precio {current_price} mayor al umbral de {threshold}")
                    
                    new_state[route_id] = current_price
                else:
                    print(f"  -> No se pudo extraer un precio entero de '{price_text}'")
                    
            except Exception as e:
                print(f"  -> Falló la extracción para {dest}: El elemento no se encontró o tardó demasiado.")
                
    finally:
        driver.quit()

    # Guardar estado actualizado
    with open(state_file, 'w') as f:
        json.dump(new_state, f)

if __name__ == "__main__":
    main()
