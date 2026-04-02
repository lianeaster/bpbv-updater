# bpbv-updater

Настільний застосунок для публікації новин у репозиторій сайту кафедри БПБВ: [lianeaster/bpbv](https://github.com/lianeaster/bpbv).

## Можливості

- Поле **«Секція для оновлення»** (зараз лише «Новини»).
- **Дата** у форматі день / місяць / рік (на картці відображається як `ДД.ММ.РРРР`).
- **Текст**: перший непорожній рядок стає заголовком картки; решта — анонс і повний текст у блоці «Детальніше» (через `<details>`, без кнопки Facebook).
- **Зображення** (JPEG, PNG, WebP, GIF): перше — обкладинка картки; наступні додаються до розгорнутого тексту. Завантажуються в `images/news/` у репозиторії.
- **Відправити** оновлює `index.html`, `translations.js` і файли зображень через [GitHub Contents API](https://docs.github.com/en/rest/repos/contents) (персональний токен).

Тексти для ключів `news.cardN*` дублюються у всі чотири мови файлу перекладів (український вміст як тимчасовий варіант для EN/DE/FR — за потреби відредагуйте `translations.js` у GitHub вручну).

## Запуск

```bash
cd bpbv-updater
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Токен GitHub

Створіть [Personal access token (classic)](https://github.com/settings/tokens) з областю **repo** (повний доступ до приватних репозиторіїв не обов’язковий — достатньо прав на push у цей публічний репозиторій). Вставте токен у поле в приложении. Не публікуйте токен і не комітьте його в git.

### Збірка .exe (Windows)

На машині з Windows, у віртуальному середовищі з установленим PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name bpbv-updater app.py
```

Щоб бачити текстові помилки в консолі, приберіть прапорець `--windowed`.

Готовий `bpbv-updater.exe` з’явиться в каталозі `dist/`. На macOS аналогічно отримаєте `dist/bpbv-updater` (без розширення .exe).

## Примітки

- Кожне збереження файлу через API створює окремий коміт на гілці `main` (зображення та правки HTML/JS можуть йти кількома комітами підряд).
- Якщо структура `index.html` або `translations.js` у [bpbv](https://github.com/lianeaster/bpbv) зміниться так, що зникне блок `#newsList` або ключі `news.readMore`, оновлювач потрібно буде адаптувати.

## Ліцензія

Як і в репозиторії-оригіналі сайту — див. [bpbv/LICENSE](https://github.com/lianeaster/bpbv/blob/main/LICENSE).
