import aiosqlite


async def insert(name_tab: str, date: str, path: str, id: int) -> None:
    """
    Добавляет данные в базу данных
    name_tab = имя таблицы, в которую будут загружены данные
    date = дата загрузки
    path = путь к файлу относительно папки media
    id = уникальный номер записи
    """
    async with aiosqlite.connect('db.sqlite3') as connect:
        async with connect.cursor() as cursor:
            await cursor.execute(f"INSERT INTO {name_tab} (id, date, image) VALUES (?, ?, ?)", (id, date, path))
            await connect.commit()


async def select(date: str) -> list:
    """
    Извлекает записи из таблицы template_screenshots по дате создание
    date = дата создания записи
    """
    async with aiosqlite.connect('db.sqlite3') as connect:
        async with connect.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM template_screenshots WHERE date = ?", (date,))
            files = [i[2] for i in await cursor.fetchall()]

            return files


async def select_all(name_tab: str) -> list:
    """
    Извлекает все записи из таблицы name_tab
    name_tab = имя таблицы, из которой будут извлечены данные
    """
    async with aiosqlite.connect('db.sqlite3') as connect:
        async with connect.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {name_tab}")
            files = [i[1:3] for i in await cursor.fetchall()]
            return files


async def get_id() -> int:
    """
    Возвращает максимальное значение id из таблицы template_screenshots.
    Используется для определения следующего свободного id при добавлении новой записи.
    """
    async with aiosqlite.connect('db.sqlite3') as connect:
        async with connect.cursor() as cursor:
            try:
                await cursor.execute('SELECT id FROM template_screenshots')
                id = [i[0] for i in await cursor.fetchall()]
                return max(id)
            except:  # Если база данных пустая
                return 0


async def delete() -> None:
    """
    Удаляет все записи из таблицы events_images
    """
    async with aiosqlite.connect('db.sqlite3') as connect:
        async with connect.cursor() as cursor:
            await cursor.execute('DELETE FROM events_images')
            await connect.commit()
