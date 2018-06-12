import asyncio
import logging

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.utils.markdown import text, bold
from vk_manager import VKM

API_TOKEN = '598011665:AAFsPZbq3AYReHOmRU9-XrUaGv6lbR_KbcI'

loop = asyncio.get_event_loop()

bot = Bot(token=API_TOKEN, loop=loop)

# For example use simple MemoryStorage for Dispatcher.
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
vk = VKM()

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
        text('Для посылания мемов в вк нужно получить токен.'),
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


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == '__main__':
    executor.start_polling(
        dp, loop=loop, skip_updates=True, on_shutdown=shutdown)
