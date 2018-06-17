import asyncio
import datetime
import states


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
        await message.reply('Когда запостить?')

    def secs_to_posttime(self, datetime_in_future):
        now = datetime.datetime.now()
        delta = datetime_in_future - now

        return delta.seconds
