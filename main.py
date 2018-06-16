import asyncio
import logging
import traceback
import re
import urlmarker
import config

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.utils.markdown import text, bold
from vk_manager import VKM

loop = asyncio.get_event_loop()

bot = Bot(token=config.API_TOKEN, loop=loop)

# For example use simple MemoryStorage for Dispatcher.
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
vk = VKM()
url_regexp = re.compile(urlmarker.WEB_URL_REGEX)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

# States
TOKEN = 'need_token'
GROUP_ID = 'need_group_id'
OPERATIONAL_MODE = 'operational_mode'


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(TOKEN)

    token_link = 'https://oauth.vk.com/authorize?client_id=6601615&' +\
                 'scope=groups,wall,offline,photos&' +\
                 'redirect_uri=https://oauth.vk.com/blank.html&' +\
                 'display=page&v=5.78&response_type=token'

    await bot.send_message(message.chat.id, text(
        text('Для вк нужно получить токен (если его еще у тебя нет).'),
        text('Перейди по ссылке ' + token_link),
        text('и скопируй из адресной строки весь текст, находящийся между'),
        text('\"access_token=\" и \"&\".'),
        text('В результате получится длинная строка из букв и цифр.'),
        sep='\n'))

    await bot.send_message(message.chat.id, "Введи токен:")


@dp.message_handler(state=TOKEN)
async def process_token(message: types.Message):
    """
    Process user token
    """
    # Save name to storage and go to next step
    # You can use context manager
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        vk_token = message.text

        await state.update_data(vk_token=vk_token)

        test_result, test_message = await vk.test_token(vk_token)

        await bot.send_message(message.chat.id, test_message)

        if test_result:
            await state.set_state(GROUP_ID)
            await bot.send_message(message.chat.id, 'Введи ID группы:')
        else:
            # Авторизация чето не удалась, заканчиваем разговор и удаляем все
            # из хранилища
            await state.finish()


@dp.message_handler(state=GROUP_ID)
async def process_group_id(message: types.Message):
    # Update state and data
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        group_id = message.text

        await state.update_data(group_id=group_id)
        data = await state.get_data()

        vk_token = data['vk_token']

        test_result, test_message = await vk.test_group_id(group_id, vk_token)

        await bot.send_message(message.chat.id, test_message)

        if test_result:
            await state.set_state(OPERATIONAL_MODE)
            await bot.send_message(message.chat.id,
                                   'Можно попробовать слать мемы.')
        else:
            # Авторизация чето не удалась, заканчиваем разговор и удаляем все
            # из хранилища
            await state.finish()


@dp.message_handler(state=OPERATIONAL_MODE,
                    content_types=types.ContentType.PHOTO)
async def process_photos(message: types.Message):
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        data = await state.get_data()
        group_id = data['group_id']
        vk_token = data['vk_token']

    try:
        url, caption = await parse_photo(message)

        if url:
            response = await vk.handle_url(vk_token, group_id, url, caption)

            if 'post_id' in response:
                await bot.send_message(message.chat.id,
                                       'Запостил тебе за щеку, проверяй.')
            else:
                await bot.send_message(message.chat.id, response)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=OPERATIONAL_MODE,
                    content_types=types.ContentType.TEXT)
async def process_text(message: types.Message):
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        data = await state.get_data()
        group_id = data['group_id']
        vk_token = data['vk_token']

    try:
        url, caption = await parse_text(message)

        if url:
            response = await vk.handle_url(vk_token, group_id, url, caption)

            if 'post_id' in response:
                await bot.send_message(message.chat.id,
                                       'Запостил тебе за щеку, проверяй.')
            else:
                await bot.send_message(message.chat.id, response)

    except Exception:
        traceback.print_exc()


async def parse_photo(message):
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

    return False, False


async def parse_text(message):
    if message.text:
        # Если в сообщении были ссылки
        matches = url_regexp.split(message.text)[1:]

        if matches:
            urls_with_captions = list(zip(*[matches[i::2] for i in range(2)]))
            # TODO: handle multiple links in one message
            return urls_with_captions[0]

    return False, False


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == '__main__':
    executor.start_polling(
        dp, loop=loop, skip_updates=True, on_shutdown=shutdown)
