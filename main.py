import asyncio
import aiohttp
import logging
import traceback
import re
import regexps
import config
import states

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor, exceptions
from aiogram.utils.markdown import text
from vk_manager import VKM
from scheduler import Scheduler
from deliverer import Deliverer

# TODO
# Показать очередь отправки
# Хранилище в БД

loop = asyncio.get_event_loop()

bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage(host=config.REDIS_HOST,
                       port=config.REDIS_PORT,
                       password=config.REDIS_PASSWORD)

dp = Dispatcher(bot, storage=storage)
vk = VKM()
scheduler = Scheduler()
deliverer = Deliverer.get_instance(bot, dp, vk)

url_regexp = re.compile(regexps.WEB_URL_REGEX)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    logging.info('Старт работы бота.')

    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(states.INITIAL)

    line1 = 'Привет, этот бот автоматически постит посылаемый ему контент ' +\
            'в заданные тобой группу ВК и канал в телеграме.'

    line2 = 'Для начала нужно настроить подключение.'
    line3 = 'Жми /vk или /channel и следуй инструкциям.'

    instructions = text(text(line1), text(line2), '', text(line3), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler(commands=['reset'], state='*')
async def cmd_reset(message: types.Message):
    # Get current state

    logging.info('Сброс.')

    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    await state.finish()
    await state.set_state(states.INITIAL)

    await bot.send_message(message.chat.id,
                           'Стер себе память, настраивай заново теперь.')


@dp.message_handler(commands=['channel'],
                    state='*')
async def cmd_channel(message: types.Message):
    logging.info('Настраиваем канал.')

    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(states.CHANNEL_NAME)

    line1 = 'Сперва сделай бота админом канала.'
    line2 = 'Потом пришли мне имя канала в формате @название_канала.'

    instructions = text(text(line1), text(line2), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler(commands=['vk'],
                    state='*')
async def cmd_vk(message: types.Message):
    logging.info('Настраиваем ВК.')

    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(states.VK_TOKEN)

    token_link = 'https://oauth.vk.com/authorize?client_id=6601615&' +\
                 'scope=groups,wall,offline,photos&' +\
                 'redirect_uri=https://oauth.vk.com/blank.html&' +\
                 'display=page&v=5.78&response_type=token'

    line2 = 'Перейди по ссылке и скопируй из адресной строки весь ' +\
            'текст, находящийся между \"access_token=\" и \"&\".'

    instructions = text(
        text('Для вк нужно получить токен (если его еще у тебя нет).'),
        text(line2),
        text('В результате получится длинная строка из букв и цифр.'),
        sep='\n')

    # настроим клавиатуру
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    url_button = types.InlineKeyboardButton(text="Получить токен",
                                            url=token_link)

    keyboard.add(url_button)

    await bot.send_message(message.chat.id,
                           instructions,
                           reply_markup=keyboard)

    await bot.send_message(message.chat.id, "Введи токен:")


@dp.message_handler(state=states.CHANNEL_NAME)
async def process_channel(message: types.Message):
    """
    Process user channel name
    """
    logging.info('Обрабатываем ввод имени канала.')

    # Save name to storage and go to next step
    # You can use context manager
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        channel_tg = message.text.strip()

        if channel_tg[0] != '@':
            await bot.send_message(message.chat.id, 'Нет @ в начале имени.')
            return

        data = await state.get_data()
        data['channel_tg'] = channel_tg
        await state.update_data(data=data, channel_tg=channel_tg)

        await bot.send_message(message.chat.id,
                               'Можно попробовать слать мемы.')

        await state.set_state(states.OPERATIONAL_MODE)


@dp.message_handler(state=states.VK_TOKEN)
async def process_token(message: types.Message):
    """
    Process user token
    """
    logging.info('Обрабатываем ввод токена ВК.')

    # Save name to storage and go to next step
    # You can use context manager
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        vk_token = message.text

        data = await state.get_data()
        data['vk_token'] = vk_token
        await state.update_data(data=data, vk_token=vk_token)

        test_result, test_message = await vk.test_token(vk_token)

        await bot.send_message(message.chat.id, test_message)

        if test_result:
            await state.set_state(states.GROUP_ID)
            await bot.send_message(message.chat.id, 'Введи ID группы:')
        else:
            # Авторизация чето не удалась
            await bot.send_message(
                message.chat.id,
                'Авторизация чето не удалась, я хз, повтори')


@dp.message_handler(state=states.GROUP_ID)
async def process_group_id(message: types.Message):
    logging.info('Обрабатываем ввод ИД группы ВК.')

    # Update state and data
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        group_id = message.text

        data = await state.get_data()
        data['group_id'] = group_id
        await state.update_data(data=data, group_id=group_id)

        data = await state.get_data()

        vk_token = data['vk_token']

        test_result, test_message = await vk.test_group_id(group_id, vk_token)

        await bot.send_message(message.chat.id, test_message)

        if test_result:
            await state.set_state(states.OPERATIONAL_MODE)
            await bot.send_message(message.chat.id,
                                   'Можно попробовать слать мемы.')
        else:
            # Авторизация чето не удалась
            await bot.send_message(
                message.chat.id,
                'Авторизация чето не удалась, я хз, повтори')


@dp.callback_query_handler(state=states.DATETIME_INPUT)
async def callback_inline(call):
    logging.info('Обрабатываем нажатие кнопки дня публикации.')

    with dp.current_state(chat=call.message.chat.id,
                          user=call.from_user.id) as state:
        if call.data == "сегодня":
            post_date = scheduler.get_today_date()
        elif call.data == "завтра":
            post_date = scheduler.get_today_date(1)
        elif call.data == "послезавтра":
            post_date = scheduler.get_today_date(2)

        data = await state.get_data()
        post_date = scheduler.date_to_str(post_date)
        data['post_date'] = post_date
        await state.update_data(data=data, post_date=post_date)

        keyboard = scheduler.get_day_selection(call.data)

        try:
            await bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard)

        except exceptions.MessageNotModified:
            keyboard = scheduler.get_day_selection()

            post_date = scheduler.get_today_date()

            data = await state.get_data()
            post_date = scheduler.date_to_str(post_date)
            data['post_date'] = post_date
            await state.update_data(data=data, post_date=post_date)

            await bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard)


