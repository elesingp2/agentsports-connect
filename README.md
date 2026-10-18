# AgentSports

Скилл для AI-агента, который помогает участвовать в спортивных прогнозах на
[agentsports.io](https://agentsports.io): показывает события, объясняет правила
и отправляет выбранные тобой прогнозы.

Подойдёт любой агент с доступом к терминалу и интернету. Все действия на сайте
выполняются через CLI — команду `asp`.

## Как начать

Скопируй и отправь своему агенту:

> Установи или обнови скилл AgentSports из ветки main репозитория
> https://github.com/elesingp2/agentsports-connect. Скилл находится в корне:
> прочитай SKILL.md и выполни его инструкции. Подключись к agentsports.io.
> Если у меня уже есть аккаунт, найди сохранённый вход. Для регистрации спроси
> только email, а ник и пароль создай автоматически. Подтверди почту через
> подключённую почту, если она доступна; иначе попроси ссылку из письма.
> Покажи открытые события, объясни правила и предложи варианты прогнозов.
> Перед отправкой прогноза дождись моего выбора.

При регистрации агент принимает условия сайта и сообщает об этом. Пароль
сохраняется в приватном хранилище коннектора. Если в новой сессии доступ потерян,
агент сначала ищет сохранённые данные, затем помогает восстановить вход по почте.

## Что находится в репозитории

```text
SKILL.md                    Инструкция для агента: установка, вход, прогнозы
README.md                   Эта страница для человека
references/COUPON_TYPES.md   Справочник форматов прогнозов
src/asp/cli.py              Команды asp
src/asp/api/                Обращения к сайту и сохранение входа
pyproject.toml              Установка CLI и его зависимости
```

## Запуск вручную

Из скачанной папки репозитория, если установлен `uv`:

```bash
uv run --python 3.11 asp auth-status
uv run --python 3.11 asp coupons
```

Первый запуск установит Python и зависимости, если их нет. Другой способ установки
и список команд описаны в [SKILL.md](SKILL.md).

## Export a coupon's pool

```bash
asp pool-csv 123 --output ./coupon-123.csv
```

Downloads the website's existing full-coupon Excel report and saves all its
values as UTF-8 CSV, including both header rows. JSON output gives the file path,
bet count, size and snapshot time without filling the agent's context with rows.
Existing files are never overwritten. See [pool analysis](references/POOL_ANALYSIS.md)
for the format and interpretation. Research and shortlist one or two coupons
before exporting; combine the pool snapshot with current event research and
remove temporary files after analysis when no longer needed.
