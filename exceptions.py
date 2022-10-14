class LoggingOnlyError(Exception):
    pass


class TelegramSendMessageError(LoggingOnlyError):
    pass


class APIError(Exception):
    pass


class BadCurrentDate(LoggingOnlyError):
    pass
