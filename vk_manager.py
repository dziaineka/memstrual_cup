import aiohttp
import urllib
import imghdr
import tempfile
import json

from files_opener import FilesOpener


class VKM:
    def __init__(self):
        self.allowed_image_extensions = ['jpeg', 'jpg', 'gif', 'png', 'gif']
        self.supported_video_platforms = ["youtube.com",
                                          "vimeo.com",
                                          "youtu.be",
                                          "coub.com",
                                          "rutube.ru"]

        self.http_session = aiohttp.ClientSession()

    def __del__(self):
        self.http_session.close()

    async def request_get(self, url, params):
        async with self.http_session.get(url, params=params) as resp:
            return await resp.json()

    async def request_upload_photo(self, url, data):
        resp = await self.http_session.post(url, data=data)

        print(resp.status)
        print(await resp.text())
        return await resp.json(content_type=None)

    async def test_token(self, token):
        params = (
            ('access_token', token),
            ('version', '5.78'),
        )

        url = 'https://api.vk.com/method/account.getProfileInfo'

        response = await self.request_get(url, params)

        account_info = response['response']
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

        url = 'https://api.vk.com/method/groups.getById'

        response = await self.request_get(url, params)

        group_info = response['response'][0]
        name = group_info['name']

        greeting = 'Будем постить в группу \"' + name + '\".'

        if name:
            return True, greeting
        else:
            return False, response.text

    async def handle_url(self, user_token, group_id, url, caption=''):
        if (any(video_platform in url for
                video_platform in self.supported_video_platforms)):
            # Если это ссылка на видео
            # то дописать сюда когда-нибудь обработчик
            pass
        else:
            url_file = urllib.parse.urlsplit(url.strip()).path.split('/')[-1]
            # Расширение файла из url
            extension = url_file.split('.')[-1]

            # Проверка на изображение
            if extension in ['jpg', 'jpeg', 'png']:
                return await self.post_image_from_url(user_token,
                                                      group_id,
                                                      url,
                                                      caption)
            elif extension == 'gif':
                return self.post_gif_from_url(url, caption)

            return await self.post_to_wall(user_token, group_id, caption, url)

    async def post_image_from_url(self, user_token, group_id, url, caption=''):
            # Загружаем фотку на диск
        filepath, extension = self.get_url(url)

        # Проверка расширения после скачивания
        if extension not in self.allowed_image_extensions:
            return 'Error: {} is not an image (allowed extensions: {})'.format(
                filepath, ','.join(self.allowed_image_extensions)
            )
        else:
            # Загружаем фотку на стену группы Вконтакте
            return await self.post_images(user_token,
                                          group_id,
                                          filepath,
                                          caption)

    async def post_images(self, user_token, group_id, image_paths, caption=''):
        # Сначала нужно загрузть фотку на сервера ВК
        photos = await self.upload_images_to_wall(user_token,
                                                  group_id,
                                                  image_paths)

        # Потом получить её ID
        attachments = ','.join([photo['id'] for photo in photos])

        # И запостить на стену группы
        return await self.post_to_wall(user_token,
                                       group_id,
                                       caption,
                                       attachments)

    async def upload_images_to_wall(self, user_token, group_id, paths):
        # получаем адрес сервера для заливания фото
        params = {}
        params['group_id'] = group_id
        params['access_token'] = user_token
        params['version'] = '5.78'

        url = 'https://api.vk.com/method/photos.getWallUploadServer'

        response = await self.request_get(url, params)
        upload_server = response['response']['upload_url']

        # подготавливаем и заливаем фото
        with FilesOpener(paths, key_format='photo') as photos_files:
            photo = {}
            photo['photo'] = photos_files[0][1][1]  # пизда
            response = await self.request_upload_photo(upload_server,
                                                       data=photo)

        # сохраняем фото и останется только этап постинга, сложна
        params.update(response)  # добавляем данные фото в параметры запроса
        url = 'https://api.vk.com/method/photos.saveWallPhoto'

        response = await self.request_get(url, params)
        return response['response']

    def get_url(self, url):
        filename = tempfile.gettempdir() + '/' + url.split('/')[-1]
        filepath, headers = urllib.request.urlretrieve(url, filename)
        headers = headers  # просто так чтобы не было предупреждения
        extension = imghdr.what(filepath)

        return filepath, extension

    async def post_to_wall(self,
                           user_token,
                           group_id,
                           message='',
                           attachments=None):
        params = (
            ('owner_id', '-' + group_id),
            ('from_group', '1'),
            ('message', message),
            ('attachments', attachments),
            ('access_token', user_token),
            ('version', '5.78'),
        )

        url = 'https://api.vk.com/method/wall.post'

        response = await self.request_get(url, params)
        return json.dumps(response['response'])
