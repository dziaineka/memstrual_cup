import logging
from asyncio import sleep
from os.path import getsize


import config
from files_opener import FilesOpener

logger = logging.getLogger('memstrual_log')


class LogManager:
    def __init__(self, bot):
        self.__checking_running = False
        self.__bot = bot

    @staticmethod
    def wipe_log():
        open(config.LOG_PATH, 'w').close()

    @staticmethod
    def log_is_big():
        file_size = getsize(config.LOG_PATH)
        return file_size > 1000000

    async def send_log(self, chat_id=config.ADMIN_ID):
        with FilesOpener(config.LOG_PATH) as files:
            log = {}
            log = files[0][1][1]  # пизда

            await self.__bot.send_document(chat_id=chat_id, document=log)

    async def check_log_size(self):
        if not self.log_is_big():
            return

        await self.send_log()
        self.wipe_log()
        logger.info('Удалил лог потому что он большой.')

    async def start_checking(self):
        logger.info('Пнули проверку жирного лога.')

        await self.check_log_size()

        if self.__checking_running:
            return
        else:
            self.__checking_running = True

        while True:
            await self.check_log_size()
            await sleep(3600)

    async def panic_sending(self):
        await self.__bot.send_message(config.ADMIN_ID, 'Что-то навернулось!')
        await self.send_log()
