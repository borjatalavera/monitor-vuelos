import os
import json
import requests
from amadeus import Client, ResponseError
from dotenv import load_dotenv

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
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        print(f"Respuesta de Telegram: {response.status_code} - {response.text}")
        response.raise_for_status()
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def get_flight_prices(amadeus, origin, destination, departure_date):
    try:
        print(f"Consultando Amadeus para {origin} -> {destination} el {departure_date}...")
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            adults=1,
            max=5
        )
        print(f"Amadeus devolvió {len(response.data)} ofertas.")
        return response.data
    except ResponseError as error:
        print(f"Error en la API de Amadeus: {error}")
        return []

def main():
    # Inicializar cliente Amadeus
    api_key = os.getenv('AMADEUS_API_KEY')
    api_secret = os.getenv('AMADEUS_API_SECRET')
    
    if not api_key or not api_secret:
        print("Error: AMADEUS_API_KEY o AMADEUS_API_SECRET no configurados.")
        return

    amadeus = Client(client_id=api_key, client_secret=api_secret)

    # Cargar configuración
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Error: config.json no encontrado.")
        return

    # Cargar estado anterior (cache)
    state_file = 'state.json'
    state = {}
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            state = json.load(f)

    new_state = {}

    for route in config.get('routes', []):
        origin = route['origin']
        destination = route['destination']
        date = route['departure_date']
        threshold = route['price_threshold']
        
        route_id = f"{origin}-{destination}-{date}"
        print(f"Buscando vuelos para {route_id}...")
        
        flights = get_flight_prices(amadeus, origin, destination, date)
        
        if not flights:
            print(f"⚠️ No se encontraron vuelos para la fecha {date}. Asegúrate de que sea una fecha futura.")
            continue
            
        # Obtener el precio más bajo
        cheapest_flight = min(flights, key=lambda x: float(x['price']['total']))
        current_price = float(cheapest_flight['price']['total'])
        currency = cheapest_flight['price']['currency']
        
        print(f"Precio actual: {current_price} {currency} (Umbral: {threshold})")
        
        # Guardar precio actual en el nuevo estado
        new_state[route_id] = current_price
        
        # Lógica de alerta
        if current_price <= threshold:
            last_price = state.get(route_id)
            
            # Solo alertar si el precio bajó o si no había un precio anterior guardado
            if last_price is None or current_price < last_price:
                message = (
                    f"✈️ *¡Alerta de Precio Bajo!*\n\n"
                    f"Ruta: {origin} -> {destination}\n"
                    f"Fecha: {date}\n"
                    f"Precio actual: *{current_price} {currency}*\n"
                    f"Umbral configurado: {threshold} {currency}\n"
                    f"[Reservar en Amadeus](https://www.amadeus.com)"
                )
                send_telegram_message(message)
                print("Alerta enviada a Telegram.")
            else:
                print("El precio sigue bajo pero no ha disminuido respecto a la última alerta.")
        else:
            print("El precio está por encima del umbral.")

    # Guardar estado actualizado
    with open(state_file, 'w') as f:
        json.dump(new_state, f)

if __name__ == "__main__":
    main()
