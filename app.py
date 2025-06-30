from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import logging
import traceback
from datetime import datetime, date
import pytz
import re
import random

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# --- URLs de las APIs ---
API_PERFORMANCE_URL_TEMPLATE = 'https://api-global.morningstar.com/sal-service/v1/fund/performance/v5/{}?secExchangeList=&limitAge=&hideYTD=false&languageId=es&locale=es&clientId=MDC&benchmarkId=mstarorcat&component=sal-mip-growth-10k&version=4.65.0'
API_TRAILING_RETURN_URL_TEMPLATE = 'https://api-global.morningstar.com/sal-service/v1/fund/trailingReturn/v3/{}/data?duration=quarterly&limitAge=&languageId=es&locale=es&clientId=MDC&benchmarkId=mstarorcat&component=sal-mip-trailing-return&version=4.65.0'

# URLs para rentabilidades YTD
MORNINGSTAR_SP500_API_URL = API_PERFORMANCE_URL_TEMPLATE.format('F0GBR04UOL')
MORNINGSTAR_SP500_USD_API_URL = API_PERFORMANCE_URL_TEMPLATE.format('F0000000VM')
MORNINGSTAR_WORLD_API_URL = API_PERFORMANCE_URL_TEMPLATE.format('F0GBR052TN')
MORNINGSTAR_WORLD_HEDGED_API_URL = API_PERFORMANCE_URL_TEMPLATE.format('F0GBR05PLZ')
# --- NUEVA LÍNEA AÑADIDA ---
MORNINGSTAR_GREATER_CHINA_API_URL = API_PERFORMANCE_URL_TEMPLATE.format('F0GBR04LGV')


# URL para rentabilidad "Desde su creación"
MORNINGSTAR_SP500_INCEPTION_API_URL = API_TRAILING_RETURN_URL_TEMPLATE.format('F0GBR04UOL')

# URLs de otras fuentes
TRADINGVIEW_USDEUR_URL = 'https://es.tradingview.com/symbols/USDEUR/?exchange=FX_IDC&timeframe=YTD'
ECB_ESTR_URL = 'https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_short-term_rate/html/index.en.html'
BOGLE_QUOTES_URL = 'https://www.gestionpasiva.com/john-bogle-en-30-grandes-citas/'

DEFAULT_SELECTOR = 'span[data-test="instrument-price-change-percent"]'
INSTRUMENTS_DATA = {
    "sp500_net_eur": {"display_name": "S&P 500 NETO EUROS", "url": "https://es.investing.com/indices/msci-us-net-eur", "comment": "Este es el índice que hay que mirar si quieres ver como queda el SP500 ya en euros, es el que os importa para saber cuánto dinero vais a ganar al día siguiente.", "selector": DEFAULT_SELECTOR},
    "sp500_usd": {"display_name": "S&P 500 INDICE OFICIAL EN DOLARES", "url": "https://es.investing.com/indices/us-spx-500", "comment": "Por si queréis ver como va el SP500 de forma \"oficial\" en dólares, no es relevante para vosotros.", "selector": DEFAULT_SELECTOR},
    "sp500_futures": {"display_name": "S&P 500 $ FUTURO", "url": "https://es.investing.com/indices/us-spx-500-futures?cid=1175153", "comment": "Por si queréis ver como se prevé que abra la sesión próxima del SP500. Funciona en tiempo real de forma diaria, solo es útil cuándo el mercado está cerrado (por la mañana para nosotros) y está en dolares. Sirve para haceros una idea de, viendo esta cotización y la del $/€, saber si abrirá plano, verde/rojo tímido, o positivo/negativo.", "selector": DEFAULT_SELECTOR},
    "world_net_eur": {"display_name": "MUNDO NETO EN EUROS", "url": "https://es.investing.com/indices/msci-world-net-eur", "comment": "Por si queréis ver como va el World (Mundo) en comparación con el SP500, ya esta neteado también en €, esto es lo que gano yo básicamente con mi principal fondo.", "selector": DEFAULT_SELECTOR},
    "usd_eur": {"display_name": "USD/EUR", "url": "https://es.investing.com/currencies/usd-eur", "comment": "Cotización del par $/€, BÁSICAMENTE: SI ESTÁ EN VERDE, OS BENEFICIA, SI ESTÁ EN ROJO, OS PERJUDICA.", "selector": DEFAULT_SELECTOR}
}

