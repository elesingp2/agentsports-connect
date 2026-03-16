# Анализ репозитория agentsports-connect: точки роста

## 1. SKILL.md — проблемы как инструкции для AI-агента

### 1.1. Нет стратегического руководства для агента

SKILL.md объясняет **как** вызывать команды, но не помогает агенту **принимать лучшие решения**. Агент, прочитавший этот документ, умеет нажимать кнопки, но не понимает, когда и зачем.

**Что добавить:**
- Руководство по анализу истории (`asp history`) — как интерпретировать `points`, какие паттерны искать
- Рекомендации по спортам: футбол более предсказуем для 1X2 чем MMA
- Базовый bankroll management: не ставить больше X% баланса на одну предикцию
- Рекомендация собирать статистику побед/поражений по спортам и адаптировать стратегию

### 1.2. Линейный workflow без ветвлений

Секция "Returning user" — прямая линия из 7 шагов. В реальности:
- Что если `asp coupons` вернул пустой список?
- Что если все события в купоне уже `betting_closed`?
- Что если баланс ASP = 0 и Wooden room недоступен?
- Что если `asp coupon <id>` вернул неизвестный тип маркета?

**Нужно:** дерево решений или хотя бы секция "Troubleshooting / Edge cases".

### 1.3. Неполная документация outcome codes

Написано: *"Different coupon types use different outcome code ranges (e.g. `292`–`298` for specialized markets)"* — и всё. Агент не знает, что означают эти коды. Даже если он должен читать их из `asp coupon`, ему полезно понимать типы маркетов:
- 1X2 (Match Result): 8/9/10
- Over/Under: какие коды?
- Handicap: какие коды?
- Correct Score: какие коды?

Если коды динамические — написать это явно и убрать вводящий в заблуждение пример с 292-298.

### 1.4. Accuracy scoring — чёрный ящик

Документ говорит "0-100 accuracy score" но не объясняет формулу. Агент не может оптимизировать метрику, которую не понимает. Хотя бы: "accuracy зависит от количества правильных предикций в купоне" или ссылка на документацию agentsports.io.

### 1.5. Нет MCP-специфичного workflow

Workflow написан только через CLI команды (`asp coupons`, `asp predict`). MCP-пользователи (Claude Desktop, Cursor) должны мысленно транслировать в `asp_coupons()`, `asp_predict()`. Стоит добавить параллельный пример или хотя бы примечание.

### 1.6. Frontmatter перегружен

Строки 1-5 содержат массивный JSON в `metadata.openclaw` который полезен для OpenClaw registry, но засоряет документ для агента. Агент тратит токены контекста на парсинг install-инструкций, которые ему не нужны — он уже имеет `asp` в PATH.

---

## 2. Код — баги и архитектурные проблемы

### 2.1. `_try_relogin` повторяет запрос при неудаче вместо возврата 401

**Файл:** `src/asp/api/client.py:100-113`

```python
def _try_relogin(self, http, method, path, headers, meta, kwargs):
    creds = self.state.load_credentials()
    if not creds:
        return http.request(method, path, headers=headers, **kwargs)  # ← повторный запрос, снова 401
    ...
    if login_resp.status_code != 200:
        return http.request(method, path, headers=headers, **kwargs)  # ← повторный запрос, снова 401
```

Если реlogин не удался, метод делает **повторный запрос** к оригинальному endpoint — который снова вернёт 401. Это бессмысленный HTTP-вызов. Нужно возвращать оригинальный 401-ответ, а не делать новый запрос.

### 2.2. Credentials хранятся в plaintext без ограничения прав

**Файл:** `src/asp/api/state.py:112-115`

`credentials.json` записывается через `Path.write_text()` с дефолтным umask. На многопользовательских системах пароль может быть доступен другим пользователям. Нужно `os.chmod(path, 0o600)` после записи.

### 2.3. `logout()` делает двойную блокировку

**Файл:** `src/asp/api/auth.py:35-41`

```python
def logout(self):
    result = self.request("POST", "/api/logout")  # ← lock/unlock внутри request()
    with self.state.lock():                         # ← ещё раз lock
        cookies, meta = self.state.load()
        meta["csrf_token"] = ""
        self.state.save(cookies, meta)
    return result
```

Между первым unlock и вторым lock другой процесс может изменить состояние. CSRF-токен нужно очищать внутри того же lock что и logout-запрос, или через пост-хук в `request()`.

### 2.4. MCP `asp_register` не экспортирует параметр `sex`

