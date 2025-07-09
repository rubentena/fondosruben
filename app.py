from flask import Flask,jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import logging,traceback,json,urllib.parse
from datetime import datetime,date
import pytz,re,random
import concurrent.futures
from time import time

app=Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO,format='%(levelname)s:%(name)s:%(message)s')

# --- Constantes y URLs ---
API_PERFORMANCE_URL_TEMPLATE='https://api-global.morningstar.com/sal-service/v1/fund/performance/v5/{}?secExchangeList=&limitAge=&hideYTD=false&languageId=es&locale=es&clientId=MDC&benchmarkId=mstarorcat&component=sal-mip-growth-10k&version=4.65.0'
API_TRAILING_RETURN_URL_TEMPLATE='https://api-global.morningstar.com/sal-service/v1/fund/trailingReturn/v3/{}/data?duration=quarterly&limitAge=&languageId=es&locale=es&clientId=MDC&benchmarkId=mstarorcat&component=sal-mip-trailing-return&version=4.65.0'
MORNINGSTAR_SP500_API_URL=API_PERFORMANCE_URL_TEMPLATE.format('F0GBR04UOL')
MORNINGSTAR_SP500_USD_API_URL=API_PERFORMANCE_URL_TEMPLATE.format('F0000000VM')
MORNINGSTAR_WORLD_API_URL=API_PERFORMANCE_URL_TEMPLATE.format('F0GBR052TN')
MORNINGSTAR_WORLD_HEDGED_API_URL=API_PERFORMANCE_URL_TEMPLATE.format('F0GBR05PLZ')
MORNINGSTAR_GREATER_CHINA_API_URL=API_PERFORMANCE_URL_TEMPLATE.format('F0GBR04LGV')
MORNINGSTAR_SP500_INCEPTION_API_URL=API_TRAILING_RETURN_URL_TEMPLATE.format('F0GBR04UOL')
TRADINGVIEW_USDEUR_URL='https://es.tradingview.com/symbols/USDEUR/?exchange=FX_IDC&timeframe=YTD'
ECB_ESTR_URL='https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_short-term_rate/html/index.en.html'
BOGLE_QUOTES_URL='https://www.gestionpasiva.com/john-bogle-en-30-grandes-citas/'
DEFAULT_SELECTOR='span[data-test="instrument-price-change-percent"]'

INSTRUMENTS_DATA={
    'sp500_net_eur':{'display_name':'S&P 500 NETO EUROS','url':'https://es.investing.com/indices/msci-us-net-eur','comment':'Este es el índice que hay que mirar si quieres ver como queda el SP500 ya en euros, es el que os importa para saber cuánto dinero vais a ganar al día siguiente.','selector':DEFAULT_SELECTOR},
    'sp500_usd':{'display_name':'S&P 500 INDICE OFICIAL EN DOLARES','url':'https://es.investing.com/indices/us-spx-500','comment':'Por si queréis ver como va el SP500 de forma "oficial" en dólares, no es relevante para vosotros.','selector':DEFAULT_SELECTOR},
    'sp500_futures':{'display_name':'S&P 500 $ FUTURO','url':'https://es.investing.com/indices/us-spx-500-futures?cid=1175153','comment':'Por si queréis ver como se prevé que abra la sesión próxima del SP500. Funciona en tiempo real de forma diaria, solo es útil cuándo el mercado está cerrado (por la mañana para nosotros) y está en dolares. Sirve para haceros una idea de, viendo esta cotización y la del $/€, saber si abrirá plano, verde/rojo tímido, o positivo/negativo.','selector':DEFAULT_SELECTOR},
    'world_net_eur':{'display_name':'MUNDO NETO EN EUROS','url':'https://es.investing.com/indices/msci-world-net-eur','comment':'Por si queréis ver como va el World (Mundo) en comparación con el SP500, ya esta neteado también en €, esto es lo que gano yo básicamente con mi principal fondo.','selector':DEFAULT_SELECTOR},
    'usd_eur':{'display_name':'USD/EUR','url':'https://es.investing.com/currencies/usd-eur','comment':'Cotización del par $/€, BÁSICAMENTE: SI ESTÁ EN VERDE, OS BENEFICIA, SI ESTÁ EN ROJO, OS PERJUDICA.','selector':DEFAULT_SELECTOR},
    'bitcoin_eur':{'display_name':'BITCOIN','comment':'Cotización del Bitcoin en euros. Mercado activo 24/7. Fuente: Kraken API.','api_source': 'kraken','api_pair': 'BTCEUR'}
}

