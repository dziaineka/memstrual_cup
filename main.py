import asyncio
import aiohttp
import logging
import traceback
import re
import regexps
import config
import states

from aiogram import Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher
from aiogram.types import ParseMode
from aiogram.utils import executor, exceptions
from aiogram.utils.markdown import text, bold
from vk_manager import VKM
from scheduler import Scheduler
from files_opener import FilesOpener

# 2. Постинг текста
# 3. Если прилетает сообщение с картинкой и текстом, то постить картинку и текст
# 4. Предупреждение, что по ссылке нет фотки
# 5. Подумать над кнопкой "отменить"

loop = asyncio.get_event_loop()

bot = Bot(token=config.API_TOKEN, loop=loop)

# For example use simple MemoryStorage for Dispatcher.
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
vk = VKM()
scheduler = Scheduler()
url_regexp = re.compile(regexps.WEB_URL_REGEX)
vk_wall_url = re.compile(regexps.VK_WALL_URL)
vk_photo_url = re.compile(regexps.VK_PHOTO_URL)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
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
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    await state.finish()
    await state.set_state(states.INITIAL)

    await bot.send_message(message.chat.id,
                           'Стер себе память, настраивай заново теперь.')


@dp.message_handler(commands=['channel'],
                    state='*')
async def cmd_channel(message: types.Message):
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
    # Save name to storage and go to next step
    # You can use context manager
    with dp.current_state(chat=message.chat.id,
                          user=message.from_user.id) as state:
        channel_tg = (message.text).strip()

        if channel_tg[0] != '@':
            await bot.send_message(message.chat.id, 'Нет @ в начале имени.')
            return

        await state.update_data(channel_tg=channel_tg)

        await bot.send_message(message.chat.id,
                               'Можно попробовать слать мемы.')

        await state.set_state(states.OPERATIONAL_MODE)


@dp.message_handler(state=states.VK_TOKEN)
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
            await state.set_state(states.GROUP_ID)
            await bot.send_message(message.chat.id, 'Введи ID группы:')
        else:
            # Авторизация чето не удалась
            await bot.send_message(
                message.chat.id,
                'Авторизация чето не удалась, я хз, повтори')


@dp.message_handler(state=states.GROUP_ID)
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
    with dp.current_state(chat=call.message.chat.id,
                          user=call.from_user.id) as state:
        if call.data == "сегодня":
            post_date = scheduler.get_today_date()
            await state.update_data(post_date=post_date)
        elif call.data == "завтра":
            post_date = scheduler.get_today_date(1)
            await state.update_data(post_date=post_date)
        elif call.data == "послезавтра":
            post_date = scheduler.get_today_date(2)
            await state.update_data(post_date=post_date)

        keyboard = scheduler.get_day_selection(call.data)

        try:
            await bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard)

        except exceptions.MessageNotModified:
            keyboard = scheduler.get_day_selection()

            post_date = scheduler.get_today_date()
            await state.update_data(post_date=post_date)

            await bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard)


@dp.message_handler(state=states.DATETIME_INPUT,
                    content_types=types.ContentType.TEXT)
async def process_postdate(message: types.Message):
    # Если в сообщении есть ссылка, то это очевидно новый псто, забей на старый
    if url_regexp.split(message.text)[1:]:
        # очистим на всякий пожарный поле для отлаживаемого поста
        with dp.current_state(chat=message.chat.id,
                              user=message.from_user.id) as state:
            await state.update_data(message_to_schedule_id=None)

        # и вызовем обработчик ссылок
        await process_text(message)
    else:
        # если ссылки нет, то будем парсить время на куда отложить
        state = dp.current_state(chat=message.chat.id,
                                 user=message.from_user.id)

        data = await state.get_data()
        post_date = data['post_date']

        seconds = scheduler.parse_time_input(post_date, message.text)
        if seconds < 0:
            await bot.send_message(message.chat.id,
                                   'Это время уже прошло, введи другое.')
            return
        elif seconds > 0:
            post_time = scheduler.get_datetime_in_future(seconds)

            post_date_message = 'Будет отправлено ' + post_time + '.'

            await bot.send_message(message.chat.id,
                                   post_date_message)

        message_to_schedule_id = data['message_to_schedule_id']
        await state.update_data(message_to_schedule_id=None)

        # вернем рабочий режим
        await state.set_state(states.OPERATIONAL_MODE)

        # подождем указанное время
        await asyncio.sleep(int(seconds))

        scheduled_message = await bot.forward_message(
            chat_id=message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message_to_schedule_id,
            disable_notification=True)

        # вернем сообщению ID пользователя, а не бота, а то не
        # загрузится хранилище пользователя
        scheduled_message.from_user.id = message.from_user.id

        await share_message(scheduled_message)


