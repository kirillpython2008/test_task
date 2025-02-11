from fastapi import FastAPI, HTTPException, Request
from starlette.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
import uvicorn

import os
from datetime import datetime
import multiprocessing
import asyncio
import json

from sqlite import select, select_all, delete
from opencv import process_video

app = FastAPI(title='API для поиска людей на видео',
              description='Данное API помогает обнаружить людей на видео',
              version='0.0.1')

# Глобальные переменные для хранения процесса, события остановки и общего счетчика
video_process = None
shared_counter = None
stop_event = None

VIDEO_PATH = 'assets/people_test2.mp4'  # Чтобы изменить путь к видео (по-умолчанию тестовая запись)
SETTINGS_FILE = 'settings.json'  # json Файл с координатами и размерами рамки


@app.get('/start',
         tags=['start / stop'],
         summary='Включить камеру',
         description='Включает камеру для поиска людей')
async def start_camera() -> dict:
    """
    Включает камеру для обнаружения человека,
    в заданной файлом settings.json области
    """
    global video_process, shared_counter, stop_event

    if video_process is not None and video_process.is_alive():
        return {"message": "Обработка видео уже запущена"}

    shared_counter = multiprocessing.Value('i', 1)  # Инициализировать общий счетчик
    stop_event = multiprocessing.Event()  # Инициализировать событие остановки

    video_process = multiprocessing.Process(
        target=process_video,
        args=(VIDEO_PATH, SETTINGS_FILE, stop_event)
    )

    video_process.start()
    return {"message": "Обработка видео запущена"}


@app.get('/stop',
         tags=['start / stop'],
         summary='Выключить камеру',
         description='Выключает камеру для поиска людей')
async def stop_camera() -> dict:
    """
    Удаляет все данные из таблицы events_images.
    Останавливает процесс записи видео
    """
    global video_process, stop_event, shared_counter

    await delete()

    if video_process is None:
        return {"message": "Обработка видео не запущена"}

    if video_process.is_alive():
        print("Сигнализируем процессу видео о завершении")
        stop_event.set()  # Установить событие остановки
        video_process.join()  # Подождать завершения процесса
        print("Процесс видео завершён")
    else:
        print("Процесс видео не был активен")

    # Сбросить глобальные переменные независимо от состояния процесса
    video_process = None
    stop_event = None
    shared_counter = None
    return {"message": "Обработка видео остановлена"}


class ValidateDate(BaseModel):  # Валидация даты на корректность
    """
    Проверяет дату введенную пользователем на корректность.
    Если дата некорректная вызывает исключение ValueError
    """
    date: str

    @field_validator('date')
    def validate_date(cls, date: str) -> str:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Неправильный формат даты. Ожидается YYYY-MM-DD (например, 2025-01-01)')

        year, month, day = map(int, date.split('-'))
        if not 1970 <= year <= 2025:
            raise ValueError('Год должен быть в диапазоне от 1970 до 2025')
        return date


@app.get('/humans/{date}',
         tags=['find humans'],
         description='Выводит список путей фоток людей по их дате',
         summary='Поиск людей')
async def get_humans(date: str):
    """
    Возвращает список расположений скриншотов (result), найденных на дату date
    Если данных не найдено возвращает 'Скриншотов на данную дату не найдено'
    Если дата некорректная вызывает исключение ValueError с сообщением, что в дате написано неправильно
    """
    try:
        validated_date = ValidateDate(date=date)

        result = [os.path.abspath(file) for file in await select(validated_date.date)]

        if result:
            return result
        else:
            return 'Скриншотов на данную дату не найдено'
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


app.mount("/static", StaticFiles(directory="static"), name="static")  # Подключение css к шаблонам
app.mount('/media', StaticFiles(directory='media'), name='media')  # Подключение картинок к шаблону template-main.html
templates = Jinja2Templates(directory='templates')


@app.get('/events',
         response_class=HTMLResponse,
         tags=['events'],
         summary='Отслеживание добавления изображения в базу данных',
         description='Позволяет отслеживать изображения, добавленные в базу данных в реальном времени по SSE')
async def get_events(request: Request):
    """
    Возвращает шаблон template-events.html,
    в который передаются обновления о добавлении новых изображений в таблицу events_images
    """
    context = {
        'request': request,
        'screenshots': []  # Пустой список, так как данные будут загружаться через SSE
    }
    return templates.TemplateResponse("template-events.html", context)


@app.get('/events/stream',
         tags=['events'],
         summary="SSE Endpoint для обновлений событий",
         description="Предоставляет поток SSE с обновлениями из таблицы events_images")
async def stream_events():
    async def event_generator():
        while True:
            screenshots = await select_all('events_images')
            data = json.dumps(screenshots)
            yield f"data: {data}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get('/',
         response_class=HTMLResponse,
         tags=['main'],
         summary='Отображение текущих фотографий',
         description='Страница для просмотра текущих изображений, добавленных в базу данных в реальном времени по SSE')
async def get_main_page(request: Request):
    """
    Возвращает шаблон template-main.html,
    в который передаются новые изображения,
    из таблицы events_image по sse
    """
    context = {
        'request': request,
        'screenshots': []  # Пустой список, так как данные будут загружаться через SSE
    }
    return templates.TemplateResponse("template-main.html", context)


@app.get('/main/stream',
         tags=['main'],
         summary="SSE Endpoint для обновлений событий",
         description="Предоставляет поток SSE с обновлениями из таблицы events_images")
async def stream_events():
    async def event_generator():
        while True:
            screenshots = await select_all('events_images')
            data = json.dumps(screenshots)
            yield f"data: {data}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=5000)  # запускаем сервер Uvicorn для обслуживания приложения FastAPI