HEADERS_MORNINGSTAR_API={'accept':'*/*','accept-language':'es-ES,es;q=0.8','apikey':'lstzFDEOhfFNMLikKa0am9mgEKLBl49T','origin':'https://global.morningstar.com','referer':'https://global.morningstar.com/','sec-ch-ua':'"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"','sec-ch-ua-mobile':'?0','sec-ch-ua-platform':'"Windows"','sec-fetch-dest':'empty','sec-fetch-mode':'cors','sec-fetch-site':'same-site','user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36','Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7','Accept-Language': 'es-ES,es;q=0.9','Referer': 'https://www.google.com/','Upgrade-Insecure-Requests': '1','DNT': '1'}

# --- Sistema de Caché ---
CACHE_DURATION = 900  # 15 minutos en segundos
_cache = {}
_cache_timestamps = {}

def get_cached_or_fetch(key, fetch_func, *args, **kwargs):
    """
    Wrapper para obtener datos de la caché o, si han expirado,
    llamando a la función de scraping correspondiente.
    """
    now = time()
    if key in _cache and (now - _cache_timestamps.get(key, 0)) < CACHE_DURATION:
        logging.info(f"Sirviendo '{key}' desde la caché.")
        return _cache[key]
    
    logging.info(f"Caché para '{key}' no encontrada o expirada. Haciendo fetch.")
    result, error = fetch_func(*args, **kwargs)

    if error is None:  # Solo guardar en caché si la petición fue exitosa
        _cache[key] = (result, error)
        _cache_timestamps[key] = now
        
    return result, error

# --- Funciones de Scraping (sin cambios) ---
def scrape_ytd_from_morningstar_api(url,headers):
	try:
		logging.info(f"Fetching YTD from Morningstar API: {url}");response=requests.get(url,headers=headers,timeout=10);response.raise_for_status();data=response.json();growth_data=data.get('table',{}).get('growth10KReturnData',[]);fund_data=next((item for item in growth_data if item.get('label')=='fund'),None)
		if fund_data and'datum'in fund_data and fund_data['datum']:
			ytd_value_str=fund_data['datum'][-1]
			if ytd_value_str is None:return'N/A',None
			ytd_value=float(ytd_value_str);formatted_value=f"{ytd_value:+.2f}".replace('.',',')+'%';return formatted_value,None
		return None,'Dato YTD no encontrado en API'
	except requests.exceptions.RequestException as e:return None,f"Error de red (API): {e}"
	except Exception as e:return None,f"Error procesando datos de API: {e}"

def scrape_inception_return_from_api(url,headers):
	try:
		logging.info(f"Fetching Inception Return from API: {url}");response=requests.get(url,headers=headers,timeout=10);response.raise_for_status();data=response.json();net_return_list=data.get('netReturn',[])
		if net_return_list:
			inception_value_str=net_return_list[-1]
			if inception_value_str is None:return'N/A',None
			inception_value=float(inception_value_str);formatted_value=f"{inception_value:+.2f}".replace('.',',')+'%';return formatted_value,None
		return None,"Dato 'netReturn' no encontrado en API"
	except requests.exceptions.RequestException as e:return None,f"Error de red (API Inception): {e}"
	except Exception as e:return None,f"Error procesando datos de API Inception: {e}"

def scrape_instrument_data(instrument_url,css_selector):
	try:
		logging.info(f"Fetching URL: {instrument_url}");response=requests.get(instrument_url,headers=HEADERS,timeout=10);response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser');element=soup.select_one(css_selector)
		if element:return element.get_text(strip=True),None
		else:return None,'Elemento no encontrado'
	except Exception as e:return None,f"Error de red: {str(e)}"

def scrape_crypto_data_from_kraken(pair):
    url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    try:
        logging.info(f"Fetching crypto data from Kraken API for {pair}")
        response = requests.get(url, timeout=10)
        response.raise_for_status();data = response.json()
        if data.get('error'): return None, f"Error de API Kraken: {data['error']}"
        result_key = list(data['result'].keys())[0];ticker_data = data['result'][result_key]
        opening_price = float(ticker_data['o']);last_price = float(ticker_data['c'][0])
        if opening_price == 0: return "N/A", None
        percentage_change = ((last_price / opening_price) - 1) * 100
        formatted_change = f"{percentage_change:+.2f}".replace('.', ',')
        return f"({formatted_change}%)", None
    except Exception as e: return None, f"Error procesando Kraken API: {str(e)}"

