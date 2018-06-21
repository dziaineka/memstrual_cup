import asyncio
import datetime
import states

from aiogram import types


class Scheduler:
    def __init__(self):
        pass

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

        keyboard = self.get_day_selection('сегодня')

        text_message = '''Когда запостить?
Нужно выбрать день и ввести время или ввести время и дату.
        '''

        await message.reply(text_message, reply_markup=keyboard)

    def secs_to_posttime(self, datetime_in_future):
        now = datetime.datetime.now()
        delta = datetime_in_future - now

        return delta.seconds

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