async def share_message(message):
    with dp.current_state(chat=message.chat.id,
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
        url, caption = await parse_message(message)

        if vk_token and group_id:
            response = await post_from_url_to_vk(vk_token,
                                                 group_id,
                                                 url,
                                                 caption)

            await message.reply(response)

        if channel_tg:
            response = await post_from_url_to_channel(channel_tg, url, caption)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=states.DATETIME_INPUT,
                    content_types=types.ContentType.PHOTO)
async def break_input_by_photo(message: types.Message):
    # Get current state
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    # Update user's state
    await state.set_state(states.OPERATIONAL_MODE)
    await process_photos(message)


@dp.message_handler(state=states.OPERATIONAL_MODE,
                    content_types=types.ContentType.PHOTO)
async def process_photos(message: types.Message):
    try:
        url, caption = await parse_message(message)
        caption = caption

        if url:
            await scheduler.schedule_post(dp, message)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=states.OPERATIONAL_MODE,
                    content_types=types.ContentType.TEXT)
async def process_text(message: types.Message):
    try:
        url, caption = await parse_message(message)
        caption = caption

        if url:
            await scheduler.schedule_post(dp, message)

    except Exception:
        traceback.print_exc()


@dp.message_handler(state=states.INITIAL)
async def no_way(message: types.Message):
    line1 = 'Пока не настроишь места для пересылки, тут будет скучновато.'
    line2 = 'Жми /vk или /channel и следуй инструкциям.'

    instructions = text(text(line1), text(line2), sep='\n')

    await bot.send_message(message.chat.id,
                           instructions)


async def post_from_url_to_channel(channel_tg, url, caption=''):
    # попросим вк подготовить файлы
    filepath, extension = vk.get_url(url)

    if extension in vk.allowed_image_extensions:
        # подготавливаем и заливаем фото
        with FilesOpener(filepath, key_format='photo') as photos_files:
            photo = {}
            photo = photos_files[0][1][1]  # пизда

            await bot.send_photo(chat_id=channel_tg,
                                 photo=photo,
                                 caption=caption)
    else:
        await bot.send_message(channel_tg, url)


async def post_from_url_to_vk(vk_token, group_id, url, caption=''):
    response = await vk.handle_url(vk_token, group_id, url, caption)

    if 'post_id' in response:
        response = ('Запостил в ВК.')

    return response


async def parse_message(message):
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
        matches = url_regexp.split(message.text)[1:]

        if matches:
            urls_with_captions = list(zip(*[matches[i::2] for i in range(2)]))
            # TODO: handle multiple links in one message

            # тут посмотреть не скормили ли нам ссылку на псто вк,
            # оттуда надо утянуть картинку
            with dp.current_state(chat=message.chat.id,
                                  user=message.from_user.id) as state:
                data = await state.get_data()

                vk_token = None

                if ('vk_token' in data):
                    vk_token = data['vk_token'].strip()
                else:
                    warning = 'Нужно подключиться к вк, ' +\
                                'чтобы забирать оттуда картинки.'
                    await bot.send_message(message.chat.id, warning)
                    return False, False

                if vk_wall_url.match(urls_with_captions[0][0]):
                    pic_url = await vk.check_wall_post(
                        vk_token,
                        urls_with_captions[0][0])

                elif vk_photo_url.match(urls_with_captions[0][0]):
                    pic_url = await vk.check_photo_post(
                        vk_token,
                        urls_with_captions[0][0])
                else:
                    return urls_with_captions[0]

                urls_with_captions[0] = (
                    pic_url, urls_with_captions[0][1])

            return urls_with_captions[0]

    return False, False


async def startup(dispatcher: Dispatcher):
    vk.http_session = aiohttp.ClientSession()


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()
    vk.http_session.close()


if __name__ == '__main__':
    executor.start_polling(dp,
                           loop=loop,
                           skip_updates=True,
                           on_startup=startup,
                           on_shutdown=shutdown)