def scrape_tradingview_ytd_data(url,headers):
	try:
		logging.info(f"Fetching TradingView URL: {url}");response=requests.get(url,headers=headers,timeout=10);response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser');selector='button[class*="selected"] span[class*="change-"]';value_element=soup.select_one(selector)
		if value_element:
			value_text=value_element.get_text(strip=True)
			if'%'not in value_text:value_text+='%'
			return value_text,None
		return None,'Dato YTD no encontrado'
	except Exception as e:return None,'No se pudo procesar la página'

def scrape_ecb_rate_data(url,headers):
	try:
		logging.info(f"Fetching ECB URL: {url}");response=requests.get(url,headers=headers,timeout=10);response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser');data_cell=soup.select_one('td strong')
		if data_cell:value_text=data_cell.get_text(strip=True);return f"{value_text}%",None
		return None,"Dato 'Rate' no encontrado"
	except Exception as e:return None,'No se pudo procesar la página'

def scrape_indexa_data(headers):
	today=date.today();start_of_year=today.strftime('01-01-%Y');today_str=today.strftime('%d-%m-%Y');url=f"https://indexacapital.com/es/esp/stats?from={start_of_year}&to={today_str}&risk=10&size=medium&style=capitalization"
	try:
		logging.info(f"Fetching Indexa Capital URL: {url}");response=requests.get(url,headers=headers,timeout=10);response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser');selector='td.border-left.js-plusmin';value_cell=soup.select_one(selector)
		if value_cell:value_text=value_cell.get_text(strip=True).replace('\xa0',' ');return value_text,None
		return None,"Dato 'TOTAL' no encontrado (v2)"
	except Exception as e:return None,'No se pudo procesar la página'

def calculate_bitcoin_cagr():
    try:
        logging.info("Calculating Bitcoin CAGR from Kraken historical data")
        url = "https://api.kraken.com/0/public/OHLC?pair=BTCEUR&interval=10080"
        response = requests.get(url, timeout=10);response.raise_for_status();data = response.json()
        if data.get('error') and len(data.get('error')) > 0: return None, f"Error de API Kraken (OHLC): {data['error']}"
        result_key = list(data['result'].keys())[0];ohlc_data = data['result'][result_key]
        if not ohlc_data or len(ohlc_data) < 2: return None, "No hay suficientes datos históricos de Kraken"
        start_point = ohlc_data[0];start_timestamp = start_point[0];start_price = float(start_point[4])
        end_point = ohlc_data[-1];end_timestamp = end_point[0];end_price = float(end_point[4])
        if start_price == 0: return None, "El precio inicial es cero, no se puede calcular CAGR"
        num_years = (end_timestamp - start_timestamp) / (365.25 * 24 * 60 * 60)
        if num_years < 1: return "N/A (periodo < 1 año)", None
        cagr = ((end_price / start_price) ** (1 / num_years)) - 1;cagr_percentage = cagr * 100
        formatted_cagr = f"{cagr_percentage:,.2f} %".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted_cagr, None
    except requests.exceptions.RequestException as e: return None, f"Error de red (Kraken OHLC): {e}"
    except Exception as e: return None, f"Error inesperado en cálculo de CAGR: {e}"

def get_bogle_quotes():
    # Esta función es tan rápida que la paralelización/caché no es crítica, pero se incluye por consistencia.
    if _cache.get('bogle_quotes'): return _cache['bogle_quotes'], None
    try:
        logging.info(f"Fetching Bogle quotes from: {BOGLE_QUOTES_URL}");response=requests.get(BOGLE_QUOTES_URL,headers=HEADERS,timeout=10);response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser');quotes=[p.get_text(strip=True,separator=' ')for p in soup.select('div.thrv_tw_quote p')]
        if quotes: _cache['bogle_quotes'] = quotes; return random.choice(quotes), None
        return'No invierta, simplemente, posea acciones.', None
    except Exception as e: return'El error más grande es no permanecer en el camino.', f'Error Bogle: {e}'

