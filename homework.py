import logging
import os
import sys
from http import HTTPStatus
from time import time, sleep

import requests
from dotenv import load_dotenv
import telegram

from exceptions import (
    TelegramSendMessageError,
    APIError,
    BadCurrentDate,
    LoggingOnlyError
)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

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
        )
    except telegram.error.TelegramError as error:
        raise TelegramSendMessageError(
            'Попытка отправить сообщение в Telegram '
            f'закончилась ошибкой "{error}"'
        )
    else:
        logging.info(f'Сообщение "{message}" отправлено в телеграм')


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
        )
        if api_data.status_code != HTTPStatus.OK:
            api_data.raise_for_status()
        return api_data.json()
    except requests.exceptions.RequestException as error:
        raise APIError(
            f'Запрос к API ({api_data.url}) '
            f'закончился ошибкой {error}'
        )


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
    if 'current_date' not in response:
        raise BadCurrentDate(
            'В ответе API нет ключа "current_date"')
    if type(response['current_date']) is not int:
        raise BadCurrentDate(
            'В ответе API ключ "current_date" содержит не время ответа')
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
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError(f"Неожиданный статус работы: '{homework_status}'")
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие переменных окружения."""
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


def send_error_message(message, bot):
    """
    Отправляет сообщение об ошибке в Telegram.
    В случае успеха возвращает отправленное сообщение
    """
    try:
        send_message(message, bot)
    except TelegramSendMessageError as error:
        logging.error(error)
    else:
        return message
    return


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
        lost_token_message = ''.join(
            ['Нет переменных окружения: ',
             str([token for token in
                  ['PRACTICUM_TOKEN',
                   'TELEGRAM_TOKEN',
                   'TELEGRAM_CHAT_ID']
                  if not globals()[token]])]
        )
        logging.critical(lost_token_message)
        sys.exit(lost_token_message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    last_error_message = ''
    current_timestamp = int(time())

    while True:
        try:
            api_data = get_api_answer(current_timestamp)
            homework_statuses = check_response(api_data)
            if len(homework_statuses) > 0:
                for homework in homework_statuses:
                    send_message(parse_status(homework), bot)
            else:
                logging.debug('Нет обновлений, я проверил')
        except LoggingOnlyError as error:
            logging.error(error)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if message != last_error_message:
                last_error_message = (
                    send_error_message(message, bot)
                    or last_error_message
                )
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
                '- строка %(lineno)d '
                '- %(funcName)s '
                '- %(message)s'
                )
    )
    main()
