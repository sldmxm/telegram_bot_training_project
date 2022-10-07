import logging
import os
import sys
from time import time, sleep

import requests

from dotenv import load_dotenv
import telegram

from exceptions import EnvironmentNotExist


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

TIMEOUT = 3
RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

last_error_message = ''


def log_and_report(level, message):
    """
    Пишет лог.
    События ERROR и CRITICAL отправляет в TELEGRAM_CHAT_ID,
    если предыдущая отправленная ошибка была другой.
    """
    global last_error_message
    logging_levels = {'CRITICAL': 50,
                      'ERROR': 40,
                      'WARNING': 30,
                      'INFO': 20,
                      'DEBUG': 10,
                      }
    logging.log(logging_levels[level], message)
    if logging_levels[level] >= 40 and message != last_error_message:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        send_message(f'{level} - {message}', bot)
        last_error_message = message
    return


def send_message(message, bot):
    """
    Отправляет сообщение TELEGRAM_CHAT_ID.
    Если не удается за TIMEOUT, пишет ошибку в лог.
    """
    start_time = time()
    while time() - start_time < TIMEOUT:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            logging.info(f'Сообщение "{message}" отправлено в телеграм')
            break
        except Exception as error:
            log_and_report('ERROR', error)
            break
    else:
        logging.error(f'Не удалось отправить '
                      f'сообщение в Telegram за {TIMEOUT} сек.')
    return


def get_api_answer(current_timestamp):
    """
    Делает запрос к эндпоинту API-сервиса.
    В качестве параметра функция получает временную метку
    или использует текущее время, если параметр не передан.
    В случае успешного запроса возвращает ответ API,
    преобразовав его из формата JSON к типам данных Python.
    """
    api_data = requests.get(ENDPOINT,
                            headers=HEADERS,
                            params={'from_date': (current_timestamp
                                    or int(time()))
                                    },
                            timeout=TIMEOUT
                            )
    if api_data.status_code == 200:
        return api_data.json()
    else:
        raise requests.HTTPError(f'API вернул ошибку {api_data.status_code}')


def check_response(response):
    """
    Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям,
    возвращает список домашних работ,
    доступный в ответе API по ключу 'homeworks'.
    """
    if type(response) is not dict:
        raise TypeError('API вернул не словарь')
    if ('homeworks' not in response
            or type(response['homeworks']) is not list):
        raise TypeError(
            'В ответе API нет ключа "homeworks", содержащего список')
    if ('current_date' not in response
            or type(response['current_date']) is not int):
        raise TypeError(
            'В ответе API нет ключа "current_date", содержащего время ответа')
    return response['homeworks']


def parse_status(homework):
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра получает один элемент из списка домашних работ.
    Возвращает подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES.
    """
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
        verdict = HOMEWORK_STATUSES.get(homework_status)
        if not verdict:
            log_and_report('ERROR',
                           f'Статуса "{homework_status}" раньше не было')
        else:
            return (f'Изменился статус проверки работы '
                    f'"{homework_name}". {verdict}')
    except KeyError:
        log_and_report('ERROR', 'Имена ключей домашней работы изменились')
    return


def check_tokens():
    """Проверяет наличие переменных окружения."""
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
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stdout,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    if not check_tokens():
        log_and_report('CRITICAL', 'Нет переменных окружения!')
        raise EnvironmentNotExist('Нет переменных окружения!')

    current_timestamp = int(time())

    while True:
        try:
            api_data = get_api_answer(current_timestamp)
            homework_statuses = check_response(api_data)
        except Exception as error:
            log_and_report(
                'ERROR',
                f'Сбой в работе программы: {error}')
        else:
            if len(homework_statuses) > 0:
                for homework in homework_statuses:
                    if parse_status(homework):
                        send_message(parse_status(homework), bot)
            else:
                log_and_report('DEBUG', 'Нет обновлений, я проверил')

            current_timestamp = api_data['current_date']
        sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