HEADERS_MORNINGSTAR_API = {
    'accept': '*/*', 'accept-language': 'es-ES,es;q=0.8', 'apikey': 'lstzFDEOhfFNMLikKa0am9mgEKLBl49T', 'origin': 'https://global.morningstar.com', 'referer': 'https://global.morningstar.com/',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

bogle_quotes_cache = []

def scrape_ytd_from_morningstar_api(url, headers):
    try:
        logging.info(f"Fetching YTD from Morningstar API: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        growth_data = data.get("table", {}).get("growth10KReturnData", [])
        fund_data = next((item for item in growth_data if item.get("label") == "fund"), None)
        if fund_data and "datum" in fund_data and fund_data["datum"]:
            ytd_value_str = fund_data["datum"][-1]
            if ytd_value_str is None:
                return "N/A", None
            ytd_value = float(ytd_value_str)
            formatted_value = f"{ytd_value:+.2f}".replace('.', ',') + '%'
            return formatted_value, None
        return None, "Dato YTD no encontrado en API"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red (API): {e}"
    except Exception as e:
        return None, f"Error procesando datos de API: {e}"

def scrape_inception_return_from_api(url, headers):
    try:
        logging.info(f"Fetching Inception Return from API: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        net_return_list = data.get("netReturn", [])
        if net_return_list:
            inception_value_str = net_return_list[-1]
            if inception_value_str is None:
                return "N/A", None
            inception_value = float(inception_value_str)
            formatted_value = f"{inception_value:+.2f}".replace('.', ',') + '%'
            return formatted_value, None
        return None, "Dato 'netReturn' no encontrado en API"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red (API Inception): {e}"
    except Exception as e:
        return None, f"Error procesando datos de API Inception: {e}"

def parse_percentage_to_float(perc_str):
    if not perc_str: return None
    try:
        cleaned_str = perc_str.replace('−', '-').replace('(', '').replace(')', '').replace('%', '').replace(',', '.').replace('+', '')
        return float(cleaned_str)
    except (ValueError, TypeError):
        logging.warning(f"Could not parse percentage string: {perc_str}")
        return None

def get_current_spain_time():
    try:
        return datetime.now(pytz.timezone('Europe/Madrid'))
    except Exception as e:
        logging.error(f"Error getting Spain time: {e}. Defaulting to server time.")
        return datetime.now().astimezone()

def get_market_status(instrument_key, spain_time):
    is_weekday = spain_time.weekday() < 5
    hour, minute = spain_time.hour, spain_time.minute
    is_us_market_open = (15, 30) <= (hour, minute) < (22, 0)
    us_indices = ["sp500_net_eur", "sp500_usd"]
    continuous_markets = ["sp500_futures", "usd_eur", "world_net_eur"]
    if instrument_key in us_indices:
        return "ABIERTO" if is_weekday and is_us_market_open else "CERRADO"
    elif instrument_key in continuous_markets:
        return "ACTIVO" if is_weekday else "CERRADO"
    return ""

def scrape_instrument_data(instrument_url, css_selector):
    try:
        logging.info(f"Fetching URL: {instrument_url}")
        response = requests.get(instrument_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        element = soup.select_one(css_selector)
        if element: return element.get_text(strip=True), None
        else: return None, "Elemento no encontrado"
    except Exception as e:
        return None, f"Error de red: {str(e)}"

def scrape_tradingview_ytd_data(url, headers):
    try:
        logging.info(f"Fetching TradingView URL: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        selector = 'button[class*="selected"] span[class*="change-"]'
        value_element = soup.select_one(selector)
        if value_element:
            value_text = value_element.get_text(strip=True)
            if '%' not in value_text:
                value_text += '%'
            return value_text, None
        return None, "Dato YTD no encontrado"
    except Exception as e:
        return None, "No se pudo procesar la página"

def scrape_ecb_rate_data(url, headers):
    try:
        logging.info(f"Fetching ECB URL: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        data_cell = soup.select_one('td strong')
        if data_cell:
            value_text = data_cell.get_text(strip=True)
            return f"{value_text}%", None
        return None, "Dato 'Rate' no encontrado"
    except Exception as e:
        return None, "No se pudo procesar la página"

def scrape_indexa_data(headers):
    today = date.today()
    start_of_year = today.strftime("01-01-%Y")
    today_str = today.strftime("%d-%m-%Y")
    url = f"https://indexacapital.com/es/esp/stats?from={start_of_year}&to={today_str}&risk=10&size=medium&style=capitalization"
    try:
        logging.info(f"Fetching Indexa Capital URL: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        selector = "td.border-left.js-plusmin"
        value_cell = soup.select_one(selector)
        if value_cell:
            value_text = value_cell.get_text(strip=True).replace('\xa0', ' ')
            return value_text, None
        return None, "Dato 'TOTAL' no encontrado (v2)"
    except Exception as e:
        return None, "No se pudo procesar la página"

def get_bogle_quotes():
    global bogle_quotes_cache
    if bogle_quotes_cache:
        return random.choice(bogle_quotes_cache)
    try:
        logging.info(f"Fetching Bogle quotes from: {BOGLE_QUOTES_URL}")
        response = requests.get(BOGLE_QUOTES_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        quotes = [p.get_text(strip=True, separator=' ') for p in soup.select('div.thrv_tw_quote p')]
        if quotes:
            bogle_quotes_cache = quotes
            return random.choice(bogle_quotes_cache)
        return "No invierta, simplemente, posea acciones."
    except Exception as e:
        return "El error más grande es no permanecer en el camino."

@app.route('/all_instrument_data')
def get_all_instrument_data():
    try:
        instrument_values_temp = {}
        current_spain_time = get_current_spain_time()
        for key, info in INSTRUMENTS_DATA.items():
            perc_str, error = scrape_instrument_data(info['url'], info['selector'])
            instrument_values_temp[key] = {
                "percentage_str": perc_str, "percentage_float": parse_percentage_to_float(perc_str),
                "error": error, "market_status": get_market_status(key, current_spain_time)
            }
        
        current_hour_spain = current_spain_time.hour
        sp500_comment_text, sp500_comment_sentiment = "", "neutral"
        if 8 <= current_hour_spain < 15:
            future_perc = instrument_values_temp.get("sp500_futures", {}).get("percentage_float")
            usd_eur_perc = instrument_values_temp.get("usd_eur", {}).get("percentage_float")
            if future_perc is not None and usd_eur_perc is not None:
                predicted_opening = future_perc + usd_eur_perc
                formatted_prediction = f"{predicted_opening:+.2f}%".replace('.', ',')
                sp500_comment_text = f"S&P 500: Se prevé que abra sobre {formatted_prediction}."
                if predicted_opening > 0: sp500_comment_sentiment = "positive"
                elif predicted_opening < 0: sp500_comment_sentiment = "negative"
        else:
            sp_net_eur_perc = instrument_values_temp.get("sp500_net_eur", {}).get("percentage_float")
            if sp_net_eur_perc is not None:
                if sp_net_eur_perc > 0.50: sp500_comment_text, sp500_comment_sentiment = "S&P 500 (en €): ¡Pinta bien la cosa, se viene verde positivo!", "positive"
                elif sp_net_eur_perc > 0: sp500_comment_text, sp500_comment_sentiment = "S&P 500 (en €): Verde tímido.", "positive"
                elif sp_net_eur_perc == 0: sp500_comment_text, sp500_comment_sentiment = "S&P 500 (en €): Cotiza plano actualmente.", "neutral"
                elif sp_net_eur_perc >= -0.50: sp500_comment_text, sp500_comment_sentiment = "S&P 500 (en €): Rojo tímido.", "negative"
                else: sp500_comment_text, sp500_comment_sentiment = "S&P 500 (en €): Pinta mal, parece que se viene un buen rojo hoy.", "negative"
        
        world_perc = instrument_values_temp.get("world_net_eur", {}).get("percentage_float")
        world_comment_text, world_comment_sentiment = "", "neutral"
        if world_perc is not None:
            if world_perc > 0.05: world_comment_text, world_comment_sentiment = "MSCI World (en €): ¡Pinta bien la cosa, parece que se viene verde!", "positive"
            elif world_perc < -0.05: world_comment_text, world_comment_sentiment = "MSCI World (en €): Pinta mal, parece que se viene rojo hoy", "negative"
            else: world_comment_text, world_comment_sentiment = "MSCI World (en €): Se mantiene estable.", "neutral"
            
        final_instrument_data = {}
        for key, info in INSTRUMENTS_DATA.items():
            data_dict = instrument_values_temp[key]
            final_instrument_data[key] = {
                "display_name": info['display_name'], "comment": info['comment'],
                "percentage_change": data_dict["percentage_str"], "error": data_dict["error"],
                "id_key": key, "market_status": data_dict["market_status"]
            }
        
        sp500_eur_ytd_str, sp500_eur_ytd_error = scrape_ytd_from_morningstar_api(MORNINGSTAR_SP500_API_URL, HEADERS_MORNINGSTAR_API)
        sp500_usd_ytd_str, sp500_usd_ytd_error = scrape_ytd_from_morningstar_api(MORNINGSTAR_SP500_USD_API_URL, HEADERS_MORNINGSTAR_API)
        world_ytd_str, world_ytd_error = scrape_ytd_from_morningstar_api(MORNINGSTAR_WORLD_API_URL, HEADERS_MORNINGSTAR_API)
        world_hedged_ytd_str, world_hedged_ytd_error = scrape_ytd_from_morningstar_api(MORNINGSTAR_WORLD_HEDGED_API_URL, HEADERS_MORNINGSTAR_API)
        sp500_inception_str, sp500_inception_error = scrape_inception_return_from_api(MORNINGSTAR_SP500_INCEPTION_API_URL, HEADERS_MORNINGSTAR_API)
        usdeur_ytd_str, usdeur_ytd_error = scrape_tradingview_ytd_data(TRADINGVIEW_USDEUR_URL, HEADERS)
        money_market_rate_str, money_market_rate_error = scrape_ecb_rate_data(ECB_ESTR_URL, HEADERS)
        indexa_rate_str, indexa_rate_error = scrape_indexa_data(HEADERS)
        # --- NUEVA LÍNEA AÑADIDA ---
        greater_china_ytd_str, greater_china_ytd_error = scrape_ytd_from_morningstar_api(MORNINGSTAR_GREATER_CHINA_API_URL, HEADERS_MORNINGSTAR_API)
        
        random_bogle_quote = get_bogle_quotes()

        return jsonify({
            "data_fetched_at": datetime.now(pytz.utc).isoformat(),
            "instruments": final_instrument_data,
            "page_commentaries": {
                "sp500_insight": {"text": sp500_comment_text, "sentiment": sp500_comment_sentiment},
                "world_insight": {"text": world_comment_text, "sentiment": world_comment_sentiment}
            },
            "page_data": {
                "sp500_ytd": { "performance_str": sp500_eur_ytd_str, "error": sp500_eur_ytd_error },
                "sp500_usd_ytd": { "performance_str": sp500_usd_ytd_str, "error": sp500_usd_ytd_error },
                "world_ytd": { "performance_str": world_ytd_str, "error": world_ytd_error },
                "world_hedged_ytd": { "performance_str": world_hedged_ytd_str, "error": world_hedged_ytd_error },
                "usdeur_ytd": { "performance_str": usdeur_ytd_str, "error": usdeur_ytd_error },
                "sp500_10y_annualized": { "performance_str": sp500_inception_str, "error": sp500_inception_error },
                "money_market_rate": { "performance_str": money_market_rate_str, "error": money_market_rate_error },
                "indexa_rate": { "performance_str": indexa_rate_str, "error": indexa_rate_error },
                # --- NUEVA LÍNEA AÑADIDA ---
                "greater_china_ytd": { "performance_str": greater_china_ytd_str, "error": greater_china_ytd_error }
            },
            "quote": random_bogle_quote
        })
    except Exception as e:
        logging.error(f"Error fatal en la ruta /all_instrument_data: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Ocurrió un error interno en el servidor."}), 500

