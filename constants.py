"""Тексты блоков 1–7 и справочные данные анкеты (из ТЗ)."""
from __future__ import annotations

from professions_data import PROFESSIONS

# --- Вертикали (Блок 2) ---
VERTICALS: tuple[str, ...] = (
    "Gambling",
    "Betting",
    "Crypto",
    "Dating",
    "E-Commerce",
    "FinTech",
    "Nutra",
    "Other",
)

# --- Грейды ---
GRADES: tuple[str, ...] = (
    "C-Level",
    "Head of / Director",
    "Management",
    "Senior",
    "Specialist",
    "Junior / Entry",
)

INVESTOR_GRADE = "Инвестор"  # доступен только для Gambling (по ТЗ)

# --- Инвестор-ветка (только Gambling) ---
INVESTOR_TYPES: tuple[str, ...] = (
    "Частный инвестор (инвестирую свои деньги)",
    "Управляющий / Инвест-менеджер (ищу проекты для фонда)",
    "Венчурный фонд / Инвест-группа (инвестирую от лица организации)",
    "Агентство",
)

INVESTOR_AMOUNTS: tuple[str, ...] = (
    "Micro / Angel: до $25k",
    "Seed / Early stage: $25k – $100k",
    "Growth / Series A: $100k – $500k",
    "Institutional: $500k+",
)

INVESTOR_NEEDS: tuple[str, ...] = (
    "Поиск стартапов для инвестиций",
    "Поиск партнеров / нетворкинг",
    "Поиск специалистов / кадров",
    "Хочу предложить услуги своему фонду",
)


def grades_for(vertical: str) -> tuple[str, ...]:
    """Список грейдов для вертикали (у Gambling добавляется «Инвестор»)."""
    if vertical == "Gambling":
        return GRADES + (INVESTOR_GRADE,)
    return GRADES


def professions_for(vertical: str, grade: str) -> list[tuple[str, str]]:
    return list(PROFESSIONS.get(vertical, {}).get(grade, []))


# --- Кнопки (подписи) ---
BTN_START = "Получить доступ"
BTN_BACK = "« Назад"
BTN_OTHER = "Другое"
BTN_SKIP = "Пропустить"
BTN_DONE = "Готово ✅"
BTN_JOIN = "Вступить в сообщество"
BTN_PREV = "◀"
BTN_NEXT = "▶"

PROFESSIONS_PER_PAGE = 8

# --- Тексты блоков ---
WELCOME_TEXT = (
    "<b>Добро пожаловать в Private Gambling Community</b>\n\n"
    "<blockquote>Private Gambling Community — международное профессиональное сообщество "
    "специалистов из Gambling, Betting, Crypto, Payments и других направлений.\n\n"
    "В сообществе {members}+ участников: владельцы компаний, C-level, "
    "руководители направлений и специалисты разных уровней.\n\n"
    "PGC используется для нетворкинга, поиска партнёров, сотрудников, работы "
    "и обмена опытом внутри индустрии.\n\n"
    "Мы используем короткую анкету, чтобы:\n"
    "• быстрее находить релевантные контакты внутри комьюнити\n"
    "• показывать вам людей и возможности, которые действительно подходят вашему профилю\n"
    "• улучшать качество нетворкинга внутри сообщества</blockquote>\n\n"
    "<tg-emoji emoji-id=\"5399817885952520170\">🎁</tg-emoji> Доступ в сообщество <b>бесплатный</b>.\n\n"
    "Для получения доступа ответьте на несколько коротких вопросов.\n\n"
    "<tg-emoji emoji-id=\"5330271224285115429\">⌛</tg-emoji> Заполнение анкеты займёт менее 1 минуты."
)

ASK_VERTICAL = "<tg-emoji emoji-id=\"5301180276917952560\">📊</tg-emoji> Выберите вашу вертикаль:"
ASK_VERTICAL_OTHER = "<tg-emoji emoji-id=\"5199880874786588162\">✍️</tg-emoji> Опишите вашу вертикаль своими словами:"
ASK_GRADE = "<tg-emoji emoji-id=\"5301166722001168584\">📈</tg-emoji> Выберите ваш грейд:"

