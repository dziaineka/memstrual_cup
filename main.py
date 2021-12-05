import asyncio
import logging
import re
import traceback

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.utils import exceptions, executor
from aiogram.utils.markdown import text

import config
import regexps
from deliverer import Deliverer
from exceptions import NoTimeInStringException
from logManager import LogManager
from scheduler import Scheduler
from states import Form
from vk_manager import VKM


def setup_logging():
    # create logger
    logger = logging.getLogger('memstrual_log')
    logger.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    fh = logging.FileHandler(config.LOG_PATH)
    fh.setLevel(logging.DEBUG)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


loop = asyncio.get_event_loop()

bot = Bot(token=config.API_TOKEN, loop=loop)

storage = RedisStorage2(host=config.REDIS_HOST,
                        port=config.REDIS_PORT,
                        password=config.REDIS_PASSWORD)

dp = Dispatcher(bot, storage=storage)
vk = VKM()
scheduler = Scheduler()
log_manager = LogManager(bot)
deliverer = Deliverer.get_instance(bot, dp, vk)

url_regexp = re.compile(regexps.WEB_URL_REGEX)

logger = setup_logging()


async def manage_post_sending(state, chat_id, user_id, seconds):
    if seconds < 0:
        await bot.send_message(chat_id,
                               'Это время уже прошло, введи другое.')
        return
    elif seconds > 0:
        post_time = scheduler.get_str_datetime_in_future(seconds)

        post_date_message = 'Будет отправлено ' + post_time + '.'

        await bot.send_message(chat_id,
                               post_date_message)

    async with state.proxy() as data:
        await deliverer.append(
            post_time=scheduler.get_datetime_in_future(seconds),
            chat_id=chat_id,
            message_id=data['message_to_schedule_id'],
            user_id=user_id)

        data['message_to_schedule_id'] = None

    # вернем рабочий режим
    await Form.operational_mode.set()


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    logger.info('Старт работы бота.')

    # Set state
    await Form.initial.set()

    line1 = 'Привет, этот бот автоматически постит посылаемый ему контент ' +\
            'в заданные тобой группу ВК и канал в телеграме.'

    line2 = 'Для начала нужно настроить подключение.'
    line3 = 'Жми /vk или /channel и следуй инструкциям.'

    instructions = text(text(line1), text(line2), '', text(line3), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler(commands=['getlog'], state='*')
async def cmd_getlog(message: types.Message):
    logger.info('Отдаю лог.')
    await log_manager.send_log(chat_id=message.chat.id)


@dp.message_handler(commands=['dellog'], state='*')
async def cmd_dellog(message: types.Message):
    log_manager.wipe_log()

    logger.info('Удалил лог.')
    await bot.send_message(message.chat.id, 'Удалил лог.')


@dp.message_handler(commands=['reset'], state='*')
@dp.message_handler(lambda message: message.text.lower() == 'reset', state='*')
async def cmd_reset(message: types.Message, state: FSMContext):
    # Get current state

    logger.info('Сброс.')

    await state.finish()
    await Form.initial.set()

    await bot.send_message(message.chat.id,
                           'Стер себе память, настраивай заново теперь.')


@dp.message_handler(commands=['channel'], state='*')
@dp.message_handler(lambda message: message.text.lower() == 'channel',
                    state='*')
async def cmd_channel(message: types.Message):
    logger.info('Настраиваем канал.')

    await Form.channel_name.set()

    line1 = 'Сперва сделай бота админом канала.'
    line2 = 'Потом пришли мне имя канала в формате @название_канала.'

    instructions = text(text(line1), text(line2), sep='\n')

    await bot.send_message(message.chat.id, instructions)


@dp.message_handler(commands=['vk'], state='*')
@dp.message_handler(lambda message: message.text.lower() == 'vk', state='*')
async def cmd_vk(message: types.Message):
    logger.info('Настраиваем ВК.')

    await Form.vk_token.set()

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
                                            url=config.VK_TOKEN_LINK)

    keyboard.add(url_button)

    await bot.send_message(message.chat.id,
                           instructions,
                           reply_markup=keyboard)

    await bot.send_message(message.chat.id, "Введи токен:")


@dp.message_handler(state=Form.channel_name)
async def process_channel(message: types.Message, state: FSMContext):
    """
    Process user channel name
    """
    logger.info('Обрабатываем ввод имени канала.')

    # Save name to storage and go to next step
    channel_tg = message.text.strip()

    if channel_tg[0] != '@':
        await bot.send_message(message.chat.id, 'Нет @ в начале имени.')
        return

    async with state.proxy() as data:
        data['channel_tg'] = channel_tg

    await bot.send_message(message.chat.id, 'Можно попробовать слать мемы.')
    await Form.operational_mode.set()


@dp.message_handler(state=Form.vk_token)
async def process_token(message: types.Message, state: FSMContext):
    """
    Process user token
    """
    logger.info('Обрабатываем ввод токена ВК.')

    vk_token = message.text

    async with state.proxy() as data:
        data['vk_token'] = vk_token

    test_result, test_message = await vk.test_token(vk_token)

    await bot.send_message(message.chat.id, test_message)

    if test_result:
        await Form.group_id.set()
        await bot.send_message(message.chat.id, 'Введи ID группы:')
    else:
        # Авторизация чето не удалась
        await bot.send_message(
            message.chat.id,
            'Авторизация чето не удалась, я хз, повтори')


