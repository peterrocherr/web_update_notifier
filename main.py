import os
import logging
import requests
import re
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

# Configuración de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class BotComms(ABC):
    @abstractmethod
    def enviar_mensaje(self, mensaje: str): pass

class TelegramBot(BotComms):
    def __init__(self, token: str, chat_id: str):
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def enviar_mensaje(self, mensaje: str):
        try:
            requests.post(self.api_url, json={"chat_id": self.chat_id, "text": mensaje}, timeout=10).raise_for_status()
            logging.info("Notificación enviada a Telegram.")
        except Exception as e:
            logging.error(f"Error con Telegram: {e}")

class PageReader:
    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
        })

    def obtener_estado_actual(self) -> str:
        try:
            response = self.session.get(self.url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Buscar la clase estándar de WooCommerce
            elemento_stock = soup.find(class_='stock')
            if elemento_stock:
                return elemento_stock.text.strip()

            # Búsqueda de respaldo por la palabra "Availability:"
            etiqueta_disponibilidad = soup.find(string=re.compile("Availability:", re.IGNORECASE))
            if etiqueta_disponibilidad:
                return etiqueta_disponibilidad.parent.text.replace("Availability:", "").strip()

            return "ESTADO DESCONOCIDO"
        except Exception as e:
            logging.error(f"Error de red: {e}")
            return None

class Checker:
    def __init__(self, reader, bot, archivo_estado="ultimo_estado.txt"):
        self.reader = reader
        self.bot = bot
        self.archivo_estado = archivo_estado

    def ejecutar(self):
        estado_actual = self.reader.obtener_estado_actual()
        if not estado_actual: return # Si hay error de red, abortamos

        ultimo_estado = None
        if os.path.exists(self.archivo_estado):
            with open(self.archivo_estado, 'r', encoding='utf-8') as f:
                ultimo_estado = f.read().strip()

        if ultimo_estado is None:
            # Primera ejecución: guarda pero no avisa
            with open(self.archivo_estado, 'w', encoding='utf-8') as f: f.write(estado_actual)
            logging.info(f"Estado inicial guardado: {estado_actual}")
            return

        if estado_actual != ultimo_estado:
            self.bot.enviar_mensaje(f"🔔 ¡Actualización de Stock!\n\nProducto: Estradiol Enanthate\nEstado actual: {estado_actual}\nEnlace: {self.reader.url}")
            with open(self.archivo_estado, 'w', encoding='utf-8') as f: f.write(estado_actual)
            logging.info("Cambio detectado y notificado.")
        else:
            logging.info("Sin cambios en el stock.")

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    URL = os.getenv("URL_PRODUCTO")
    
    mi_checker = Checker(PageReader(URL), TelegramBot(TOKEN, CHAT_ID))
    mi_checker.ejecutar()
