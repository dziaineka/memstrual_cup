import aiovk
import requests
import json


class VKM:
    def __init__(self):
        self.allowed_image_extensions = ['jpeg', 'jpg', 'gif', 'png', 'gif']
        self.supported_video_platforms = ["youtube.com",
                                          "vimeo.com",
                                          "youtu.be",
                                          "coub.com",
                                          "rutube.ru"]

    async def test_token(self, token):
        params = (
            ('access_token', token),
            ('version', '5.78'),
        )

        response = requests.get(
            'https://api.vk.com/method/account.getProfileInfo',
            params=params)

        account_info = json.loads(response.text)['response']
        first_name = account_info['first_name']
        last_name = account_info['last_name']

        greeting = 'Привет, ' + first_name + ' ' + last_name + '!'

        if first_name or last_name:
            return True, greeting
        else:
            return False, response.text

    async def test_group_id(self, group_id, token):
        params = (
            ('access_token', token),
            ('group_ids', group_id),
            ('version', '5.78'),
        )

        response = requests.get(
            'https://api.vk.com/method/groups.getById',
            params=params)

        group_info = json.loads(response.text)['response'][0]
        name = group_info['name']

        greeting = 'Будем постить в группу \"' + name + '\".'

        if name:
            return True, greeting
        else:
            return False, response.text

    def post_to_wall(self, message, user_token, attachments=None):
        params = (
            ('owner_id', '-134904770'),
            ('from_group', '1'),
            ('message', 'Hello world!'),
            ('access_token', user_token),
            ('version', '5.78'),
        )

        response = requests.get('https://api.vk.com/method/wall.post',
                                params=params)

        print(response.text)