# --- Funciones de Lógica de la Aplicación (sin cambios) ---
def parse_percentage_to_float(perc_str):
	if not perc_str:return
	try:cleaned_str=perc_str.replace('−','-').replace('(','').replace(')','').replace('%','').replace(',','.').replace('+','');return float(cleaned_str)
	except(ValueError,TypeError):logging.warning(f"Could not parse percentage string: {perc_str}");return

def get_current_spain_time():
	try:return datetime.now(pytz.timezone('Europe/Madrid'))
	except Exception as e:logging.error(f"Error getting Spain time: {e}. Defaulting to server time.");return datetime.now().astimezone()

def get_market_status(instrument_key,spain_time):
	is_weekday=spain_time.weekday()<5;hour,minute=spain_time.hour,spain_time.minute;is_us_market_open=(15,30)<=(hour,minute)<(22,0);
	us_indices=['sp500_net_eur','sp500_usd']
	continuous_markets=['sp500_futures','usd_eur','world_net_eur']
	crypto_markets=['bitcoin_eur']
	if instrument_key in us_indices:return'ABIERTO'if is_weekday and is_us_market_open else'CERRADO'
	elif instrument_key in crypto_markets: return 'ACTIVO'
	elif instrument_key in continuous_markets:return'ACTIVO'if is_weekday else'CERRADO'
	return''

