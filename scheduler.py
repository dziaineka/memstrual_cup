import asyncio
import states
import regexp_datetime
import re
import pytz

from aiogram import types
from datetime import datetime, date, timedelta, timezone


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

        post_date = self.get_today_date()
        await state.update_data(post_date=post_date)

        keyboard = self.get_day_selection('сегодня')

        text_message = '''Когда запостить?
Нужно выбрать день и ввести время или ввести время и дату.
        '''

        await message.reply(text_message, reply_markup=keyboard)

    def get_datetime_in_future(self, seconds):
        post_time = (self.get_current_datetime() +
                     timedelta(seconds=seconds + 1))

        day = str(post_time.day).rjust(2, '0')
        month = str(post_time.month).rjust(2, '0')
        year = str(post_time.year).rjust(2, '0')
        hour = str(post_time.hour).rjust(2, '0')
        minute = str(post_time.minute).rjust(2, '0')

        time_message = '{}.{}.{} в {}:{}'.format(day,
                                                 month,
                                                 year,
                                                 hour,
                                                 minute)

        return time_message

    def secs_to_posttime(self, datetime_in_future):
        now = self.get_current_datetime()
        delta = datetime_in_future - now

        if delta.days < 0:
            return -delta.seconds
        else:
            return ((delta.days * 24 * 60 * 60) + delta.seconds)

    def parse_time_input(self, post_date, time_string):
        year = int(post_date.year)
        month = int(post_date.month)
        day = int(post_date.day)
        hour = 0
        minutes = 0

        if self.datetime_regexp.match(time_string):
            time_split = self.datetime_regexp.split(time_string)

            if time_split[1]:
                hour = int(time_split[1])

            if time_split[2]:
                minutes = int(time_split[2])

            if time_split[3]:
                day = int(time_split[3])

                if time_split[4]:
                    month = int(time_split[4])

                    if time_split[5]:
                        year = int(time_split[5])

        # если ввели ноль и дата сегодняшняя, то постим сразу
        zero_time = hour == 0 and minutes == 0
        if zero_time and post_date == date.today():
            return 0

        datetime_in_future = self.get_current_datetime()

        datetime_in_future = datetime_in_future.replace(year=year)
        datetime_in_future = datetime_in_future.replace(month=month)
        datetime_in_future = datetime_in_future.replace(day=day)
        datetime_in_future = datetime_in_future.replace(hour=hour)
        datetime_in_future = datetime_in_future.replace(minute=minutes)

        return self.secs_to_posttime(datetime_in_future)

    def get_today_date(self, shift_days=0):
        tz_minsk = pytz.timezone('Europe/Minsk')
        return datetime.now(tz_minsk).date() + timedelta(days=shift_days)

    def get_current_datetime(self, shift_days=0):
        tz_minsk = pytz.timezone('Europe/Minsk')
        return datetime.now(tz_minsk) + timedelta(days=shift_days)

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
