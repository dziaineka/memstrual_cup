import asyncio

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.utils.markdown import text, bold

API_TOKEN = 'PUT_TOKEN_HERE'

loop = asyncio.get_event_loop()

bot = Bot(token=API_TOKEN, loop=loop)

# For example use simple MemoryStorage for Dispatcher.
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# States
LOGIN = 'need_login'
PASSWORD = 'need_password'
GROUP_ID = 'need_group_id'
TWO_FA = 'need_2FA'
OPERATIONAL_MODE = 'operational_mode'
AUTHORISATION = 'authorisation'


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(LOGIN)

    await message.reply("Вводи логин:")


@dp.message_handler(state=LOGIN)
async def process_login(message: types.Message):
    """
    Process user login
    """
    # Save name to storage and go to next step
    # You can use context manager
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        await state.update_data(login=message.text)
        await state.set_state(PASSWORD)

    await message.reply("Введи пароль:")


@dp.message_handler(state=PASSWORD)
async def process_password(message: types.Message):
    # Update state and data
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        await state.update_data(password=message.text)
        await state.set_state(GROUP_ID)

    await message.reply("Введи ID группы:")


@dp.message_handler(state=GROUP_ID)
async def process_group_id(message: types.Message):
    # Update state and data
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        await state.update_data(group_id=message.text)
        await state.set_state(AUTHORISATION)

        data = await state.get_data()

        # And send message
        await bot.send_message(message.chat.id, text(
            text('login: ', data['login']),
            text('password: ', data['password']),
            text('group_id: ', data['group_id']),
            sep='\n'), parse_mode=ParseMode.MARKDOWN)

    # Finish conversation
    # WARNING! This method will destroy all data in storage for current user!
    await state.finish()


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == '__main__':
    executor.start_polling(
        dp, loop=loop, skip_updates=True, on_shutdown=shutdown)