ASK_INVESTOR_TYPE = "<tg-emoji emoji-id=\"5301142197737908809\">💼</tg-emoji> Кто вы как инвестор?"
ASK_INVESTOR_AMOUNT = "<tg-emoji emoji-id=\"5301207025974271730\">💰</tg-emoji> Какие суммы инвестиций рассматриваете?"
ASK_INVESTOR_NEEDS = (
    "<tg-emoji emoji-id=\"5301219309580738905\">🔎</tg-emoji> Что вы ищете в нашем комьюнити?\n"
    "<blockquote>Можно выбрать несколько вариантов, затем нажмите «Готово».</blockquote>"
)

ASK_PROFESSION = "<tg-emoji emoji-id=\"5462912188186395985\">🧑‍💻</tg-emoji> Выберите вашу должность:"
ASK_PROFESSION_OTHER = "<tg-emoji emoji-id=\"5199880874786588162\">✍️</tg-emoji> Опишите вашу должность своими словами:"

ASK_REQUEST = (
    "<tg-emoji emoji-id=\"5242486160088899134\">🎯</tg-emoji> <b>Что для вас сейчас наиболее актуально?</b>\n\n"
    "<blockquote>Например:\n"
    "• поиск работы;\n"
    "• поиск сотрудников;\n"
    "• поиск партнёров;\n"
    "• поиск трафика;\n"
    "• поиск рекламодателей;\n"
    "• поиск платёжного решения;\n"
    "• поиск новых GEO или офферов;\n"
    "• профессиональный нетворкинг.</blockquote>\n\n"
    "Опишите ваш запрос в свободной форме."
)

ASK_NAME = "<tg-emoji emoji-id=\"5348246615901624312\">😎</tg-emoji> Как вас зовут?"

ASK_COUNTRY = "<tg-emoji emoji-id=\"5247013300432019467\">🌐</tg-emoji> В какой стране вы находитесь?"

ASK_COMPANY = (
    "<tg-emoji emoji-id=\"5431646131941556182\">🏪</tg-emoji> В какой компании (продукте) или проекте вы работаете?\n"
    "<blockquote>Нам часто поступают обращения, и если мы будем понимать, какой у вас продукт — "
    "нам будет легче познакомить вас по делу, найти клиента и т.д.</blockquote>\n\n"
    "Если не можете указать название компании, напишите:\n"
    "<code>NDA</code> · <code>Freelance</code> · <code>Consultant</code> · <code>Own Project</code>"
)

ASK_LINKEDIN = (
    "<tg-emoji emoji-id=\"5332565591519670753\">🔗</tg-emoji> Оставьте ссылку на ваш LinkedIn или другой профессиональный профиль.\n\n"
    "<blockquote>Если не хотите указывать контакт, нажмите кнопку «Пропустить».</blockquote>"
)

FINAL_TEXT = (
    "<tg-emoji emoji-id=\"5436011369197484799\">🏆</tg-emoji> <b>Спасибо за заполнение анкеты!</b>\n\n"
    "<tg-emoji emoji-id=\"5319306413296599737\">✅</tg-emoji> Ваша регистрация успешно завершена.\n\n"
    "Для вступления в Private Gambling Community используйте кнопку ниже.\n\n"
    "<blockquote>По вопросам спонсорства и размещения бренда: @GuroArtem. "
    "Помогаем проектам стать заметными и укрепить репутацию внутри профессионального "
    "сообщества Guro.\n"
    "Лично обсудим варианты стратегического участия и приоритетного позиционирования.</blockquote>"
)

# Медиакит (PDF) — отправляется отдельным документом перед FINAL_TEXT/final_en, чтобы
# показать ценность сообщества до выдачи инвайта. Путь — статический ассет деплоя (не CMS).
MEDIA_KIT_RU_PATH = "assets/media_kit/GURO-Mediakit-RU.pdf"
MEDIA_KIT_EN_PATH = "assets/media_kit/GURO-Media-Kit-EN.pdf"

MEDIA_KIT_CAPTION = (
    "📎 Медиакит GURO — коротко о сообществе: аудитория, «Гэмблинговый суд» "
    "(уже вернул участникам $500K+) и тарифы для брендов-спонсоров."
)

