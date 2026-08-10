# OPERATIONS — Gambling Community Bot

Бот: [@GamblingCommunitybot](https://t.me/GamblingCommunitybot) — анкета доступа в Private Gambling Community.

## Где
- Сервер: VPS `193.111.62.16`
- Каталог: `/opt/gambling_community_bot`
- venv: `/opt/gambling_community_bot/.venv` (Python 3.12)
- Сервис: `gambling-community-bot.service`
- БД: `/opt/gambling_community_bot/gambling_community.sqlite3` (источник правды)
- Персистентность: `/opt/gambling_community_bot/bot_persistence.pkl` (состояние диалогов и
  user_data; создаётся при первом взаимодействии, переживает рестарт). Runtime-файл —
  не в git, исключён из rsync. Удаление сбросит незаконченные анкеты в процессе (готовые —
  уже в SQLite/Sheets, не теряются).

## Управление
```bash
systemctl status gambling-community-bot
systemctl restart gambling-community-bot
journalctl -u gambling-community-bot -n 100 --no-pager
```

## Конфигурация (`.env`)
- `BOT_TOKEN` — токен из @BotFather.
- `ADMIN_IDS` — кому слать новые анкеты, кто может `/export` и `/stats` (через запятую).
- `COMMUNITY_INVITE_URL` — **ЗАГЛУШКА** ссылки «Вступить в сообщество» (блок 7). Заменить на реальный invite (`https://t.me/+...`) и `restart`.
- Google Sheets: пока `GOOGLE_SHEETS_ENABLED=false` — нет ID таблицы.

## Админка / CMS «Контент»
Команды (только для `ADMIN_IDS`):
- `/admin` — раздел «Управление контентом»: **Тексты** (сообщения блоков 1–7), **Кнопки**
  (Основные / Вертикали / Грейды / Инвестор) и **Медиа** (GIF/фото/видео на экранах).
  Правка текста/кнопки — прислать новый текст; медиа — прислать GIF/фото/видео; есть
  «♻ Сбросить»/«🗑 Удалить медиа». Изменения применяются на лету, без рестарта.
  Экран с медиа показывается как фото/гиф/видео, текст экрана становится подписью.
- `/export` — CSV всех анкет. `/stats` — счётчики и статус Sheets.
- `/myid` — узнать свой Telegram ID (доступно всем; для заполнения `ADMIN_IDS`).

CMS-схема: оверрайды в SQLite (`button_settings`, `content_texts`, `media_assets`),
эффективное значение = override → дефолт из `constants.py` (`BUTTON_DEFAULTS`/`TEXT_DEFAULTS`).
Рендер экрана — единый `_show(key)` в flow.py: с медиа шлёт фото/гиф/видео+подпись, без —
текст; переход text↔media пересоздаёт сообщение (Clean Chat, один экран). Профессии (1131) —
данные, в CMS не редактируются. Подписи вертикалей/грейдов привязаны к индексу: правка подписи
не меняет логику и сохраняемые в анкету канонические значения.

## Медиакит (PDF перед инвайтом)
После анкеты, до финального экрана с кнопкой «Вступить», бот шлёт отдельным документом
PDF-медиакит GURO (аудитория, «Гэмблинговый суд», спонсорские тарифы) — показывает ценность
комьюнити в момент максимальной вовлечённости и параллельно работает как тихая воронка
спонсорских лидов.
- Файлы (статический ассет, НЕ в CMS): `assets/media_kit/GURO-Mediakit-RU.pdf`,
  `assets/media_kit/GURO-Media-Kit-EN.pdf`. Язык выбирается по `lang` анкеты.
  Чтобы обновить файл — заменить PDF по тому же пути и `restart` (кэш file_id не используется,
  бот каждый раз читает файл с диска).
- Подпись — CMS-текст `media_kit_caption` / `media_kit_caption_en` (правится как обычный экран
  из `/admin` → Тексты).
- Отправка best-effort (`handlers/flow.py::_send_media_kit`): сбой отправки логируется, но НЕ
  блокирует выдачу инвайт-ссылки. Забаненным (`storage.is_banned`) не отправляется.

## Clean Chat
Бот удаляет сообщения-команды (`/start`, `/admin`, `/myid`, `/export`, `/stats`) и весь
пользовательский ввод (ответы анкеты, тексты/медиа при правке в CMS) — остаётся один
активный экран. На экранах «Другое» (своя вертикаль и своя должность) есть кнопка «Назад»
(`vo_back`/`po_back`) — не тупик.

## Архитектура (Clean Core)
- `config.py` — настройки из окружения.
- `constants.py` — тексты блоков 1–7 + вертикали/грейды/инвестор.
- `professions_data.py` — авто-сгенерирован из ТЗ (вертикаль→грейд→[(code,label)], 1131 поз.).
- `ui.py` — клавиатуры (пагинация профессий).
- `logic.py` — чистые функции (пагинация, карточка, строка таблицы, html_escape).
- `storage.py` — SQLite + мягкие миграции `_ensure_column`.
- `google_sheets_sync.py` — best-effort запись анкет в таблицу.
- `handlers/flow.py` — ConversationHandler всего флоу (Clean Chat: один экран).
- `handlers/admin.py` — `/export`, `/stats`.
- `handlers/group_captcha.py` — капча для новичков в группе (второй уровень).
- `bot.py` — точка входа.

## Второй уровень: капча в группе + меню-ссылки после неё
Бот должен быть **админом группы** с правом **Banning users** (restrict). При входе
новичка `ChatMemberHandler` (CHAT_MEMBER) мутит его (`restrict_chat_member`, все права
False) и шлёт капчу ОДНИМ сообщением: медиа экрана `captcha_welcome` (видео/гиф/фото из
CMS) + приветствие с упоминанием (`tg://user?id=`) ENG/RU со ссылками на главные чаты +
пример «A + B = ?» и кнопки-варианты (`cap:<uid>:<value>`), один верный.
- **Неверный ответ** → тот же приём/фото остаётся, текст+кнопки редактируются на новый
  пример (`edit_message_caption`/`edit_message_text`), пользователь остаётся в муте.
  Капча бесконечна, кик/бан НЕ используются.
- **Верный ответ** → размут (`restrict_chat_member` с дефолтными правами чата), и бот
  **редактирует ТО ЖЕ сообщение** (видео/фото остаётся): текст меняется на
  `captcha_success` (та же инфа про главные чаты, без блока CAPTCHA) + клавиатура
  меняется с вариантов ответа на **5 инлайн-кнопок-ссылок** (`ui.group_menu_kb`) —
  Terms/GuroPSP/GuroAffiliate/iGamingSchool/Collaboration. Сообщение НЕ удаляется —
  остаётся в чате как постоянная памятка со ссылками (как и было по референсу).
  Инлайн-кнопки надёжно открывают ссылку и не пропадают, пока жива сама message —
  никакого якоря/самовосстановления не требуется (в отличие от нижней reply-клавиатуры,
  которую пробовали и отказались — см. ниже).
- Состояние ждущих капчу хранится в `chat_data["captcha"][user_id]` (переживает рестарт).

Конфиг капчи (`.env`): `CAPTCHA_ENABLED` (true/false), `CAPTCHA_OPTIONS` (число кнопок, ≥2),
`CAPTCHA_GROUP_IDS` (белый список ID групп через запятую; пусто = любые группы). Тексты
(`captcha_welcome`, `captcha_success`) и видео — в `/admin` → Тексты/Медиа. Сами 5 кнопок
(текст/ссылка/цвет/премиум-эмодзи/вкл-выкл) — `/admin` → «🔗 Меню группы» (таблица
`menu_buttons`, сидинг дефолтов при первом старте).

**Почему не reply-клавиатура снизу (пробовали и откатили):** Telegram не даёт reply-кнопкам
(под строкой ввода) открывать ссылку по нажатию (проверено: `url` через api_kwargs
рендерится, но не срабатывает), и клавиатура держится только пока жива хотя бы одна её
message — удалили последнюю, и кнопки у пользователей пропадают (тоже проверено на живой
группе). Инлайн-подход (кнопки на самом сообщении капчи) решает оба недостатка сразу.
- Цвет/премиум-эмодзи на кнопках — `style`/`icon_custom_emoji_id` через `api_kwargs`
  (см. `ui.link_button`), приём подсмотрен в Таки Вместе (aiogram) и воспроизведён в PTB.

## Тесты (обязательно перед деплоем)
```bash
cd /opt/gambling_community_bot && .venv/bin/python simulate_bot_tests.py
```
Проверяет данные, логику, хранилище, CMS, капчу (логика + симуляция вход/мут/неверно/верно/
размут, бот-новичок, чужой клик, allowlist, media) и сценарии флоу (включая отправку
медиакита RU/EN и её отсутствие у забаненных). PASS=3258.

## Деплой (по манифесту)
1. backup live-каталога.
2. rsync в `*_candidate`.
3. `simulate_bot_tests.py` в candidate.
4. rsync в live, прогон тестов в live.
5. `systemctl restart` → проверка `journalctl`.
6. удалить candidate.

## ОТКРЫТО / TODO
- [ ] Получить от владельца реальную invite-ссылку → `COMMUNITY_INVITE_URL`.
- [ ] Создать Google-таблицу, выдать доступ `island-summary-bot@ostrovbot.iam.gserviceaccount.com`,
      положить `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_ENABLED=true`, при необходимости
      залить накопленные анкеты из SQLite (`/export` → импорт или backfill-скрипт).
- [x] Прислать числовой Telegram ID владельца → `ADMIN_IDS` (1417059280, 8315845804).
- [ ] Капча: заменить заглушки ссылок на главные чаты под реальную группу (CMS, экран
      «Капча в группе»). Видео уже залито. При желании сузить `CAPTCHA_GROUP_IDS` под продакшн-группу.

## GURO ID Mini App (партнёрства/репутация), 09-10.08.2026

Отдельный модуль поверх бота — фиксация подтверждённого сотрудничества между
участниками и репутация (см. ТЗ владельца, п.1-8). НЕ отменяет и не заменяет
план networking-заявки/реф-центра/колеса фортуны (04.08) — это отдельный
раздел общего будущего Mini App.

**Компоненты:**
- `guro_constants.py`, `guro_logic.py` — чистые функции (формула репутации,
  анти-фрод, валидация Telegram WebApp initData).
- `guro_storage.py` — свои таблицы `guro_users`/`partnerships` в ТОМ ЖЕ
  `gambling_community.sqlite3` (WAL включён), `profiles` не трогает.
- `guro_id_api.py` — отдельный aiohttp-процесс/systemd-сервис
  `guro-id-api.service`, слушает `127.0.0.1:8092` (`GURO_ID_API_PORT`),
  раздаёт JSON (`/api/me`, `/api/search`, `/api/partnerships`, `/api/subscribe`)
  и статику собранного фронтенда (`webapp/dist`).
- `handlers/guro_partnerships.py`, `handlers/guro_payments.py` — кнопки
  Подтвердить/Отклонить и Telegram Stars (pre_checkout/successful_payment)
  обрабатывает ТОЛЬКО bot.py (он единственный поллит getUpdates) —
  guro_id_api.py лишь шлёт первое уведомление через разовый `Bot(token=...)`.
- `webapp/` — React+Vite SPA (4 экрана MVP из ТЗ п.5) + `framer-motion`
  (анимированные переходы между табами, staggered-появление карточек/списков,
  тактильная отдача через `Telegram.WebApp.HapticFeedback`, добавлено
  10.08.2026). Собирается ЛОКАЛЬНО (`npm install && npm run build` — на
  сервере Node не установлен) и копируется на сервер как `webapp/dist/`.
  Замена содержимого `dist/` НЕ требует рестарта `guro-id-api.service` —
  aiohttp отдаёт статику с диска на каждый запрос (проверено на практике).
- Menu Button бота (`bot.py` → `post_init`) открывает Mini App напрямую,
  URL — `GURO_ID_WEBAPP_URL` (settings).

**Инфраструктура (важное отличие от предположения в исходном плане — на этом
сервере НЕ nginx, а Webuzo-Apache):**
- Публичный адрес: `https://guro-app.193.111.62.16.sslip.io/` (два новых
  vhost-файла — `/usr/local/apps/apache2/etc/conf.d/guro_id_vhost.conf` (HTTP,
  редирект на HTTPS) и `guro_id_vhost_ssl.conf` (HTTPS, ProxyPass на
  `127.0.0.1:8092`), сертификат Let's Encrypt через `certbot certonly --webroot
  -w /var/www/guro-id-acme` (сам certbot не был установлен — доставлен
  отдельно, `apt install certbot`; автопродление — `certbot.timer`).
- Apache здесь управляется НЕ systemd (`httpd.service` в systemd числится
  неактивным) — бинарник напрямую: конфиг-тест `/usr/local/apps/apache2/bin/httpd
  -t`, применение изменений `/usr/local/apps/apache2/bin/httpd -k graceful`
  (НЕ полный restart — не рвёт соединения других живых сайтов на этом Apache:
  панель Webuzo, Odessa-бот прокси, Island Live Map).
- При переезде на купленный домен: получить новый сертификат
  (`certbot certonly --webroot ...` под новый домен), поменять `ServerName`+
  `SSLCertificateFile/KeyFile` в обоих vhost-файлах, `GURO_ID_WEBAPP_URL` в
  `.env`, `httpd -k graceful`.

**Известное ограничение платформы:** Bot API не отправит сообщение
произвольному `@username` — партнёрство можно подтвердить только с тем, кто
уже проходил анкету бота (есть строка в `profiles`). Это ожидаемо (см. ТЗ:
фиксация уже существующих в комьюнити знакомств), но UI явно сообщает об
ошибке `NO_CONFIRMER_PROFILE`.

**Тюнинг, требующий решения владельца (сейчас — стартовые значения по
умолчанию, не зафиксированы в ТЗ):**
- `guro_constants.CONFIRMATION_WEIGHT = 10.0` — вес одного партнёрства в
  формуле репутации.
- `guro_constants.SUBSCRIPTION_STARS_PRICE = 150` (XTR) и
  `SUBSCRIPTION_DURATION_DAYS = 30` — цена/срок подписки.

**Тесты:** `simulate_bot_tests.py` дополнен блоками `guro_id: initData`,
`guro_id: формула репутации`, `guro_id: storage`, `guro_id: API (aiohttp
routes)`, `guro_id: bot-side partnership/payment handlers` — все через
временные SQLite-файлы и фейковые Bot/Update, реальных Telegram-запросов не
делают.

**Ручная проверка после деплоя (сделать на реальном аккаунте):**
1. В личке с ботом открыть Menu Button (GURO ID) → вкладка «Профиль».
2. Отправить заявку на партнёрство со второго тестового аккаунта → на первом
   должно прийти сообщение с кнопками Подтвердить/Отклонить.
3. Подтвердить → в обоих профилях должна появиться запись.
4. Оплатить тестовую подписку Stars (если тестовый режим недоступен — хотя бы
   убедиться, что `createInvoiceLink` отдаёт рабочую ссылку и `successful_payment`
   правильно проставляет `guro_users.subscription_status`).

## GURO ID — статус-тег в чате (setChatMemberTag), 10.08.2026

По просьбе заказчика: видно прямо в группе, что автор сообщения — участник
GURO ID (и платный ли), без захода в Mini App. Реализовано через нативный
`Bot.set_chat_member_tag` (Bot API 22.7+, метод `setChatMemberTag`) — тег
у ОБЫЧНОГО участника (не только у админов, как `setChatAdministratorCustomTitle`),
поэтому не упирается в лимит ~50 админов на группу. Максимум 16 символов,
эмодзи запрещены Bot API. Подсмотрено у соседнего Island Summary Bot
(`rating.py` — там тем же методом показывается репутация-скор, у нас статус).

**Потребовало апгрейда `python-telegram-bot` 21.6 → 22.8** (метода не было в
21.x) — прогнан весь `simulate_bot_tests.py` (PASS=3343 на момент апгрейда,
без апгрейда падать было некуда, т.к. новых вызовов ещё не было) до и после,
задеплоено, регрессий не найдено. Право `can_manage_tags` у бота уже было
(видно, что выдаётся автоматически полным админам) — ручных действий от
владельца группы не потребовалось.

**Компоненты:**
- `guro_tags.py` — ядро: `target_tag()` (GURO_TAG_BASE «GURO ID» без подписки
  / GURO_TAG_PRO «GURO ID PRO» с активной), `sync_member_tag()` (пропускает
  админов/овнера/left/banned и НЕ перетирает тег, который участник выставил
  себе сам вручную — сравнивает с `GC.GURO_TAGS`), `sync_member_tag_standalone()`
  (разовый `Bot(token=...)` для процессов без Application), `sync_all_members()`
  (пакетный обход с паузой между вызовами).
- Точки вызова: `guro_id_api.py` `handle_me` (тег освежается при каждом
  открытии профиля в Mini App), `handlers/guro_payments.py`
  `on_guro_successful_payment` (мгновенное повышение до PRO сразу после
  оплаты), `guro_tags_sync.py` (systemd timer `guro-tags-sync.timer`,
  раз в час — единственное место, где тег ПОНИЖАЕТСЯ обратно при истечении
  подписки, т.к. для этого события нет триггера в реальном времени; заодно
  подчищает то, что не долетело сразу из-за сети/лимитов).
- `guro_storage.list_guro_user_ids()` — только те, кто хоть раз коснулся
  GURO ID (таблица `guro_users`), не вся группа — избегаем сотен тысяч лишних
  вызовов `getChatMember` по всей группе на 5000+ человек.

**Проверено на проде 10.08.2026:** ручной запуск `systemctl start
guro-tags-sync.service` реально проставил тег «GURO ID» двум живым
участникам группы (`getChatMember`/`setChatMemberTag` → 200 OK в логах).

**Тесты:** новый блок `guro_id: статус-тег в чате (guro_tags)` в
`simulate_bot_tests.py` (skip админа, skip ручного тега, апгрейд до PRO,
`sync_all_members`) + точечные проверки в существующих блоках `guro_id: API`
и `guro_id: bot-side partnership/payment handlers` (тег действительно
уходит после `/api/me` и после `successful_payment`). PASS=3353 FAIL=0.

## ОТКРЫТО / TODO (GURO ID)
- [ ] Подтвердить у владельца `CONFIRMATION_WEIGHT`/цену подписки (сейчас —
      стартовые значения по умолчанию).
- [ ] Сквозной прогон эталонного сценария ТЗ п.2 на реальных аккаунтах.
- [ ] Решить: остаться на sslip.io или переехать на купленный поддомен GURO.
- [ ] Т.к. это первая реализация Mini App в проекте — при добавлении
      следующих модулей (заявка на нетворкинг, реф-центр, колесо фортуны из
      плана 04.08) переиспользовать `webapp/` каркас (табы) и `guro_id_api.py`
      как основу общего API, а не плодить отдельные сервисы/домены.
