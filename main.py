import os
import logging
import requests
import re
import sys
import tls_client
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

# Clean logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class BotComms(ABC):
    @abstractmethod
    def send_message(self, message: str):
        pass


class TelegramBot(BotComms):
    def __init__(self, token: str, chat_id: str):
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send_message(self, message: str):
        try:
            # We use standard requests for Telegram API (no anti-bot needed here)
            response = requests.post(
                self.api_url,
                json={
                    "chat_id": self.chat_id,
                    "text": message
                },
                timeout=10
            )
            response.raise_for_status()
            logging.info("Notification sent to Telegram successfully.")

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send message to Telegram: {e}")


class PageReader:
    def __init__(self, url: str):
        self.url = url

        # --- CAMBIO CLAVE: tls_client para bypass avanzado ---
        # Imitamos a un navegador Chrome muy específico
        self.session = tls_client.Session(
            client_identifier="chrome_120",
            random_tls_extension_order=True
        )

        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1'
        })

    def get_current_status(self) -> str:
        try:
            # Intentos manuales (tls_client no tiene adapter nativo como requests)
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                response = self.session.get(
                    self.url,
                    timeout_seconds=15
                )
                
                # tls_client uses .status_code instead of raise_for_status()
                if response.status_code == 200:
                    break
                else:
                    logging.warning(f"Attempt {attempt + 1} failed with status code: {response.status_code}")
                    import time
                    time.sleep(2) # Backoff manual

            if response.status_code != 200:
                logging.error(f"Failed to load page after {max_retries} attempts. Status: {response.status_code}")
                return None

            soup = BeautifulSoup(
                response.text,
                'html.parser'
            )

            stock_element = soup.find(class_='stock')

            if stock_element:
                return stock_element.text.strip()

            availability_label = soup.find(
                string=re.compile(
                    "Availability:",
                    re.IGNORECASE
                )
            )

            if availability_label and availability_label.parent:
                return (
                    availability_label.parent.text
                    .replace("Availability:", "")
                    .strip()
                )

            logging.warning(
                "Could not find standard stock indicators on the page."
            )

            return "UNKNOWN STATUS"

        except Exception as e:
            logging.error(
                f"Unexpected error parsing the website: {e}"
            )
            return None


class Checker:
    def __init__(
        self,
        reader,
        bot,
        status_file="ultimo_estado.txt"
    ):
        self.reader = reader
        self.bot = bot
        self.status_file = status_file

    def _read_last_status(self):
        try:
            if os.path.exists(self.status_file):
                with open(
                    self.status_file,
                    'r',
                    encoding='utf-8'
                ) as f:
                    return f.read().strip()

            return None

        except IOError as e:
            logging.error(
                f"Error reading status file: {e}"
            )
            return None

    def _save_current_status(
        self,
        status: str
    ):
        try:
            with open(
                self.status_file,
                'w',
                encoding='utf-8'
            ) as f:
                f.write(status)

        except IOError as e:
            logging.error(
                f"Error writing to status file: {e}"
            )

    def execute(self):
        logging.info(
            "Checking product status..."
        )

        current_status = (
            self.reader.get_current_status()
        )

        # Abort cycle if there was a network error
        if not current_status:
            logging.warning(
                "Cycle aborted due to missing status data."
            )
            return

        last_status = (
            self._read_last_status()
        )

        if last_status is None:
            logging.info(
                f"First run detected. "
                f"Initial status saved: '{current_status}'."
            )

            self._save_current_status(
                current_status
            )

            return

        if current_status != last_status:
            logging.info(
                f"Status changed: "
                f"'{last_status}' -> '{current_status}'. "
                f"Notifying."
            )

            message = (
                "🔔 Stock Update!\n\n"
                f"Current status: {current_status}\n"
                f"Link: {self.reader.url}"
            )

            self.bot.send_message(
                message
            )

            self._save_current_status(
                current_status
            )

        else:
            logging.info(
                "No changes in stock. "
                f"Current status is still: "
                f"'{current_status}'."
            )


if __name__ == "__main__":
    TOKEN = os.getenv(
        "TELEGRAM_TOKEN"
    )

    CHAT_ID = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    URL = os.getenv(
        "URL_PRODUCTO"
    )

    missing_secrets = []

    if not TOKEN:
        missing_secrets.append(
            "TELEGRAM_TOKEN"
        )

    if not CHAT_ID:
        missing_secrets.append(
            "TELEGRAM_CHAT_ID"
        )

    if not URL:
        missing_secrets.append(
            "URL_PRODUCTO"
        )

    if missing_secrets:
        logging.critical(
            "Missing required environment variables: "
            f"{', '.join(missing_secrets)}. "
            "Please check GitHub Secrets."
        )

        sys.exit(1)

    my_checker = Checker(
        PageReader(URL),
        TelegramBot(
            TOKEN,
            CHAT_ID
        )
    )

    my_checker.execute()