# Показывается вместо FINAL_TEXT, если анкету заполнил забаненный администратором
# юзер (storage.is_banned) — доступ НЕ открывается, инвайт-ссылка не выдаётся.
BANNED_NOTICE_TEXT = (
    "🚫 <b>Доступ к сообществу ограничен администрацией.</b>\n\n"
    "Анкета сохранена, но автоматического вступления не будет.\n\n"
    "<blockquote>Если считаете это ошибкой — напишите администратору.</blockquote>"
)

# =========================================================================
# EN-версии текстов и кнопок анкеты (выбор языка на старте).
# Данные анкеты (вертикали/грейды/должности) НЕ переводятся — единый список.
# Ключ EN-версии = базовый ключ + «_en»; CMS правит их как обычные экраны.
# =========================================================================

LANG_SELECT_TEXT = (
    "<b>Welcome to Private Gambling Community!</b>\n"
    "<blockquote>Please choose your language for the short application form 👇</blockquote>\n"
    "<b>Добро пожаловать в Private Gambling Community!</b>\n"
    "<blockquote>Выберите язык для заполнения короткой анкеты 👇</blockquote>"
)

WELCOME_TEXT_EN = (
    "<b>Welcome to Private Gambling Community</b>\n\n"
    "<blockquote>Private Gambling Community is an international professional community of "
    "specialists in Gambling, Betting, Crypto, Payments and other verticals.\n\n"
    "The community unites {members}+ members: company owners, C-level executives, "
    "heads of departments and specialists of all levels.\n\n"
    "PGC is used for networking, finding partners and employees, job search "
    "and sharing expertise within the industry.\n\n"
    "We use a short application form to:\n"
    "• find relevant contacts inside the community faster\n"
    "• show you people and opportunities that truly match your profile\n"
    "• improve the quality of networking in the community</blockquote>\n\n"
    "<tg-emoji emoji-id=\"5399817885952520170\">🎁</tg-emoji> Access to the community is <b>free</b>.\n\n"
    "To get access, please answer a few short questions.\n\n"
    "<tg-emoji emoji-id=\"5330271224285115429\">⌛</tg-emoji> It takes less than 1 minute."
)

ASK_VERTICAL_EN = "<tg-emoji emoji-id=\"5301180276917952560\">📊</tg-emoji> Choose your vertical:"
ASK_VERTICAL_OTHER_EN = "<tg-emoji emoji-id=\"5199880874786588162\">✍️</tg-emoji> Describe your vertical in your own words:"
ASK_GRADE_EN = "<tg-emoji emoji-id=\"5301166722001168584\">📈</tg-emoji> Choose your grade:"

ASK_INVESTOR_TYPE_EN = "<tg-emoji emoji-id=\"5301142197737908809\">💼</tg-emoji> Who are you as an investor?"
ASK_INVESTOR_AMOUNT_EN = "<tg-emoji emoji-id=\"5301207025974271730\">💰</tg-emoji> What investment amounts do you consider?"
ASK_INVESTOR_NEEDS_EN = (
    "<tg-emoji emoji-id=\"5301219309580738905\">🔎</tg-emoji> What are you looking for in our community?\n"
    "<blockquote>You can select several options, then press “Done”.</blockquote>"
)

ASK_PROFESSION_EN = "<tg-emoji emoji-id=\"5462912188186395985\">🧑‍💻</tg-emoji> Choose your position:"
ASK_PROFESSION_OTHER_EN = "<tg-emoji emoji-id=\"5199880874786588162\">✍️</tg-emoji> Describe your position in your own words:"

ASK_REQUEST_EN = (
    "<tg-emoji emoji-id=\"5242486160088899134\">🎯</tg-emoji> <b>What is most relevant for you right now?</b>\n\n"
    "<blockquote>For example:\n"
    "• job search;\n"
    "• hiring;\n"
    "• looking for partners;\n"
    "• traffic;\n"
    "• advertisers;\n"
    "• payment solutions;\n"
    "• new GEOs or offers;\n"
    "• professional networking.</blockquote>\n\n"
    "Describe your request in free form."
)