@dp.message_handler(state=Form.group_id)
async def process_group_id(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод ИД группы ВК.')

    group_id = message.text

    async with state.proxy() as data:
        data['group_id'] = group_id
        vk_token = data['vk_token']

    test_result, test_message = await vk.test_group_id(group_id, vk_token)

    await bot.send_message(message.chat.id, test_message)

    if test_result:
        await Form.operational_mode.set()
        await bot.send_message(message.chat.id,
                               'Можно попробовать слать мемы.')
    else:
        # Авторизация чето не удалась
        await bot.send_message(message.chat.id,
                               'Авторизация чето не удалась, я хз, повтори')


@dp.callback_query_handler(state=Form.datetime_input)
async def callback_inline(call, state: FSMContext):
    logger.info('Обрабатываем нажатие кнопки дня публикации.')

    if call.data == "сегодня":
        post_date = scheduler.get_today_date()
    elif call.data == "завтра":
        post_date = scheduler.get_today_date(1)
    elif call.data == "послезавтра":
        post_date = scheduler.get_today_date(2)
    elif call.data == "сейчас":
        await manage_post_sending(state,
                                  call.message.chat.id,
                                  call.message.chat.id,
                                  seconds=0)
        return
    else:
        post_date = scheduler.get_today_date()

    post_date = scheduler.date_to_str(post_date)

    async with state.proxy() as data:
        data['post_date'] = post_date

    keyboard = scheduler.get_day_selection(call.data)

    try:
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard)

    except exceptions.MessageNotModified:
        keyboard = scheduler.get_day_selection()

        post_date = scheduler.get_today_date()
        post_date = scheduler.date_to_str(post_date)

        async with state.proxy() as data:
            data['post_date'] = post_date

        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard)


@dp.message_handler(state=Form.datetime_input,
                    content_types=types.ContentType.TEXT)
async def process_postdate(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем ввод времени публикации (или сброс ввода).')

    # Если в сообщении есть ссылка, то это очевидно новый псто, забей на старый
    if url_regexp.split(message.text)[1:]:
        # очистим на всякий пожарный поле для отлаживаемого поста
        async with state.proxy() as data:
            data['message_to_schedule_id'] = None

        # и вызовем обработчик ссылок
        await process_text(message, state)
        return
    else:
        # если ссылки нет, то будем парсить время на куда отложить
        async with state.proxy() as data:
            post_date = scheduler.str_to_date(data['post_date'])

        try:
            seconds = scheduler.parse_time_input(post_date, message.text)
        except NoTimeInStringException:
            # в тексте нет ничего похожего на время, поэтому пошлем
            # сообщение в обработчик постов
            await process_text(message, state)
            return

        await manage_post_sending(state,
                                  message.chat.id,
                                  message.from_user.id,
                                  seconds)


@dp.message_handler(state=Form.datetime_input,
                    content_types=types.ContentType.PHOTO)
async def break_input_by_photo(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем сброс ввода времени через новую картинку.')

    # Update user's state
    await Form.operational_mode.set()
    await process_photos(message, state)


@dp.message_handler(state=Form.operational_mode,
                    content_types=types.ContentType.PHOTO)
async def process_photos(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку картинки.')

    try:
        await scheduler.schedule_post(state, message)

    except Exception:
        with open(config.LOG_PATH, "a") as logfile:
            traceback.print_exc(file=logfile)

        traceback.print_exc()
        await log_manager.panic_sending()


@dp.message_handler(state=Form.operational_mode,
                    content_types=types.ContentType.TEXT)
async def process_text(message: types.Message, state: FSMContext):
    logger.info('Обрабатываем посылку текста.')

    try:
        await scheduler.schedule_post(state, message)

    except Exception:
        with open(config.LOG_PATH, "a") as logfile:
            traceback.print_exc(file=logfile)

        traceback.print_exc()
        await log_manager.panic_sending()


@dp.message_handler(state=Form.initial)
async def no_way(message: types.Message):
    logger.info('Обработка ввода при ненастроенных получателях.')

    line1 = 'Пока не настроишь места для пересылки, тут будет скучновато.'
    line2 = 'Жми /vk или /channel и следуй инструкциям.'

    instructions = text(text(line1), text(line2), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


@dp.message_handler(state=None)
async def to_start(message: types.Message):
    logger.info('При вводе любого сообщения стартуем.')
    await cmd_start(message)


async def checking_queue_after_pause():
    await asyncio.sleep(5)
    await deliverer.start_checking()


async def checking_log_after_pause():
    await asyncio.sleep(20)
    await log_manager.start_checking()


async def startup(dispatcher: Dispatcher):
    logger.info('Старт бота.')

    # запускаем проверку очереди сразу, все необходимое у нас есть
    asyncio.run_coroutine_threadsafe(checking_queue_after_pause(), loop)

    # запускаем проверку переполненности лога
    asyncio.run_coroutine_threadsafe(checking_log_after_pause(), loop)


async def shutdown(dispatcher: Dispatcher):
    logger.info('Убиваем бота.')
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == '__main__':
    executor.start_polling(dp,
                           loop=loop,
                           skip_updates=True,
                           on_startup=startup,
                           on_shutdown=shutdown)
