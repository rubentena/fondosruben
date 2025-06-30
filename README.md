# Panel de Seguimiento de Fondos

Un panel de control financiero personal para monitorizar en tiempo real el rendimiento de índices bursátiles y otros instrumentos financieros clave. La aplicación extrae datos de diversas fuentes web y los presenta en una interfaz limpia, moderna y fácil de usar.

## Descripción del Proyecto

Este proyecto nace de la necesidad de consolidar en un único lugar la información financiera dispersa en múltiples plataformas (Investing.com, Morningstar, etc.). La aplicación consta de un **backend en Flask (Python)** que realiza *web scraping* para obtener los datos más recientes, y un **frontend en HTML, CSS y JavaScript** que los consume y los muestra de forma intuitiva.

El panel está diseñado para ofrecer una visión rápida y clara del estado diario de los mercados, así como de la rentabilidad acumulada (YTD) de fondos de referencia como el S&P 500 y el MSCI World, todo ello contextualizado para un inversor europeo (con datos en EUR).

## Características Principales

* **Monitorización en Tiempo Real**: Sigue la cotización diaria de:
    * S&P 500 (en EUR y USD).
    * MSCI World (en EUR).
    * Futuros del S&P 500 para prever la apertura del mercado.
    * Tipo de cambio USD/EUR.
* **Rentabilidades Anuales (YTD)**: Muestra el rendimiento acumulado en el año de varios fondos e índices, incluyendo una comparativa con fondos de divisa cubierta y el mercado monetario.
* **Comentarios de Mercado Automatizados**: Genera análisis sencillos y directos sobre la posible apertura del mercado o su estado actual.
* **Interfaz Moderna y Amigable**:
    * Diseño *responsive* adaptable a escritorio y móvil.
    * **Tema claro y oscuro** con guardado de preferencias.
    * Actualización de datos manual y automática.
    * Visualización opcional de rentabilidades y calendario de festivos.
* **Citas Inspiradoras**: Muestra una cita de John C. Bogle en cada carga para mantener el foco en la filosofía de inversión a largo plazo.

## Stack Tecnológico

| Componente  | Tecnología/Librería | Propósito                                                       |
| :---------- | :------------------ | :-------------------------------------------------------------- |
| **Backend** | `Python`            | Lenguaje de programación principal.                             |
|             | `Flask`             | Microframework web para servir la API y el frontend.            |
|             | `requests`          | Para realizar peticiones HTTP a las fuentes de datos.           |
|             | `BeautifulSoup4`    | Para parsear el HTML y extraer la información (*scraping*).     |
|             | `pytz`              | Para un manejo preciso de las zonas horarias.                   |
| **Frontend**| `HTML5`             | Estructura de la página web.                                    |
|             | `CSS3`              | Estilos y diseño, incluyendo el modo oscuro y *responsive*.     |
|             | `JavaScript`        | Dinamismo, peticiones a la API y actualización del DOM.         |

## Instalación y Puesta en Marcha

Para ejecutar este proyecto en tu entorno local, sigue estos pasos:

1.  **Clona el repositorio:**
    ```bash
    git clone [https://github.com/fondosruben/fondosruben.git](https://github.com/fondosruben/fondosruben.git)
    cd fondosruben
    ```

2.  **Crea y activa un entorno virtual (recomendado):**
    ```bash
    # En macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # En Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Instala las dependencias:**
    Usa el archivo `requirements.txt` proporcionado.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Ejecuta la aplicación Flask:**
    ```bash
    flask run
    ```

5.  **Abre el panel en tu navegador:**
    Visita [`http://127.0.0.1:5000`](http://127.0.0.1:5000) en tu navegador web.

## Estructura de Archivos

/
├── app.py              # El servidor backend de Flask.
├── index.html          # La página principal (frontend).
├── requirements.txt    # Las dependencias de Python.
├── calendario_festivos.png # Imagen del calendario de festivos.
└── README.md           # Este archivo.


## Endpoint de la API

La aplicación expone un único endpoint que centraliza todos los datos.

* **GET `/all_instrument_data`**
    * **Descripción**: Devuelve un objeto JSON con todos los datos.
    * **Respuesta Exitosa (200 OK)**:
        ```json
        {
            "data_fetched_at": "2023-10-27T10:00:00.000Z",
            "instruments": { /* ... */ },
            "page_commentaries": { /* ... */ },
            "page_data": { /* ... */ },
            "quote": "Una cita de John Bogle..."
        }
        ```