ASK_NAME_EN = "<tg-emoji emoji-id=\"5348246615901624312\">😎</tg-emoji> What is your name?"

ASK_COUNTRY_EN = "<tg-emoji emoji-id=\"5247013300432019467\">🌐</tg-emoji> Which country are you based in?"

ASK_COMPANY_EN = (
    "<tg-emoji emoji-id=\"5431646131941556182\">🏪</tg-emoji> What company (product) or project do you work at?\n"
    "<blockquote>We receive many requests, and knowing your product makes it easier to "
    "introduce you properly, find you a client, etc.</blockquote>\n\n"
    "If you can\'t share the company name, write:\n"
    "<code>NDA</code> · <code>Freelance</code> · <code>Consultant</code> · <code>Own Project</code>"
)

ASK_LINKEDIN_EN = (
    "<tg-emoji emoji-id=\"5332565591519670753\">🔗</tg-emoji> Share a link to your LinkedIn or another professional profile.\n\n"
    "<blockquote>If you prefer not to, press “Skip”.</blockquote>"
)

FINAL_TEXT_EN = (
    "<tg-emoji emoji-id=\"5436011369197484799\">🏆</tg-emoji> <b>Thank you for completing the form!</b>\n\n"
    "<tg-emoji emoji-id=\"5319306413296599737\">✅</tg-emoji> Your registration is complete.\n\n"
    "Use the button below to join Private Gambling Community.\n\n"
    "<blockquote>For sponsorship and brand placement: @GuroArtem. We help projects gain "
    "visibility and strengthen their reputation within the Guro professional "
    "community.\n"
    "Let\'s discuss options for strategic participation and priority positioning.</blockquote>"
)

MEDIA_KIT_CAPTION_EN = (
    "📎 GURO media kit — a quick look at the community: audience, the Gambling Court "
    "(already recovered $500K+ for members), and rates for sponsor brands."
)

BANNED_NOTICE_TEXT_EN = (
    "🚫 <b>Your access to the community has been restricted by the administration.</b>\n\n"
    "Your form has been saved, but access will not be granted automatically.\n\n"
    "<blockquote>If you believe this is a mistake, please contact an administrator.</blockquote>"
)

# Кнопки выбора языка. ВАЖНО: русский — БЕЗ флага (требование владельца).
BTN_LANG_EN = "🇬🇧 English"
BTN_LANG_RU = "Русский"

INVESTOR_TYPES_EN: tuple[str, ...] = (
    "Private investor (investing my own money)",
    "Fund manager / Investment manager (looking for projects for a fund)",
    "VC fund / Investment group (investing on behalf of an organization)",
    "Agency",
)

INVESTOR_AMOUNTS_EN: tuple[str, ...] = (
    "Micro / Angel: up to $25k",
    "Seed / Early stage: $25k – $100k",
    "Growth / Series A: $100k – $500k",
    "Institutional: $500k+",
)

INVESTOR_NEEDS_EN: tuple[str, ...] = (
    "Looking for startups to invest in",
    "Partners / networking",
    "Looking for specialists / hiring",
    "Want to offer services to a fund",
)

SKIPPED_VALUE = "—"

# --- Капча для новичков в группе (Блок «второй уровень») ---
# Приветствие новичку. Плейсхолдер {captcha} заменяется на пример «A + B = ?».
# Ссылки на главные чаты — заглушки из примера, владелец меняет их в CMS под свою группу.
# Премиум-эмодзи (id владельца): 🟡→желтый маркер, 🇪🇺/🇬🇧→флаги в "ENG".
_CAPTCHA_DOT_EMOJI_ID = "5915838505551926382"
_CAPTCHA_EU_EMOJI_ID = "5285354520728059265"
_CAPTCHA_GB_EMOJI_ID = "5285511458833055328"

