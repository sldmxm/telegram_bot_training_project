import json
import logging
import os
import sys
from time import time, sleep
import requests

from dotenv import load_dotenv
import telegram

from exceptions import TelegramTimedOut


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

TIMEOUT = 3
RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(message, bot):
    """Отправляет сообщение TELEGRAM_CHAT_ID."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            timeout=TIMEOUT
        )
    except telegram.error.TimedOut:
        raise TelegramTimedOut(
            'Не удалось отправить сообщение в Telegram за отведенное время'
        )
    except telegram.error.Unauthorized:
        raise telegram.error.Unauthorized(
            'Не удалось пройти авторизацию для отправки сообщения в Telegram'
        )
    except Exception as error:
        raise Exception(
            f'Попытка отправить сообщение закончилась ошибкой "{error}"'
        )
    else:
        logging.info(f'Сообщение "{message}" отправлено в телеграм')
    return


def get_api_answer(current_timestamp):
    """
    Делает запрос к эндпоинту API-сервиса.
    В случае успешного запроса возвращает ответ API,
    преобразовав его из формата JSON к типам данных Python.
    """
    try:
        api_data = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': current_timestamp},
            timeout=TIMEOUT
        )
        # можно было сделать все через except,
        # но в тестах не предусмотрено использование raise_for_status:
        # "'MockResponseGET' object has no attribute 'raise_for_status'"
        if api_data.status_code == 200:
            api_data = api_data.json()
        else:
            raise requests.HTTPError(
                f'Запрос к API ({api_data.url}) '
                f'вернул ошибку "{api_data.status_code}".'
            )
    except requests.ConnectTimeout:
        raise requests.ConnectTimeout(
            f'Ответ API ({api_data.url}) '
            f'не получен за {TIMEOUT} секунд.'
        )
    except json.decoder.JSONDecodeError:
        raise json.decoder.JSONDecodeError(
            f'В ответе API ({api_data.url}) не JSON.'
        )
    else:
        return api_data


def check_response(response):
    """
    Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям,
    возвращает список домашних работ,
    доступный в ответе API по ключу 'homeworks'.
    """
    if not isinstance(response, dict):
        raise TypeError('API вернул не словарь')
    if 'homeworks' not in response:
        raise KeyError(
            'В ответе API нет ключа "homeworks"')
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            'В ответе API "homeworks" не содержит список')
    if ('current_date' not in response
            or type(response['current_date']) is not int):
        logging.info(
            'В ответе API нет ключа "current_date", содержащего время ответа')
    return response['homeworks']


def parse_status(homework):
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра получает один элемент из списка домашних работ.
    Возвращает подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES.
    """
    if 'status' not in homework:
        raise KeyError("Нет ключа 'status' в ответе API")
    if 'homework_name' not in homework:
        raise KeyError("Нет ключа 'homework_name' в ответе API")
    homework_name = homework['homework_name']
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError(f"Неожиданный статус работы: '{homework_status}'")
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие переменных окружения."""
    # не понял, как использовать словарь globals() для проверки (
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


def main():
    """
    Основная логика работы бота.
    - Сделать запрос к API.
    - Проверить ответ.
    - Если есть обновления — получить статус работы из обновления
        и отправить сообщение в TELEGRAM_CHAT_ID.
    - Подождать некоторое RETRY_TIME и сделать новый запрос.
    """
    if not check_tokens():
        sys.exit('Нет переменных окружения!')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    last_error_message = ''
    current_timestamp = int(time())

    while True:
        try:
            api_data = get_api_answer(current_timestamp)
            homework_statuses = check_response(api_data)
            if len(homework_statuses) > 0:
                for homework in homework_statuses:
                    if parse_status(homework):
                        send_message(parse_status(homework), bot)
            else:
                logging.debug('Нет обновлений, я проверил')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if message != last_error_message:
                send_message(message, bot)
                last_error_message = message
        else:
            current_timestamp = api_data['current_date'] or current_timestamp
        finally:
            sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format=('%(asctime)s '
                '- %(levelname)s '
                # учитывая, что почти все логгируется в 170 строке main'а,
                # получилось не очень информативно, документацию почитал,
                # простого способа логгировать место ошибки не нашел
                '- строка %(lineno)d '
                '- %(funcName)s '
                '- %(message)s'
                )
    )
    main()
