import os
import json
import requests
from datetime import datetime, timedelta
from amadeus import Client, ResponseError
from dotenv import load_dotenv

# Cargar variables de entorno para desarrollo local
load_dotenv()

def load_airlines():
    # Cargar base de datos local de IATAs de aerolíneas
    try:
        with open('airlines.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Advertencia: airlines.json no encontrado, se usarán los códigos IATA crudos.")
        return {}

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
        print(f"Respuesta de Telegram: {response.status_code}")
        response.raise_for_status()
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def get_flight_prices(amadeus, origin, destination, departure_date, return_date, currency_code="USD"):
    try:
        print(f"Consultando Amadeus: {origin} <-> {destination} del {departure_date} al {return_date}...")
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            returnDate=return_date,
            adults=1,
            max=5,
            currencyCode=currency_code
        )
        return response.data
    except ResponseError as error:
        print(f"Error en la API de Amadeus ({origin}-{destination}): {error}")
        return []

def get_date_range(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime("%Y-%m-%d"))
        # Buscamos cada 7 días para no saturar la API y cubrir el rango
        current_date += timedelta(days=7)
    return dates

def main():
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

    origin = config['origin']
    destinations = config['destinations']
    dates = get_date_range(config['start_date'], config['end_date'])
    threshold = config['price_threshold']
    pref_currency = config.get('currency', 'USD')
    min_duration = config.get('min_duration_days', 7)
    max_duration = config.get('max_duration_days', 16)
    
    # Cargar aerolíneas desde json
    airlines_map = load_airlines()

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

    for dest in destinations:
        for date in dates:
            for duration in range(min_duration, max_duration + 1):
                # Calcular fecha de regreso
                departure_dt = datetime.strptime(date, "%Y-%m-%d")
                return_dt = departure_dt + timedelta(days=duration)
                return_date = return_dt.strftime("%Y-%m-%d")
                
                route_id = f"{origin}-{dest}-{date}-RT{duration}"
                
                flights = get_flight_prices(amadeus, origin, dest, date, return_date, pref_currency)
                
                if not flights:
                    continue
                    
                # Obtener el precio más bajo del día
                cheapest_flight = min(flights, key=lambda x: float(x['price']['total']))
                current_price = float(cheapest_flight['price']['total'])
                currency = cheapest_flight['price']['currency']
                
                # Extraer Código de Aerolínea (Carrier)
                carrier_code = cheapest_flight['validatingAirlineCodes'][0]
                airline_name = airlines_map.get(carrier_code, carrier_code)
                
                print(f"  -> Mejor precio para {route_id}: {current_price} {currency} ({airline_name})")
                
                # Lógica de alerta
                if current_price <= threshold:
                    last_price = state.get(route_id)
                    
                    # Solo alertar si el precio bajó significativamente (>2%) o si es nuevo
                    if last_price is None or current_price < (last_price * 0.98):
                        # Generar enlaces de búsqueda
                        kayak_link = f"https://www.kayak.com.ar/flights/{origin}-{dest}/{date}/{return_date}?sort=price_a"
                        google_link = f"https://www.google.com/travel/flights?q=Flights%20to%20{dest}%20from%20{origin}%20on%20{date}%20through%20{return_date}"
                        turismocity_link = f"https://www.turismocity.com.ar/vuelos-baratos-a-{dest}-desde-{origin}"
                        despegar_link = f"https://www.despegar.com.ar/shop/flights/results/roundtrip/{origin}/{dest}/{date}/{return_date}/1/0/0/NA/NA/NA/NA/NA"
    
                        message = (
                            f"✈️ *¡OFERTA DETECTADA!*\n\n"
                            f"🏢 *Aerolínea:* {airline_name} ({carrier_code})\n"
                            f"📍 *Ruta:* {origin} ↔️ {dest}\n"
                            f"📅 *Fechas:* {date} al {return_date} ({duration} días)\n\n"
                            f"💰 *Precio Base:* `{current_price} {currency}`\n"
                            f"⚠️ _Nota: En AR, sumar impuestos locales (PAIS/Ganancias) si no figuran._\n\n"
                            f"🔗 *Ver en:* \n"
                            f"[🔍 Google Flights]({google_link}) | [✈️ Kayak]({kayak_link})\n"
                            f"[🧳 Despegar]({despegar_link}) | [🏙️ Turismocity]({turismocity_link})\n\n"
                            f"_[Último precio visto: {last_price if last_price else 'N/A'}]_"
                        )
                        send_telegram_message(message)
                        new_state[route_id] = current_price
                
                # Guardar siempre el precio más reciente visto para la próxima comparación
                new_state[route_id] = current_price

    # Guardar estado actualizado
    with open(state_file, 'w') as f:
        json.dump(new_state, f)

if __name__ == "__main__":
    main()