# Общая шапка (ссылки на главные чаты) — используется и в приветствии, и после успеха.
CAPTCHA_INTRO_TEXT = (
    'Introduce yourself in <a href="https://t.me/c/1924507124/35226">'
    f'<tg-emoji emoji-id="{_CAPTCHA_DOT_EMOJI_ID}">🟡</tg-emoji> <b>Main Chat</b></a> '
    f'<tg-emoji emoji-id="{_CAPTCHA_EU_EMOJI_ID}">🇪🇺</tg-emoji>ENG'
    f'<tg-emoji emoji-id="{_CAPTCHA_GB_EMOJI_ID}">🇬🇧</tg-emoji> within 15 min\n\n'
    'Представьтесь в <a href="https://t.me/c/1924507124/1">'
    f'<tg-emoji emoji-id="{_CAPTCHA_DOT_EMOJI_ID}">🟡</tg-emoji> <b>Главный чат (СНГ)</b></a> '
    "в течение 15 минут"
)

CAPTCHA_WELCOME_TEXT = (
    CAPTCHA_INTRO_TEXT + "\n\n"
    "<blockquote>30+ sections (swipe from left to right)</blockquote>\n\n"
    "<tg-emoji emoji-id=\"5332565591519670753\">🔗</tg-emoji> Полезные ссылки сообщества — ниже 👇"
)

# После верного ответа бот РЕДАКТИРУЕТ то же сообщение капчи: убирает капчу, оставляет
# ту же информацию (ссылки на главные чаты) и меняет клавиатуру на 5 кнопок-ссылок.
CAPTCHA_SUCCESS_TEXT = (
    CAPTCHA_INTRO_TEXT + "\n\n"
    "✅ Верификация пройдена. Полезные ссылки сообщества — ниже 👇"
)

# Приветствие в группе ПОСЛЕ анкеты (handlers/group_captcha._send_greeting) —
# 24.07.2026: разведено по языку анкеты (profiles.lang), в отличие от
# CAPTCHA_WELCOME_TEXT/CAPTCHA_SUCCESS_TEXT выше (капча на входе, отдельная
# функция, туда не лезем) — RU уходит в основной топик (СНГ), EN — в топик
# COMMUNITY_EN_TOPIC_ID. Каждый вариант ссылается только на СВОЙ чат.
GROUP_GREETING_TEXT_RU = (
    'Представьтесь в <a href="https://t.me/c/1924507124/1">'
    f'<tg-emoji emoji-id="{_CAPTCHA_DOT_EMOJI_ID}">🟡</tg-emoji> <b>Главный чат (СНГ)</b></a> '
    "в течение 15 минут\n\n"
    "<blockquote>30+ разделов (свайп слева направо)</blockquote>\n\n"
    '<tg-emoji emoji-id="5332565591519670753">🔗</tg-emoji> Полезные ссылки сообщества — ниже 👇'
)

GROUP_GREETING_TEXT_EN = (
    'Introduce yourself in <a href="https://t.me/c/1924507124/35226">'
    f'<tg-emoji emoji-id="{_CAPTCHA_EU_EMOJI_ID}">🇪🇺</tg-emoji>'
    f'<tg-emoji emoji-id="{_CAPTCHA_GB_EMOJI_ID}">🇬🇧</tg-emoji> <b>Main Chat ENG</b></a> '
    "within 15 min\n\n"
    "<blockquote>30+ sections (swipe from left to right)</blockquote>\n\n"
    '<tg-emoji emoji-id="5332565591519670753">🔗</tg-emoji> Useful community links — below 👇'
)

# Гейт группы: сообщение участнику без анкеты (он замучен до прохождения).
GATE_PROMPT_TEXT = (
    "<tg-emoji emoji-id=\"5226935195906620050\">🔐</tg-emoji> Access to the chat opens after a short form — tap the button below.\n"
    "Доступ к чату открывается после короткой анкеты у бота — жмите кнопку ниже.\n\n"
    "<blockquote><tg-emoji emoji-id=\"6037496202990194718\">🔓</tg-emoji> Бот вернёт возможность писать автоматически, сразу после анкеты 👇</blockquote>"
)
GATE_BUTTON_LABEL = "📋 Пройти анкету / Fill the form"