CLI имеет `--sex male/female` (`src/asp/cli/main.py:107`), но MCP tool `asp_register` (`src/asp/mcp/server.py:55-76`) не имеет этого параметра. Результат: через MCP всегда будет `sex="male"` (дефолт в `auth.py:56`).

### 2.5. README.md ссылается на несуществующий файл

**Файл:** `README.md:149`

```
│   ├── betting.py    ← Prediction operations
```

Реальный файл — `predictions.py`. README врёт об архитектуре.

### 2.6. Module-level `_client` в MCP server

**Файл:** `src/asp/mcp/server.py:37`

```python
_client = AspClient()  # ← создаётся при импорте модуля
```

`AspClient()` инстанцируется при **импорте** модуля с дефолтным `data_dir="~/.asp/"`. Если кто-то захочет передать `--data-dir` через CLI → MCP, это невозможно. Клиент уже создан.

### 2.7. `_raw_get` не извлекает CSRF-токен

**Файл:** `src/asp/api/client.py:123-138`

`_do_request()` вызывает `self._extract_csrf(resp, meta)`, но `_raw_get()` — нет. Если confirmation endpoint вернёт CSRF-токен (маловероятно, но возможно), он будет потерян.

### 2.8. Mixin-ы без контракта

`AuthMixin`, `PredictionMixin` и др. используют `self.request()` и `self.state`, но нет `Protocol` или `ABC` для описания контракта. IDE не даёт автокомплит внутри mixin-ов, статические анализаторы (mypy, pyright) не могут проверить корректность.

### 2.9. Нет тестов

`pyproject.toml` имеет `[tool.pytest.ini_options]` с `testpaths = ["tests"]`, но директории `tests/` не существует. Ноль тестов на 874 строки кода.

---

## 3. Безопасность

### 3.1. Нет валидации confirmation URL

**Файл:** `src/asp/api/auth.py:77-80`

```python
def confirm(self, confirmation_url: str) -> dict[str, Any]:
    if not confirmation_url.startswith("http"):
        confirmation_url = f"{self._base_url}{confirmation_url}"
    return self._raw_get(confirmation_url)
```

Агент может передать произвольный URL — `_raw_get` выполнит GET с сохранёнными cookies на любой домен. Это SSRF-вектор. Нужно валидировать что URL принадлежит `agentsports.io`.

### 3.2. JSON injection в selections

**Файл:** `src/asp/api/predictions.py:34`

```python
sel = json.loads(selections) if isinstance(selections, str) else selections
```

Парсит произвольный JSON от пользователя и отправляет как есть в API. Если API не валидирует структуру — можно отправить вложенные объекты, массивы, числа вместо строк. Нужна базовая валидация: `selections` должен быть `dict[str, str]`.

---

## 4. DX и качество кода

### 4.1. Нет `py.typed` маркера

Пакет не помечен как typed. Потребители не получат type hints при `import asp`.

### 4.2. Нет `__all__` в `__init__.py`

`src/asp/api/__init__.py` экспортирует `AspClient` и `StateManager`, но без `__all__` — IDE не знает публичный API.

### 4.3. Версия hardcoded в двух местах

`pyproject.toml:version = "1.0.0"` и `src/asp/__init__.py` (вероятно тоже содержит версию). Нужен single source of truth.

### 4.4. Нет CI/CD

Нет `.github/workflows/`, нет `Makefile`, нет `tox.ini`. Для опубликованного PyPI-пакета это плохо.

---

## 5. Приоритизация (что чинить первым)

| Приоритет | Проблема | Влияние |
|-----------|----------|---------|
| **P0** | SSRF через `confirm()` | Безопасность — утечка cookies на произвольный домен |
| **P0** | Credentials без `chmod 600` | Безопасность — пароли доступны другим пользователям |
| **P1** | README ссылается на `betting.py` | Любой новый контрибьютор будет сбит с толку |
| **P1** | `_try_relogin` бессмысленный повторный запрос | Лишний HTTP-вызов при каждом 401 |
| **P1** | MCP `sex` параметр | Неконсистентность CLI/MCP API |
| **P1** | Нет тестов | Невозможно рефакторить безопасно |
| **P2** | SKILL.md: стратегия для агента | Агенты будут делать случайные предикции |
| **P2** | SKILL.md: edge cases | Агенты зависнут на нестандартных сценариях |
| **P2** | Double lock в logout | Race condition при конкурентном доступе |
| **P2** | Module-level client в MCP | Невозможность настройки data_dir |
| **P3** | Mixin-ы без Protocol | DX: нет автокомплита, нет статической проверки |
| **P3** | py.typed, __all__ | DX для потребителей пакета |
| **P3** | CI/CD | Качество: нет автоматических проверок |
