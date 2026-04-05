# Telegram PC Assistant (Windows)

Локальный интеллектуальный Telegram-бот на Python для безопасного управления ПК через OpenAI Responses API и ограниченный набор инструментов.

## Что реализовано
- Текстовые и голосовые команды через Telegram.
- LLM-оркестрация через OpenAI Responses API + function calling.
- Локальный policy-layer (`CommandPolicy`) между LLM и системными действиями.
- Подтверждение опасных действий (inline-кнопки `Подтвердить` / `Отмена`).
- Локальные keyboard-кнопки Telegram для быстрых действий без вызова LLM.
- Операции с файлами в белом списке директорий.
- Извлечение текста из `docx`/`pdf`, краткий пересказ.
- Сетевые шаблонные команды (`IP`, `ping`, `check internet`).
- Локальный полнотекстовый индекс (`SQLite FTS5`) и поиск по содержимому.
- Планировщик задач (`APScheduler`) и отмена задач.
- Автозапуск на Windows через Startup folder.
- Логирование с ротацией + журнал сгенерированных `.ps1`.
- Unit-тесты для policy, file tools и command routing.

## Структура проекта
Собрана в соответствии с ТЗ:

- `app.py`
- `bot/`
- `llm/`
- `tools/`
- `speech/`
- `security/`
- `search/`
- `storage/`
- `tests/`
- `config.yaml`
- `.env.example`
- `requirements.txt`

## Требования
- Windows 10/11
- Python 3.11+
- PowerShell
- Telegram Bot Token
- OpenAI API key
- `ffmpeg` (для конвертации Telegram voice через `pydub`)

## Установка
1. Создайте venv и установите зависимости:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Скопируйте `.env.example` в `.env` и заполните:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `TELEGRAM_ALLOWED_USER_IDS` (обязательный whitelist Telegram user ID)
3. При необходимости отредактируйте `config.yaml`.

## Запуск
```powershell
python app.py
```

## Тесты
```powershell
pytest -q
```

## Основные команды
- `Найди файл Курсы.docx`
- `Выключи компьютер через 30 минут` (с подтверждением)
- `Через 30 минут запусти notepad`
- `Почисти папку Загрузки` (с подтверждением)
- `Пингани google.com`
- `Пересобери индекс`
- `Включи автозапуск` / `Выключи автозапуск` (с подтверждением)

## Безопасность
- LLM не имеет прямого доступа к shell.
- Любое действие проходит через `security/policy.py`.
- Запрещены команды вне allowlist.
- Блокируются опасные паттерны (инъекции, реестр, destructive-последовательности).
- Файловые операции ограничены `ALLOWED_DIRS`.
- Опасные действия только после явного подтверждения.
- Финальное решение об исполнении принимает Python policy-layer, не модель.

## Важные замечания
- Для voice-команд требуется корректно установленный `ffmpeg`.
- STT использует `faster-whisper` локально (CPU).
- `mute/unmute` использует `pycaw` при наличии; иначе fallback через media key toggle.
- Не задавайте пустой `TELEGRAM_ALLOWED_USER_IDS` в production.