# Премиум-иконки кнопок (icon_custom_emoji_id), из интернет-паков 16.07.2026.
LANG_RU_EMOJI_ID = "5247013300432019467"  # 🌐 глобус (GTAOnlineIcons, вариант C)
START_BUTTON_EMOJI_ID = "5318898653396485988"  # ⭐ звезда (InterfaceElements)
GATE_BUTTON_EMOJI_ID = "5199880874786588162"   # ✍️ перо (InterfaceElements)
JOIN_BUTTON_EMOJI_ID = "5368842040647919004"   # 🚀 ракета (Rich369)
INVITE_BUTTON_EMOJI_ID = "5467450727372693938"  # реф-кнопка «Пригласить/Invite» в группе

# Постоянная reply-клавиатура в группе (заменяет клавиатуру ввода у ВСЕХ
# участников) — plain-текст, Telegram не поддерживает цвет/premium-эмодзи
# для reply-кнопок (это только для inline).
GROUP_KB_INVITE_TEXT = "➕ Пригласить/Invite"
GROUP_KB_INVITE_TEXT_EN = "➕ Invite"  # для EN-приветствия (group_greeting_en)

# Иконки кнопок вертикалей (Блок 2), по индексу VERTICALS. 16.07.2026.
VERTICAL_EMOJI_IDS: tuple[str, ...] = (
    "5213044588771562736",  # Gambling 🎰 (casinoimg)
    "5199662179346822252",  # Betting ⚽️ (football pack)
    "5300848194341596510",  # Crypto 🪙 (FinanceAnimations)
    "5381963389075489428",  # Dating 💌 (InterfaceElements)
    "5380013551232495435",  # E-Commerce 🛍 (InterfaceElements)
    "5244669145936570101",  # FinTech 🏦 (GTAOnlineIcons)
    "5377753109944610780",  # Nutra 💊 (GTAOnlineIcons)
    "5201979339972836348",  # Other ❔ (InterfaceElements)
)

# Цвета кнопок вертикалей (Блок 2), по индексу VERTICALS (решение владельца 20.07.2026).
VERTICAL_STYLES: tuple[str, ...] = (
    "primary",  # Gambling
    "success",  # Betting
    "success",  # Crypto
    "primary",  # Dating
    "primary",  # E-Commerce
    "success",  # FinTech
    "success",  # Nutra
    "primary",  # Other
)

# Стили (цвета) кнопок Telegram. Прокидываются в API через api_kwargs["style"].
MENU_STYLE_LABELS: dict[str, str] = {
    "default": "⚪ Обычный (серый)",
    "primary": "🔵 Синий (primary)",
    "success": "🟢 Зелёный (success)",
    "danger": "🔴 Красный (danger)",
}

# Дефолтные кнопки-ссылки панели. slot — порядок и стабильный id.
# style/emoji_id — цвет и премиум-эмодзи-иконка (по умолчанию пусто, задаются в /admin).
MENU_BUTTON_DEFAULTS: tuple[dict, ...] = (
    {"slot": 0, "label": "Terms", "url": "https://t.me/c/1924507124/1883/23168"},
    {"slot": 1, "label": "GuroPSP", "url": "https://t.me/GuroPSP"},
    {"slot": 2, "label": "GuroAffiliate", "url": "https://t.me/GuroAffiliate"},
    {"slot": 3, "label": "iGamingSchool", "url": "https://t.me/iGamingSchool"},
    {"slot": 4, "label": "Collaboration", "url": "https://t.me/GuroArtem"},
)


# =========================================================================
# CMS — редактируемый контент (раздел «Контент» в /admin)
# Эффективное значение = override из БД → иначе дефолт отсюда.
# Подписи вертикалей/грейдов/инвестора привязаны к ключу (индексу), поэтому
# правка подписи НЕ меняет внутреннюю логику и данные анкеты.
# =========================================================================

BUTTON_DEFAULTS: dict[str, str] = {
    "start": BTN_START,
    "back": BTN_BACK,
    "other": BTN_OTHER,
    "skip": BTN_SKIP,
    "done": BTN_DONE,
    "join": BTN_JOIN,
    "prev": BTN_PREV,
    "next": BTN_NEXT,
    "g_inv": INVESTOR_GRADE,
    "guro_id": "🪪 Открыть GURO ID",
}
for _i, _v in enumerate(VERTICALS):
    BUTTON_DEFAULTS[f"v_{_i}"] = _v
