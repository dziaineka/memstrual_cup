import asyncio
import datetime
import states
import regexp_datetime
import re

from aiogram import types


class Scheduler:
    def __init__(self):
        self.datetime_regexp = re.compile(regexp_datetime.FULL_DATETIME)

    async def schedule_post(self, dispatcher, message):
        # сохраним ID поста, который нужно запланировать
        with dispatcher.current_state(chat=message.chat.id,
                                      user=message.from_user.id) as state:
            await state.update_data(message_to_schedule_id=message.message_id)

        # пользователь вводит время
        await self.input_time_to_post(dispatcher, message)

    async def input_time_to_post(self, dispatcher, message):
        # Get current state
        state = dispatcher.current_state(chat=message.chat.id,
                                         user=message.from_user.id)

        # Update user's state
        await state.set_state(states.DATETIME_INPUT)

        post_date = datetime.date.today()
        await state.update_data(post_date=post_date)

        keyboard = self.get_day_selection('сегодня')

        text_message = '''Когда запостить?
Нужно выбрать день и ввести время или ввести время и дату.
        '''

        await message.reply(text_message, reply_markup=keyboard)

    def get_datetime_in_future(self, seconds):
        return (datetime.datetime.now() +
                datetime.timedelta(seconds=seconds + 1))

    def secs_to_posttime(self, datetime_in_future):
        now = datetime.datetime.now()
        delta = datetime_in_future - now

        if delta.days < 0:
            return -delta.seconds
        else:
            return delta.seconds

    def parse_time_input(self, post_date, time_string):
        year = int(post_date.year)
        month = int(post_date.month)
        day = int(post_date.day)
        hour = 0
        minutes = 0

        if self.datetime_regexp.match(time_string):
            time_split = self.datetime_regexp.split(time_string)

            hour = int(time_split[1])
            minutes = int(time_split[2])

            if time_split[3]:
                day = int(time_split[3])

                if time_split[4]:
                    month = int(time_split[4])

                    if time_split[5]:
                        year = int(time_split[5])

        # если ввели ноль и дата сегодняшняя, то постим сразу
        zero_time = hour == 0 and minutes == 0
        if zero_time and post_date == datetime.date.today():
            return 0

        datetime_in_future = datetime.datetime(year,
                                               month,
                                               day,
                                               hour,
                                               minutes)

        return self.secs_to_posttime(datetime_in_future)

    def get_day_selection(self, dayType=''):
        # настроим клавиатуру
        keyboard = types.InlineKeyboardMarkup(row_width=3)

        if dayType == "сегодня":
            button_text = '✔️ Сегодня'
        else:
            button_text = 'Сегодня'

        button_today = types.InlineKeyboardButton(
            text=button_text,
            callback_data="сегодня")

        if dayType == "завтра":
            button_text = '✔️ Завтра'
        else:
            button_text = 'Завтра'

        button_tomorrow = types.InlineKeyboardButton(
            text=button_text,
            callback_data="завтра")

        if dayType == "послезавтра":
            button_text = '✔️ Послезавтра'
        else:
            button_text = 'Послезавтра'

        button_next_day = types.InlineKeyboardButton(
            text=button_text,
            callback_data="послезавтра")

        keyboard.add(button_today, button_tomorrow, button_next_day)

        return keyboard
