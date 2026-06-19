import os
import logging
import requests
import re
import sys
import cloudscraper
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

        # --- CAMBIO CLAVE: Usamos cloudscraper para imitar un navegador real ---
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )

        retry_strategy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=2,
            status_forcelist=[
                429,
                500,
                502,
                503,
                504
            ],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_current_status(self) -> str:
        try:
            response = self.session.get(
                self.url,
                timeout=15
            )

            response.raise_for_status()

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

        except requests.exceptions.RequestException as e:
            logging.error(
                f"Network or HTTP error accessing the website: {e}"
            )
            return None

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