for _i, _g in enumerate(GRADES):
    BUTTON_DEFAULTS[f"g_{_i}"] = _g
for _i, _t in enumerate(INVESTOR_TYPES):
    BUTTON_DEFAULTS[f"it_{_i}"] = _t
for _i, _a in enumerate(INVESTOR_AMOUNTS):
    BUTTON_DEFAULTS[f"ia_{_i}"] = _a
for _i, _n in enumerate(INVESTOR_NEEDS):
    BUTTON_DEFAULTS[f"in_{_i}"] = _n

# EN-двойники служебных кнопок (данные v_*/g_* не переводятся — уже английские)
BUTTON_DEFAULTS.update({
    "lang_en": BTN_LANG_EN,
    "lang_ru": BTN_LANG_RU,
    "start_en": "Get access",
    "back_en": "« Back",
    "other_en": "Other",
    "skip_en": "Skip",
    "done_en": "Done ✅",
    "join_en": "Join the community",
    "g_inv_en": "Investor",
    "gate": GATE_BUTTON_LABEL,
    "guro_id_en": "🪪 Open GURO ID",
})
for _i, _v in enumerate(INVESTOR_TYPES_EN):
    BUTTON_DEFAULTS[f"it_{_i}_en"] = _v
for _i, _a in enumerate(INVESTOR_AMOUNTS_EN):
    BUTTON_DEFAULTS[f"ia_{_i}_en"] = _a
for _i, _n in enumerate(INVESTOR_NEEDS_EN):
    BUTTON_DEFAULTS[f"in_{_i}_en"] = _n

# Группы для админ-каталога кнопок: (заголовок, [ключи])
BUTTON_CATALOG: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Основные", ("start", "join", "guro_id", "skip", "other", "back", "done", "prev", "next",
                  "lang_en", "lang_ru", "gate")),
    ("Основные (EN)", ("start_en", "join_en", "guro_id_en", "skip_en", "other_en", "back_en", "done_en")),
    ("Вертикали", tuple(f"v_{i}" for i in range(len(VERTICALS)))),
    ("Грейды", tuple(f"g_{i}" for i in range(len(GRADES))) + ("g_inv", "g_inv_en")),
    ("Инвестор", tuple(
        [f"it_{i}" for i in range(len(INVESTOR_TYPES))]
        + [f"ia_{i}" for i in range(len(INVESTOR_AMOUNTS))]
        + [f"in_{i}" for i in range(len(INVESTOR_NEEDS))]
    )),
    ("Инвестор (EN)", tuple(
        [f"it_{i}_en" for i in range(len(INVESTOR_TYPES_EN))]
        + [f"ia_{i}_en" for i in range(len(INVESTOR_AMOUNTS_EN))]
        + [f"in_{i}_en" for i in range(len(INVESTOR_NEEDS_EN))]
    )),
)

TEXT_DEFAULTS: dict[str, str] = {
    "welcome": WELCOME_TEXT,
    "ask_vertical": ASK_VERTICAL,
    "ask_vertical_other": ASK_VERTICAL_OTHER,
    "ask_grade": ASK_GRADE,
    "ask_investor_type": ASK_INVESTOR_TYPE,
    "ask_investor_amount": ASK_INVESTOR_AMOUNT,
    "ask_investor_needs": ASK_INVESTOR_NEEDS,
    "ask_profession": ASK_PROFESSION,
    "ask_profession_other": ASK_PROFESSION_OTHER,
    "ask_request": ASK_REQUEST,
    "ask_name": ASK_NAME,
    "ask_country": ASK_COUNTRY,
    "ask_company": ASK_COMPANY,
    "ask_linkedin": ASK_LINKEDIN,
    "final": FINAL_TEXT,
    "media_kit_caption": MEDIA_KIT_CAPTION,
    "banned_notice": BANNED_NOTICE_TEXT,
    "lang_select": LANG_SELECT_TEXT,
    "welcome_en": WELCOME_TEXT_EN,
    "ask_vertical_en": ASK_VERTICAL_EN,
    "ask_vertical_other_en": ASK_VERTICAL_OTHER_EN,
    "ask_grade_en": ASK_GRADE_EN,
    "ask_investor_type_en": ASK_INVESTOR_TYPE_EN,
    "ask_investor_amount_en": ASK_INVESTOR_AMOUNT_EN,
    "ask_investor_needs_en": ASK_INVESTOR_NEEDS_EN,
    "ask_profession_en": ASK_PROFESSION_EN,
    "ask_profession_other_en": ASK_PROFESSION_OTHER_EN,
    "ask_request_en": ASK_REQUEST_EN,
    "ask_name_en": ASK_NAME_EN,
    "ask_country_en": ASK_COUNTRY_EN,
    "ask_company_en": ASK_COMPANY_EN,
    "ask_linkedin_en": ASK_LINKEDIN_EN,
    "final_en": FINAL_TEXT_EN,
    "media_kit_caption_en": MEDIA_KIT_CAPTION_EN,
    "banned_notice_en": BANNED_NOTICE_TEXT_EN,
    "captcha_welcome": CAPTCHA_WELCOME_TEXT,
    "captcha_success": CAPTCHA_SUCCESS_TEXT,
    "gate_prompt": GATE_PROMPT_TEXT,
    "group_greeting": GROUP_GREETING_TEXT_RU,
    "group_greeting_en": GROUP_GREETING_TEXT_EN,
}

