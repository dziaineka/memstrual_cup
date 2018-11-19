from aiogram.dispatcher.filters.state import State, StatesGroup


# States
class Form(StatesGroup):
    initial = State()  # In storage as 'Form:initial'
    channel_name = State()  # In storage as 'Form:channel_name'
    vk_token = State()  # In storage as 'Form:vk_token'
    group_id = State()  # In storage as 'Form:group_id'
    operational_mode = State()  # In storage as 'Form:operational_mode'
    datetime_input = State()  # In storage as 'Form:datetime_input'