@dp.message_handler(state=states.DATETIME_INPUT,
                    content_types=types.ContentType.TEXT)
async def process_postdate(message: types.Message):
    logging.info('Обрабатываем ввод времени публикации (или сброс ввода).')

    # Если в сообщении есть ссылка, то это очевидно новый псто, забей на старый
    if url_regexp.split(message.text)[1:]:
        # очистим на всякий пожарный поле для отлаживаемого поста
        with dp.current_state(chat=message.chat.id,
                              user=message.from_user.id) as state:

            data = await state.get_data()
            data['message_to_schedule_id'] = None
            await state.update_data(data=data, message_to_schedule_id=None)

        # и вызовем обработчик ссылок
        await process_text(message)
    else:
        # если ссылки нет, то будем парсить время на куда отложить
        state = dp.current_state(chat=message.chat.id,
                                 user=message.from_user.id)

        data = await state.get_data()
        post_date = scheduler.str_to_date(data['post_date'])
        seconds = scheduler.parse_time_input(post_date, message.text)

        if seconds < 0:
            await bot.send_message(message.chat.id,
                                   'Это время уже прошло, введи другое.')
            return
        elif seconds > 0:
            post_time = scheduler.get_str_datetime_in_future(seconds)

            post_date_message = 'Будет отправлено ' + post_time + '.'

            await bot.send_message(message.chat.id,
                                   post_date_message)

        await deliverer.append(
            post_time=scheduler.get_datetime_in_future(seconds),
            chat_id=message.chat.id,
            message_id=data['message_to_schedule_id'],
            user_id=message.from_user.id)

        data = await state.get_data()
        data['message_to_schedule_id'] = None
        await state.update_data(data=data, message_to_schedule_id=None)

        # вернем рабочий режим
        await state.set_state(states.OPERATIONAL_MODE)


@dp.message_handler(state=states.DATETIME_INPUT,
                    content_types=types.ContentType.PHOTO)
async def break_input_by_photo(message: types.Message):
    logging.info('Обрабатываем сброс ввода времени через новую картинку.')

    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(states.OPERATIONAL_MODE)
    await process_photos(message)


@dp.message_handler(state=states.OPERATIONAL_MODE,
                    content_types=types.ContentType.PHOTO)
async def process_photos(message: types.Message):
    logging.info('Обрабатываем посылку картинки.')

    try:
        await scheduler.schedule_post(dp, message)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=states.OPERATIONAL_MODE,
                    content_types=types.ContentType.TEXT)
async def process_text(message: types.Message):
    logging.info('Обрабатываем посылку текста.')

    try:
        await scheduler.schedule_post(dp, message)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=states.INITIAL)
async def no_way(message: types.Message):
    logging.info('Обработка ввода при ненастроенных получателях.')

    line1 = 'Пока не настроишь места для пересылки, тут будет скучновато.'
    line2 = 'Жми /vk или /channel и следуй инструкциям.'

    instructions = text(text(line1), text(line2), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler(state=None)
async def to_start(message: types.Message):
    logging.info('При вводе любого сообщения стартуем.')
    await cmd_start(message)


async def checking_after_pause():
    await asyncio.sleep(5)
    await deliverer.start_checking()


async def startup(dispatcher: Dispatcher):
    logging.info('Старт бота.')
    vk.http_session = aiohttp.ClientSession()

    # запускаем проверку очереди сразу, все необходимое у нас есть
    asyncio.run_coroutine_threadsafe(checking_after_pause(), loop)


async def shutdown(dispatcher: Dispatcher):
    logging.info('Убиваем бота.')

    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()
    await vk.http_session.close()


if __name__ == '__main__':
    executor.start_polling(dp,
                           loop=loop,
                           skip_updates=True,
                           on_startup=startup,
                           on_shutdown=shutdown)