# Список текстов для админ-каталога: (ключ, человекочитаемая подпись)
TEXT_CATALOG: tuple[tuple[str, str], ...] = (
    ("lang_select", "Выбор языка (первый экран)"),
    ("welcome", "Приветствие (блок 1)"),
    ("ask_vertical", "Вопрос: вертикаль (блок 2)"),
    ("ask_vertical_other", "Вертикаль: своё описание"),
    ("ask_grade", "Вопрос: грейд"),
    ("ask_investor_type", "Инвестор: тип"),
    ("ask_investor_amount", "Инвестор: суммы"),
    ("ask_investor_needs", "Инвестор: что ищет"),
    ("ask_profession", "Вопрос: должность"),
    ("ask_profession_other", "Должность: своё описание"),
    ("ask_request", "Вопрос: что актуально (блок 3)"),
    ("ask_name", "Вопрос: имя (блок 4)"),
    ("ask_country", "Вопрос: страна"),
    ("ask_company", "Вопрос: компания (блок 5)"),
    ("ask_linkedin", "Вопрос: LinkedIn (блок 6)"),
    ("final", "Финал (блок 7)"),
    ("media_kit_caption", "Финал: подпись к медиакиту (PDF перед инвайтом)"),
    ("banned_notice", "Финал: юзер забанен админом (доступ не открыт)"),
    ("captcha_welcome", "Приветствие в группе (текст + видео + кнопки)"),
    ("gate_prompt", "Гейт: мут до анкеты (просьба пройти)"),
    ("group_greeting", "Приветствие в группе ПОСЛЕ анкеты — RU (по анкете на русском)"),
    ("group_greeting_en", "EN: Приветствие в группе ПОСЛЕ анкеты (анкета на английском)"),
    ("welcome_en", "EN: Приветствие (блок 1)"),
    ("ask_vertical_en", "EN: Вопрос: вертикаль"),
    ("ask_vertical_other_en", "EN: Вертикаль: своё описание"),
    ("ask_grade_en", "EN: Вопрос: грейд"),
    ("ask_investor_type_en", "EN: Инвестор: тип"),
    ("ask_investor_amount_en", "EN: Инвестор: суммы"),
    ("ask_investor_needs_en", "EN: Инвестор: что ищет"),
    ("ask_profession_en", "EN: Вопрос: должность"),
    ("ask_profession_other_en", "EN: Должность: своё описание"),
    ("ask_request_en", "EN: Вопрос: что актуально"),
    ("ask_name_en", "EN: Вопрос: имя"),
    ("ask_country_en", "EN: Вопрос: страна"),
    ("ask_company_en", "EN: Вопрос: компания"),
    ("ask_linkedin_en", "EN: Вопрос: LinkedIn"),
    ("final_en", "EN: Финал"),
    ("media_kit_caption_en", "EN: Финал: подпись к медиакиту"),
    ("banned_notice_en", "EN: Финал: юзер забанен админом"),
)
