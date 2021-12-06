from datetime import datetime
import logging
import re
import traceback
from asyncio import sleep
from typing import Optional

import config
import regexps
from files_opener import FilesOpener
from scheduler import Scheduler
from storage import Storage

logger = logging.getLogger('memstrual_log')
QUEUE_NAME = "post_queue"


class Deliverer:
    __instance = None

    def __init__(self, bot, dp, vk):
        self._bot = bot
        self._dp = dp
        self._vk = vk

        self._post_queue = Storage("post_queue")

        self.__checking_running = False

        self.STATUS_OK = 0
        self.STATUS_TOO_EARLY = 1
        self.STATUS_EMPTY = 2

        self.url_regexp = re.compile(regexps.WEB_URL_REGEX)
        self.vk_wall_url = re.compile(regexps.VK_WALL_URL)
        self.vk_photo_url = re.compile(regexps.VK_PHOTO_URL)

    @staticmethod
    def get_instance(bot, dp, vk):
        logger.info('Получаем доставщика постов.')

        if Deliverer.__instance is None:
            Deliverer.__instance = Deliverer(bot, dp, vk)

        return Deliverer.__instance

    async def append(self,
                     post_time: datetime,
                     chat_id: int,
                     message_id: int,
                     user_id: int,
                     silent=False):
        logger.info('Добавляем пост в очередь.')

        unix_time = post_time.timestamp()
        str_post_time = post_time.isoformat()

        post = {'post_time': str_post_time,
                'chat_id': chat_id,
                'message_id': message_id,
                'user_id': user_id}

        await self._post_queue.add_in_sorted_set(QUEUE_NAME, post, unix_time)

        if not silent:
            await self.start_checking()

    async def pop(self) -> Optional[dict]:
        logger.info('Достаем пост из очереди.')
        return await self._post_queue.pop_min_from_sorted_set(QUEUE_NAME)

    @staticmethod
    def its_time_to_post(cur_time, post_time):
        return cur_time >= post_time

    async def check_queue(self):
        logger.info('Проверяем очередь, мб уже есть что постить.')
        nearest_post = await self.pop()

        if nearest_post is None:
            logger.info('Походу очередь пуста.')
            return self.STATUS_EMPTY

        post_dtime = datetime.fromisoformat(nearest_post['post_time'])

        if self.its_time_to_post(Scheduler.get_current_datetime(),
                                 post_dtime):
            scheduled_message = await self._bot.forward_message(
                chat_id=nearest_post['chat_id'],
                from_chat_id=nearest_post['chat_id'],
                message_id=nearest_post['message_id'],
                disable_notification=True)

            # вернем сообщению ID пользователя, а не бота, а то не
            # загрузится хранилище пользователя
            scheduled_message.from_user.id = nearest_post['user_id']

            await self.share_message(scheduled_message)

            return self.STATUS_OK
        else:
            await self.append(post_dtime,
                              nearest_post['chat_id'],
                              nearest_post['message_id'],
                              nearest_post['user_id'],
                              True)

            return self.STATUS_TOO_EARLY

    async def start_checking(self):
        logger.info('Пнули проверку очереди.')

        await self.check_queue()

        if self.__checking_running:
            return
        else:
            self.__checking_running = True

        while True:
            status = await self.check_queue()

            if status == self.STATUS_OK:
                continue
            elif status == self.STATUS_TOO_EARLY:
                await sleep(20)
            elif status == self.STATUS_EMPTY:
                self.__checking_running = False
                return

    async def share_message(self, message):
        logger.info('Постим пост.')

        state = self._dp.current_state(chat=message.chat.id,
                                       user=message.from_user.id)

        async with state.proxy() as data:
            vk_token = None
            group_id = None
            channel_tg = None

            if ('vk_token' in data) and ('group_id' in data):
                vk_token = data['vk_token'].strip()
                group_id = data['group_id'].strip()

            if 'channel_tg' in data:
                channel_tg = data['channel_tg'].strip()

        try:
            url, caption = await self.parse_message(message)

            if vk_token and group_id:
                response = await self.post_from_url_to_vk(vk_token,
                                                          group_id,
                                                          url,
                                                          caption)

                await self._bot.send_message(message.chat.id, response)

            if channel_tg:
                await self.post_from_url_to_channel(channel_tg,
                                                    url,
                                                    caption)

                await self._bot.send_message(message.chat.id,
                                             'Запостил в ТГ.')

        except Exception:
            traceback.print_exc()

    async def parse_message(self, message):
        logger.info('Парсим сообщение.')

        if message.photo:
            # Получаем фотку наилучшего качества(последнюю в массиве)
            photo = message.photo[-1]

            # Описание к фотке
            caption = message['caption']

            if not caption:
                caption = ''

            # url фото на сервере Telegram
            file = await self._bot.get_file(photo['file_id'])
            image_url = config.URL_BASE + file.file_path

            return image_url, caption

        elif message.text:
            # Если в сообщении были ссылки
            matches = self.url_regexp.split(message.text)[1:]

            if matches:
                matched_url: str = matches[0].strip()
                matched_caption: str = matches[1].strip()
                url_with_caption = (matched_url, matched_caption)

                # тут посмотреть не скормили ли нам ссылку на псто вк,
                # оттуда надо утянуть картинку
                state = self._dp.current_state(chat=message.chat.id,
                                               user=message.from_user.id)

                async with state.proxy() as data:
                    vk_token = None

                    warning = 'Нужно подключиться к вк, ' +\
                        'чтобы забирать оттуда картинки.'

                    if 'vk_token' in data:
                        vk_token = data['vk_token'].strip()

                if self.vk_wall_url.match(url_with_caption[0]):
                    if not vk_token:
                        await self._bot.send_message(message.chat.id, warning)
                        return url_with_caption[0], message.text

                    pic_url = await self._vk.check_wall_post(
                        vk_token,
                        url_with_caption[0])

                elif self.vk_photo_url.match(url_with_caption[0]):
                    if not vk_token:
                        await self._bot.send_message(message.chat.id, warning)
                        return url_with_caption[0], message.text

                    pic_url = await self._vk.check_photo_post(
                        vk_token,
                        url_with_caption[0])

                else:
                    return url_with_caption[0], message.text

                url_with_caption = (pic_url, url_with_caption[1])
                return url_with_caption

        return '', message.text

    async def post_from_url_to_vk(self, vk_token, group_id, url, caption=''):
        logger.info('Постим в вк.')

        result = await self._vk.handle_url(vk_token, group_id, url, caption)

        if result is True:
            result = 'Запостил в ВК.'

        return result

    async def post_from_url_to_channel(self, channel_tg, url, caption=''):
        logger.info('Постим в канал.')

        # попросим вк подготовить файлы
        filepath, extension = self._vk.get_filepath(url)

        if extension in self._vk.allowed_image_extensions:
            # подготавливаем и заливаем фото
            with FilesOpener(filepath, key_format='photo') as photos_files:
                photo = {}
                photo = photos_files[0][1][1]  # пизда

                # таким образом мы удалям ссылку из текста, если постим
                # ее как аттачмент
                caption = caption.replace(url, '')

                await self._bot.send_photo(chat_id=channel_tg,
                                           photo=photo,
                                           caption=caption)
        else:
            await self._bot.send_message(channel_tg, caption)
