FROM python:3.10.8-alpine3.15

WORKDIR /usr/src/app

RUN apk add build-base

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./main.py" ]
