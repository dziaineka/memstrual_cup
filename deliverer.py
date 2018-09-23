import asyncio
import re
import logging
import traceback
import config
import regexps

from scheduler import Scheduler
from files_opener import FilesOpener

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


class Deliverer:
    __instance = None

    def __init__(self, bot, dp, vk):
        self._bot = bot
        self._dp = dp
        self._vk = vk

        self._post_queue = self._dp.current_state(chat=config.QUEUE_ID,
                                                  user=config.QUEUE_ID)

        self.__checking_running = False

        self.STATUS_OK = 0
        self.STATUS_TOO_EARLY = 1
        self.STATUS_EMPTY = 2

        self.url_regexp = re.compile(regexps.WEB_URL_REGEX)
        self.vk_wall_url = re.compile(regexps.VK_WALL_URL)
        self.vk_photo_url = re.compile(regexps.VK_PHOTO_URL)

    @staticmethod
    def get_instance(bot, dp, vk):
        logging.info('Получаем доставщика постов.')

        if Deliverer.__instance is None:
            Deliverer.__instance = Deliverer(bot, dp, vk)

        return Deliverer.__instance

    @staticmethod
    def sort_by_nearest_time(post):
        dtime = Scheduler.str_to_datetime(post['post_time'])

        return (dtime - Scheduler.get_current_datetime()).total_seconds()

    async def append(self,
                     post_time,
                     chat_id,
                     message_id,
                     user_id,
                     silent=False):
        logging.info('Добавляем пост в очередь.')

        post_time = Scheduler.datetime_to_str(post_time)

        post = {'post_time': post_time,
                'chat_id': chat_id,
                'message_id': message_id,
                'user_id': user_id}

        queue = await self._post_queue.get_data()

        try:
            queue = queue['post_queue']
        except KeyError:
            queue = []

        queue.append(post)
        queue.sort(key=self.sort_by_nearest_time)
        queue.reverse()

        await self._post_queue.set_data({'post_queue': queue})

        if not silent:
            await self.start_checking()

    async def pop(self):
        logging.info('Достаем пост из очереди.')

        queue = await self._post_queue.get_data()

        try:
            queue = queue['post_queue']
        except KeyError:
            queue = []

        post = queue.pop()

        await self._post_queue.set_data({'post_queue': queue})

        return post

    @staticmethod
    def its_time_to_post(cur_time, post_time):
        return cur_time >= post_time

    async def check_queue(self):
        logging.info('Проверяем очередь, мб уже есть что постить.')

        try:
            nearest_post = await self.pop()
            post_dtime = Scheduler.str_to_datetime(nearest_post['post_time'])
        except IndexError:
            return self.STATUS_EMPTY

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
        logging.info('Пнули проверку очереди.')

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
                await asyncio.sleep(20)
            elif status == self.STATUS_EMPTY:
                self.__checking_running = False
                return

    async def share_message(self, message):
        logging.info('Постим пост.')

        with self._dp.current_state(chat=message.chat.id,
                                    user=message.from_user.id) as state:
            data = await state.get_data()

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

                await message.reply(response)

            if channel_tg:
                await self.post_from_url_to_channel(channel_tg,
                                                    url,
                                                    caption)

        except Exception:
            traceback.print_exc()

    async def parse_message(self, message):
        logging.info('Парсим сообщение.')

        url_base = 'https://api.telegram.org/file/bot' + config.API_TOKEN + '/'

        if message.photo:
            # Получаем фотку наилучшего качества(последнюю в массиве)
            photo = message.photo[-1]

            # Описание к фотке
            caption = message['caption']

            if not caption:
                caption = ''

            # url фото на сервере Telegram
            file = await message.bot.get_file(photo['file_id'])
            image_url = url_base + file.file_path

            return image_url, caption

        elif message.text:
            # Если в сообщении были ссылки
            matches = self.url_regexp.split(message.text)[1:]

            if matches:
                urls_with_captions = list(
                    zip(*[matches[i::2] for i in range(2)]))[0]

                # тут посмотреть не скормили ли нам ссылку на псто вк,
                # оттуда надо утянуть картинку
                with self._dp.current_state(
                        chat=message.chat.id,
                        user=message.from_user.id) as state:
                    data = await state.get_data()

                    vk_token = None

                    warning = 'Нужно подключиться к вк, ' +\
                        'чтобы забирать оттуда картинки.'

                    if 'vk_token' in data:
                        vk_token = data['vk_token'].strip()

                    if self.vk_wall_url.match(urls_with_captions[0]):
                        if not vk_token:
                            await self._bot.send_message(message.chat.id,
                                                         warning)

                            return urls_with_captions[0], message.text

                        pic_url = await self._vk.check_wall_post(
                            vk_token,
                            urls_with_captions[0])

                    elif self.vk_photo_url.match(urls_with_captions[0]):
                        if not vk_token:
                            await self._bot.send_message(message.chat.id,
                                                         warning)

                            return urls_with_captions[0], message.text

                        pic_url = await self._vk.check_photo_post(
                            vk_token,
                            urls_with_captions[0])

                    else:
                        return urls_with_captions[0], message.text

                    urls_with_captions = (
                        pic_url, urls_with_captions[1])

                return urls_with_captions

        return '', message.text

    async def post_from_url_to_vk(self, vk_token, group_id, url, caption=''):
        logging.info('Постим в вк.')

        response = await self._vk.handle_url(vk_token, group_id, url, caption)

        if 'post_id' in response:
            response = 'Запостил в ВК.'

        return response

    async def post_from_url_to_channel(self, channel_tg, url, caption=''):
        logging.info('Постим в канал.')

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