@app.route('/all_instrument_data')
def get_all_instrument_data():
    try:
        futures = {}
        # Usamos un ThreadPoolExecutor para lanzar todas las peticiones de red en paralelo
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # --- Tareas SIN caché (se ejecutan siempre) ---
            for key, info in INSTRUMENTS_DATA.items():
                if info.get('api_source') == 'kraken':
                    futures[key] = executor.submit(scrape_crypto_data_from_kraken, info['api_pair'])
                else:
                    futures[key] = executor.submit(scrape_instrument_data, info['url'], info['selector'])
            
            # --- Tareas CON caché (se ejecutan solo si la caché ha expirado) ---
            futures['sp500_ytd'] = executor.submit(get_cached_or_fetch, 'sp500_ytd', scrape_ytd_from_morningstar_api, MORNINGSTAR_SP500_API_URL, HEADERS_MORNINGSTAR_API)
            futures['sp500_usd_ytd'] = executor.submit(get_cached_or_fetch, 'sp500_usd_ytd', scrape_ytd_from_morningstar_api, MORNINGSTAR_SP500_USD_API_URL, HEADERS_MORNINGSTAR_API)
            futures['world_ytd'] = executor.submit(get_cached_or_fetch, 'world_ytd', scrape_ytd_from_morningstar_api, MORNINGSTAR_WORLD_API_URL, HEADERS_MORNINGSTAR_API)
            futures['world_hedged_ytd'] = executor.submit(get_cached_or_fetch, 'world_hedged_ytd', scrape_ytd_from_morningstar_api, MORNINGSTAR_WORLD_HEDGED_API_URL, HEADERS_MORNINGSTAR_API)
            futures['greater_china_ytd'] = executor.submit(get_cached_or_fetch, 'greater_china_ytd', scrape_ytd_from_morningstar_api, MORNINGSTAR_GREATER_CHINA_API_URL, HEADERS_MORNINGSTAR_API)
            futures['sp500_10y_annualized'] = executor.submit(get_cached_or_fetch, 'sp500_10y_annualized', scrape_inception_return_from_api, MORNINGSTAR_SP500_INCEPTION_API_URL, HEADERS_MORNINGSTAR_API)
            futures['usdeur_ytd'] = executor.submit(get_cached_or_fetch, 'usdeur_ytd', scrape_tradingview_ytd_data, TRADINGVIEW_USDEUR_URL, HEADERS)
            futures['money_market_rate'] = executor.submit(get_cached_or_fetch, 'money_market_rate', scrape_ecb_rate_data, ECB_ESTR_URL, HEADERS)
            futures['indexa_rate'] = executor.submit(get_cached_or_fetch, 'indexa_rate', scrape_indexa_data, HEADERS)
            futures['bitcoin_cagr'] = executor.submit(get_cached_or_fetch, 'bitcoin_cagr', calculate_bitcoin_cagr)
            futures['quote'] = executor.submit(get_cached_or_fetch, 'quote', get_bogle_quotes)

        # Recopilamos los resultados. El .result() espera a que la tarea termine.
        results = {key: future.result() for key, future in futures.items()}

        # --- Procesamiento de resultados (mucho más rápido, ya no hay esperas de red) ---
        current_spain_time = get_current_spain_time()
        instrument_values = {}
        for key in INSTRUMENTS_DATA.keys():
            perc_str, error = results[key]
            instrument_values[key] = {
                'percentage_str': perc_str,
                'percentage_float': parse_percentage_to_float(perc_str),
                'error': error,
                'market_status': get_market_status(key, current_spain_time)
            }
        
        # Construir comentarios de la página
        sp500_comment_text, sp500_comment_sentiment = '', 'neutral'
        if 8 <= current_spain_time.hour < 15:
            future_perc = instrument_values.get('sp500_futures',{}).get('percentage_float')
            usd_eur_perc = instrument_values.get('usd_eur',{}).get('percentage_float')
            if future_perc is not None and usd_eur_perc is not None:
                predicted_opening = future_perc + usd_eur_perc
                formatted_prediction = f"{predicted_opening:+.2f}%".replace('.',',')
                sp500_comment_text = f"S&P 500: Se prevé que abra sobre {formatted_prediction}."
                if predicted_opening > 0: sp500_comment_sentiment = 'positive'
                elif predicted_opening < 0: sp500_comment_sentiment = 'negative'
        else:
            sp_net_eur_perc = instrument_values.get('sp500_net_eur',{}).get('percentage_float')
            if sp_net_eur_perc is not None:
                if sp_net_eur_perc > .5: sp500_comment_text, sp500_comment_sentiment = 'S&P 500 (en €): ¡Pinta bien la cosa, se viene verde positivo!', 'positive'
                elif sp_net_eur_perc > 0: sp500_comment_text, sp500_comment_sentiment = 'S&P 500 (en €): Verde tímido.', 'positive'
                elif sp_net_eur_perc == 0: sp500_comment_text, sp500_comment_sentiment = 'S&P 500 (en €): Cotiza plano actualmente.', 'neutral'
                elif sp_net_eur_perc >= -.5: sp500_comment_text, sp500_comment_sentiment = 'S&P 500 (en €): Rojo tímido.', 'negative'
                else: sp500_comment_text, sp500_comment_sentiment = 'S&P 500 (en €): Pinta mal, parece que se viene un buen rojo hoy.', 'negative'
        
        world_perc = instrument_values.get('world_net_eur',{}).get('percentage_float')
        world_comment_text, world_comment_sentiment = '','neutral'
        if world_perc is not None:
            if world_perc > .05: world_comment_text, world_comment_sentiment = 'MSCI World (en €): ¡Pinta bien la cosa, parece que se viene verde!', 'positive'
            elif world_perc < -.05: world_comment_text, world_comment_sentiment = 'MSCI World (en €): Pinta mal, parece que se viene rojo hoy', 'negative'
            else: world_comment_text, world_comment_sentiment = 'MSCI World (en €): Se mantiene estable.', 'neutral'

        # Formatear el JSON de respuesta final
        final_instrument_data = {key: {
            'display_name': info['display_name'], 'comment': info['comment'], 'id_key': key,
            'percentage_change': instrument_values[key]['percentage_str'],
            'error': instrument_values[key]['error'],
            'market_status': instrument_values[key]['market_status']
        } for key, info in INSTRUMENTS_DATA.items()}

        page_data = {key: {'performance_str': res[0], 'error': res[1]} for key, res in results.items() if key not in INSTRUMENTS_DATA and key != 'quote'}
        
        return jsonify({
            'data_fetched_at': datetime.now(pytz.utc).isoformat(),
            'instruments': final_instrument_data,
            'page_commentaries': {
                'sp500_insight': {'text': sp500_comment_text, 'sentiment': sp500_comment_sentiment},
                'world_insight': {'text': world_comment_text, 'sentiment': world_comment_sentiment}
            },
            'page_data': page_data,
            'quote': results['quote'][0]
        })

    except Exception as e:
        logging.error(f"Error fatal en la ruta /all_instrument_data: {e}\n{traceback.format_exc()}")
        return jsonify({'error':'Ocurrió un error interno en el servidor.'}), 500