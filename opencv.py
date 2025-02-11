import cv2
import mediapipe as mp

import asyncio
import json
import time
import datetime
import os
import multiprocessing

from sqlite import insert, get_id


class EmergencyStopException(Exception):
    pass


def process_video(video_path: str, settings_file: str, stop_event) -> None:
    """
    Обрабатывает видео, обнаруживает позы людей и сохраняет скриншоты выделенной области,
    когда поза человека обнаружена внутри этой области на протяжении 5 секунд.

    Аргументы:
        video_path (str): Путь к видеофайлу.
        settings_file (str): Путь к JSON файлу с настройками области интереса (x, y, width, height).
        stop_event (multiprocessing.Event): Событие, сигнализирующее о необходимости остановки обработки.
    """
    capture = cv2.VideoCapture(video_path)

    body_sol = mp.solutions.pose
    body = body_sol.Pose(
        static_image_mode=False,
        min_tracking_confidence=0.6,
        min_detection_confidence=0.6)
    draw = mp.solutions.drawing_utils

    try:
        with open(settings_file, 'r') as settings:
            data = json.load(settings)

            position_border_x = data['x']
            position_border_y = data['y']
            scale_border_x = data['width']
            scale_border_y = data['height']
    except:  # Если не получилось открыть settings.json
        position_border_x = 100
        position_border_y = 100
        scale_border_x = 100
        scale_border_y = 100

    last_screen_time = 0  # Начальное значение времени
    screen_interval = 5  # Сколько секунд человек должен находиться в заданной области

    while capture.isOpened():
        # Проверяем, не было ли запрошено завершение
        if stop_event.is_set():
            print("Получен сигнал остановки. Завершаем обработку видео")
            break

        ret, img = capture.read()
        if not ret:
            break

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        op = body.process(rgb)
        if op.pose_landmarks:
            draw.draw_landmarks(img, op.pose_landmarks, body_sol.POSE_CONNECTIONS)

            for landmark in op.pose_landmarks.landmark:
                x = landmark.x * img.shape[1]
                y = landmark.y * img.shape[0]

                if (position_border_x <= x <= position_border_x + scale_border_x) and \
                        (position_border_y <= y <= position_border_y + scale_border_y):
                    current_time = time.time()

                    if current_time - last_screen_time >= screen_interval:
                        last_screen_time = current_time

                        # Сохранение скриншота области рамки
                        resized_image = cv2.resize(img, (1280, 720))
                        screenshot = resized_image[position_border_y:position_border_y + scale_border_y,
                                     position_border_x:position_border_x + scale_border_x]

                        count = asyncio.run(get_id())

                        asyncio.run(insert('template_screenshots', str(datetime.date.today()), f'screenshots/screenshot_{count + 1}_{datetime.date.today()}.png', count + 1))
                        asyncio.run(insert('events_images', str(datetime.date.today()), f'screenshots/screenshot_{count + 1}_{datetime.date.today()}.png', count + 1))

                        cv2.imwrite(os.path.join(f'media/screenshots/screenshot_{count + 1}_{datetime.date.today()}.png'), screenshot)
                        print(f'Скриншот сохранен как media/screenshots/screenshot_{count + 1}_{datetime.date.today()}.png')


        resized_image = cv2.resize(img, (1280, 720))
        cv2.rectangle(resized_image, (position_border_x, position_border_y),
                      (position_border_x + scale_border_x, position_border_y + scale_border_y),
                      (0, 0, 255),
                      thickness=2)
        cv2.imshow('window', resized_image)


        if cv2.waitKey(1) == ord('q'):
            break


    capture.release()
    cv2.destroyAllWindows()



def main(stop=False) -> None:
    """
    Запускает процесс, который включает камеру,
    если stop = True происходит остановка записи видео
    """
    if stop:
        raise EmergencyStopException('Остановка видео')

    settings_file = 'settings.json'
    screenshots_dir = 'screenshots'

    # Создаем событие для сигнализации об остановке процесса
    stop_event = multiprocessing.Event()

    # Создаем и запускаем процесс
    video_process = multiprocessing.Process(target=process_video, args=(settings_file, screenshots_dir, stop_event))
    video_process.start()
