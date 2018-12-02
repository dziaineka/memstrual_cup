import json
import logging
import re
import tempfile
import urllib
from os import path

import regexps
from files_opener import FilesOpener


logger = logging.getLogger('memstrual_log')


class VKM:
    def __init__(self):
        self.allowed_image_extensions = ['.jpeg',
                                         '.jpg',
                                         '.gif',
                                         '.png',
                                         '.gif']

        self.supported_video_platforms = ["youtube.com",
                                          "vimeo.com",
                                          "youtu.be",
                                          "coub.com",
                                          "rutube.ru"]

        self.http_session = None
        self.vk_wall_url = re.compile(regexps.VK_WALL_URL, re.IGNORECASE)
        self.vk_photo_url = re.compile(regexps.VK_PHOTO_URL, re.IGNORECASE)

    async def request_get(self, url, params):
        async with self.http_session.get(url, params=params) as resp:
            status = resp.status

            try:
                response = await resp.json(content_type=None)
            except json.decoder.JSONDecodeError:
                logger.warning('Опять результат реквеста не смог в json')
                response = None

            return response, status

    async def request_post(self, url, data):
        resp = await self.http_session.post(url, data=data)
        return await resp.json(content_type=None)

    async def test_token(self, token):
        params = (
            ('access_token', token),
            ('version', '5.78'),
        )

        url = 'https://api.vk.com/method/account.getProfileInfo'

        response, status = await self.request_get(url, params)

        try:
            account_info = response['response']
            first_name = account_info['first_name']
            last_name = account_info['last_name']

            greeting = 'Привет, ' + first_name + ' ' + last_name + '!'
        except KeyError:
            return False, response.text

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

        response, status = await self.request_get(url, params)

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
            # тут постим видео, если оно по ссылке
            return await self.post_video_from_url(user_token,
                                                  group_id,
                                                  url,
                                                  caption)
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
            elif extension == 'mp4':
                return await self.post_video_from_url(user_token,
                                                      group_id,
                                                      url,
                                                      caption)

            return await self.post_to_wall(user_token, group_id, caption, url)

    async def post_video_from_url(self, user_token, group_id, url, caption=''):
        if not url:
            raise ValueError('URL is required')

        # таким образом мы удалям ссылку из текста, если постим
        # ее как аттачмент
        caption = caption.replace(url, '')

        params = {
            'description': caption,
            'wallpost': 1,
            'link': url,
            'group_id': group_id,
            'access_token': user_token,
            'version': '5.78'
        }

        method_url = 'https://api.vk.com/method/video.save'
        response, status = await self.request_get(method_url, params)

        try:
            url = response['response']['upload_url']
        except KeyError:
            url = response['response']['video']['upload_url']

        response = await self.request_post(url,
                                           data=None)

        try:
            if response['response'] == 1:
                return True
        except KeyError:
            return response['error_msg']

    async def post_image_from_url(self, user_token, group_id, url, caption=''):
            # Загружаем фотку на диск
        filepath, extension = self.get_filepath(url)

        # Проверка расширения после скачивания
        if extension not in self.allowed_image_extensions:
            return await self.post_to_wall(user_token,
                                           group_id,
                                           caption)
        else:
            # таким образом мы удалям ссылку из текста, если постим
            # ее как аттачмент
            caption = caption.replace(url, '')

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
        params = {'group_id': group_id,
                  'access_token': user_token,
                  'version': '5.78'}

        url = 'https://api.vk.com/method/photos.getWallUploadServer'

        response, status = await self.request_get(url, params)
        upload_server = response['response']['upload_url']

        # подготавливаем и заливаем фото
        with FilesOpener(paths, key_format='photo') as photos_files:
            photo = {'photo': photos_files[0][1][1]}
            response = await self.request_post(upload_server,
                                               data=photo)

        # сохраняем фото и останется только этап постинга, сложна
        params.update(response)  # добавляем данные фото в параметры запроса
        url = 'https://api.vk.com/method/photos.saveWallPhoto'

        response, status = await self.request_get(url, params)
        return response['response']

    @staticmethod
    def get_filepath(url):
        if not url:
            return '', ''

        filename = tempfile.gettempdir() + '/' + url.split('/')[-1]

        try:
            filepath, headers = urllib.request.urlretrieve(url, filename)
        except Exception:
            return '', ''

        filename, extension = path.splitext(filepath)

        return filepath, extension

    async def post_to_wall(self,
                           user_token,
                           group_id,
                           message='',
                           attachments=''):
        params = (
            ('owner_id', '-' + group_id),
            ('from_group', '1'),
            ('message', message),
            ('attachments', attachments),
            ('access_token', user_token),
            ('version', '5.78'),
        )

        url = 'https://api.vk.com/method/wall.post'

        response, status = await self.request_get(url, params)

        if status == 200:
            return True
        elif status == 414:
            return 'Слишком большая длина текста для постинга в ВК. ВК лох.'
        else:
            return ('Что-то пошло не так, код ошибки - ' + status)

    async def check_wall_post(self, user_token, url):
        url_splited = self.vk_wall_url.search(url)
        pic_id = url_splited.group('id')

        if pic_id:
            api_url = 'https://api.vk.com/method/wall.getById'

            params = (
                ('posts', '-' + pic_id),
                ('access_token', user_token),
                ('version', '5.78'),
            )

            response, status = await self.request_get(api_url, params)

            try:
                post = response['response'][0]['attachment']['photo']
                new_url = self.get_biggest_size_link(post)
            except KeyError:
                new_url = url

            return new_url
        else:
            return url

    @staticmethod
    def get_biggest_size_link(vk_post):
        if 'src_xxxbig' in vk_post:
            return vk_post['src_xxxbig']
        elif 'src_xxbig' in vk_post:
            return vk_post['src_xxbig']
        elif 'src_xbig' in vk_post:
            return vk_post['src_xbig']
        elif 'src_big' in vk_post:
            return vk_post['src_big']
        elif 'src' in vk_post:
            return vk_post['src']
        elif 'src_small' in vk_post:
            return vk_post['src_small']
        else:
            raise KeyError

    async def check_photo_post(self, user_token, url):
        url_splited = self.vk_photo_url.search(url)
        pic_id = url_splited.group('id')

        if not pic_id:
            return url

        api_url = 'https://api.vk.com/method/photos.getById'

        params = (
            ('photos', '-' + pic_id),
            ('access_token', user_token),
            ('version', '5.78'),
        )

        response, status = await self.request_get(api_url, params)

        try:
            post = response['response'][0]
            new_url = self.get_biggest_size_link(post)
        except KeyError:
            return url

        return new_url
