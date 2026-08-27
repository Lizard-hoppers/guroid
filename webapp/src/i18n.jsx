import { createContext, useContext, useState } from "react";

// Двуязычность приложения (12.08.2026, по просьбе владельца — переключатель
// в правом верхнем углу). Лёгкая самодельная реализация, без библиотек —
// приложение небольшое, полноценный i18n-фреймворк был бы избыточен.
// Дефолт ВСЕГДА "ru" (не читаем Telegram language_code) — сообщество
// русскоязычное, плюс это делает поведение предсказуемым для тестов
// (headless-смоук кликает по кнопкам с русским текстом).
const STORAGE_KEY = "guro_id_lang";

export function readStoredLang() {
  try {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    return saved === "en" ? "en" : "ru";
  } catch {
    return "ru";
  }
}

function writeStoredLang(lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // приватный режим/недоступен localStorage — просто не переживёт перезаход
  }
}

// key -> { ru, en }. Плоский namespace "экран.элемент" вместо вложенных
// объектов — проще искать/добавлять по ходу разработки.
const STRINGS = {
  "app.subtitle": { ru: "Ваш рабочий рейтинг в индустрии", en: "Your professional rating in the industry" },

  "tab.profile": { ru: "Профиль", en: "Profile" },
  "tab.search": { ru: "Поиск", en: "Search" },
  "tab.confirm": { ru: "Сделки", en: "Deals" },
  "tab.subscribe": { ru: "Подписка", en: "Subscribe" },

  "common.back": { ru: "‹ Профиль", en: "‹ Profile" },
  "common.backToMessages": { ru: "‹ Сообщения", en: "‹ Messages" },
  "common.backToPersonal": { ru: "‹ Личный профиль", en: "‹ Personal profile" },
  "common.noName": { ru: "Без имени", en: "No name" },
  "common.hidden": { ru: "Скрыто", en: "Hidden" },
  "common.save": { ru: "Сохранить", en: "Save" },
  "common.cancel": { ru: "Отмена", en: "Cancel" },
  "common.saving": { ru: "Сохраняем…", en: "Saving…" },
  "common.edit": { ru: "Изменить", en: "Edit" },
  "common.fill": { ru: "Заполнить", en: "Fill in" },
  "common.notFilled": { ru: "не заполнено", en: "not filled in" },
  "common.saveError": { ru: "Не получилось сохранить. Попробуйте ещё раз.", en: "Couldn't save. Please try again." },
  "common.errorGeneric": { ru: "Ошибка. Попробуйте позже.", en: "Something went wrong. Please try again later." },
  "common.yes": { ru: "Да", en: "Yes" },
  "common.no": { ru: "Нет", en: "No" },
  "common.notSpecified": { ru: "Не указано", en: "Not specified" },
  "common.delete": { ru: "Удалить", en: "Delete" },

  "workspace.personal": { ru: "Личный", en: "Personal" },
  "workspace.recruiter": { ru: "Рекрутер", en: "Recruiter" },
  "workspace.company": { ru: "Компания", en: "Company" },

  // --- Профиль / хаб ---
  "hub.status": { ru: "Статус", en: "Status" },
  "hub.addToHome": { ru: "Добавить на экран телефона", en: "Add to home screen" },
  "hub.menu.rating": { ru: "Мой рейтинг", en: "My rating" },
  "hub.menu.cv": { ru: "Моё CV", en: "My CV" },
  "hub.menu.contacts": { ru: "Мои контакты", en: "My contacts" },
  "hub.menu.offers": { ru: "Мои офферы", en: "My offers" },
  "hub.menu.messages": { ru: "Мои сообщения", en: "My messages" },
  "hub.menu.qr": { ru: "Мой QR", en: "My QR" },
  "hub.ratingLocked": { ru: "🔒", en: "🔒" },
  "hub.dealsConfirmed": { ru: "{count} подтверждённых сделок", en: "{count} confirmed deals" },
  "hub.dealsLocked": { ru: "Сделки скрыты", en: "Deals hidden" },
  "hub.lowRatingHint": { ru: "У вас низкий рейтинг в индустрии", en: "Your industry rating is low" },
  "hub.lowRatingCta": { ru: "Как исправить?", en: "How to fix?" },
  "hub.daysInCommunity": { ru: "В сообществе {count} {unit}", en: "{count} {unit} in the community" },
  "hub.privacyHint": {
    ru: "Эти поля видны в вашей визитке тем, кто ищет вас в GURO ID. По умолчанию скрыты — включите то, что хотите показать.",
    en: "These fields are visible on your card to people searching for you in GURO ID. Hidden by default — turn on what you want to show.",
  },

  "workStatus.looking": { ru: "Ищу работу", en: "Open to work" },
  "workStatus.neutral": { ru: "Нейтральный", en: "Neutral" },
  "workStatus.working": { ru: "Уже работаю", en: "Employed" },

  // --- Мой рейтинг ---
  "rating.title": { ru: "Мой рейтинг", en: "My rating" },
  "rating.gateTitle": { ru: "Рейтинг и сделки скрыты", en: "Rating and deals are hidden" },
  "rating.gateText": {
    ru: "Без активной подписки рейтинг и история сделок не видны — ни вам, ни другим. Ничего не удалено: как только подписка возобновится, всё вернётся как было.",
    en: "Without an active subscription your rating and deal history aren't visible — not to you, not to others. Nothing is deleted: as soon as the subscription is renewed, everything comes back.",
  },
  "rating.subscribeCta": { ru: "Оформить подписку", en: "Subscribe" },
  "rating.helpToggle": { ru: "Как поднять рейтинг?", en: "How do I raise my rating?" },
  "rating.helpHide": { ru: "Скрыть", en: "Hide" },
  "rating.help1": {
    ru: "Рейтинг — это сколько людей подтвердило успешные сделки с вами. У кого высокий рейтинг — с тем человеком меньше рисков попасть на деньги.",
    en: "Rating shows how many people confirmed successful deals with you. The higher the rating, the lower the risk of getting scammed by that person.",
  },
  "rating.help2": { ru: "Рейтинг формируется от сделок и найма.", en: "Rating is built from deals and hires." },
  "rating.help3": {
    ru: "Вы и ваш партнёр, с которым уже была успешная сделка, добавляете друг друга по кнопке «Подтвердить партнёрство» во вкладке «Сделки». Чем больше успешных сделок или наймов подтверждено — тем выше рейтинг и тем охотнее люди из индустрии пойдут с вами на контакт. Можно добавить всех, с кем вы работали ещё до появления GURO ID.",
    en: "You and your partner, once you've had a successful deal, confirm each other via the \"Confirm partnership\" button on the Deals tab. The more confirmed deals or hires — the higher your rating, and the more willing people in the industry are to reach out. You can add everyone you worked with before GURO ID existed.",
  },
  "rating.partnershipsTitle": { ru: "Партнёрства", en: "Partnerships" },
  "rating.emptyOwn": {
    ru: "Пока нет подтверждённых партнёрств. Отметьте сотрудничество во вкладке «Сделки».",
    en: "No confirmed partnerships yet. Mark a collaboration on the Deals tab.",
  },
  "rating.emptyOther": { ru: "Пока нет подтверждённых партнёрств.", en: "No confirmed partnerships yet." },
  "rating.privacyHint": {
    ru: "Управляет тем, что видят чужие при поиске вас. Партнёрства видны всем ЧУЖИМ всегда (это ядро смысла GURO ID) — при условии, что у вас активна подписка (см. выше).",
    en: "Controls what strangers see when they find you. Partnerships are ALWAYS visible to others (that's the whole point of GURO ID) — provided your subscription is active (see above).",
  },
  "rating.otherHistoryTitle": { ru: "История партнёрств контрагента", en: "Counterparty's partnership history" },
  "metric.rating": { ru: "Рейтинг", en: "Rating" },
  "metric.partnerships": { ru: "Партнёрств", en: "Partnerships" },
  "metric.daysInCommunity": { ru: "Дней в комьюнити", en: "Days in community" },
  "partner.amountReceived": { ru: "Получено", en: "Received" },
  "partner.amountPaid": { ru: "Оплачено", en: "Paid" },
  "partner.amountNote": { ru: "(со слов инициатора)", en: "(as stated by the initiator)" },
  // Атрибуция оффера/отзыва (25.08.2026, баг "Пофиксить.pdf" — офер/отзыв
  // писал инициатор о СЕБЕ, но отображалось безлико под именем контрагента).
  "partner.wordsOf": { ru: "Слова {name}", en: "{name}'s words" },
  "partner.wordsYours": { ru: "Ваши слова", en: "Your words" },
  "partner.wordsInitiator": { ru: "Слова инициатора", en: "Initiator's words" },
  "partner.notRated": { ru: "не влияет на рейтинг", en: "doesn't affect rating" },
  "partner.txHash": { ru: "Хэш транзакции", en: "Transaction hash" },
  "partner.txVerified": { ru: "подтверждено ончейн", en: "verified on-chain" },
  "rating.ratePrompt": { ru: "Как прошло сотрудничество?", en: "How did the collaboration go?" },
  "rating.verdict.success": { ru: "Успешно", en: "Success" },
  "rating.verdict.nuance": { ru: "Были нюансы", en: "Had nuances" },
  "rating.verdict.problematic": { ru: "Проблемная сделка", en: "Problematic deal" },
  "rating.commentPlaceholder": { ru: "Что именно произошло (необязательно)", en: "What happened (optional)" },
  "rating.commentSubmit": { ru: "Отправить оценку", en: "Submit rating" },
  "rating.myRating": { ru: "Ваша оценка", en: "Your rating" },
  "rating.editLink": { ru: "изменить", en: "edit" },
  "rating.deleteLink": { ru: "удалить", en: "delete" },
  "rating.otherRating": { ru: "Оценка контрагента", en: "Counterparty's rating" },
  "rating.error": { ru: "Не получилось отправить оценку.", en: "Couldn't submit the rating." },

  // --- Моё CV ---
  "cv.title": { ru: "Моё CV", en: "My CV" },
  // «Характеристика» (26.08.2026) — кнопка в каждом профиле, доступная
  // любому подписчику: офферы ("Я ищу"/"Я полезен") + CV просматриваемого.
  "characteristic.button": { ru: "🪪 Характеристика", en: "🪪 Characteristic" },
  "characteristic.hide": { ru: "Скрыть характеристику", en: "Hide characteristic" },
  "characteristic.offersTitle": { ru: "Офферы", en: "Offers" },
  "characteristic.emptyOffers": { ru: "Офферы не заполнены.", en: "No offers filled in." },
  "cv.viewBtn": { ru: "👁 Посмотреть моё CV", en: "👁 View my CV" },
  "cv.backToEdit": { ru: "‹ К редактированию", en: "‹ Back to editing" },
  "cv.shareBtn": { ru: "📤 Поделиться CV", en: "📤 Share CV" },
  "cv.shareBusy": { ru: "Готовим ссылку…", en: "Preparing link…" },
  "cv.shareError": { ru: "Не получилось создать ссылку, попробуйте ещё раз", en: "Couldn't create the link, try again" },
  "cv.shareText": {
    ru: "Посмотрите моё CV в GURO ID",
    en: "Check out my CV on GURO ID",
  },
  "cv.label": { ru: "Опыт и навыки", en: "Experience and skills" },
  "cv.placeholder": {
    ru: "Например: 5 лет в iGaming, руководил командой из 10 человек…",
    en: "E.g.: 5 years in iGaming, led a team of 10 people…",
  },
  "cv.privacyHint": {
    ru: "Пока выключено — CV не видно тем, кто ищет вас в GURO ID.",
    en: "While off — your CV isn't visible to people searching for you in GURO ID.",
  },
  "cv.profession.label": { ru: "Должность", en: "Position" },
  "cv.profession.required": { ru: "Укажите должность", en: "Enter a position" },
  "cv.profession.limitHint": {
    ru: "Можно менять не чаще 2 раз в год",
    en: "Can be changed no more than 2 times per year",
  },
  "cv.profession.limitReached": {
    ru: "Лимит смен должности на этот год исчерпан (не более 2 раз в год).",
    en: "You've reached the position-change limit for this year (max 2 per year).",
  },
  "cv.verticals.title": { ru: "Вертикали", en: "Verticals" },
  "cv.grade.title": { ru: "Грейд", en: "Seniority level" },
  "cv.grade.placeholder": { ru: "Не выбрано", en: "Not selected" },
  "cv.location.label": { ru: "Локация", en: "Location" },
  "cv.location.placeholder": { ru: "Например: Одесса, Украина", en: "E.g.: Odesa, Ukraine" },
  "cv.relocation.title": { ru: "Готовность к релокации", en: "Ready to relocate" },
  "cv.polygraph.title": { ru: "Согласие на полиграф", en: "Consent to polygraph" },
  "cv.salary.title": { ru: "Зарплатные ожидания", en: "Salary expectations" },
  "cv.salary.fromPlaceholder": { ru: "От, $", en: "From, $" },
  "cv.salary.toPlaceholder": { ru: "До, $", en: "To, $" },
  "cv.salary.negotiableLabel": { ru: "По договорённости", en: "Negotiable" },
  "cv.skills.title": { ru: "Навыки и технологии", en: "Skills & technologies" },
  "cv.skills.label": { ru: "Ключевые навыки", en: "Key skills" },
  "cv.skills.placeholder": { ru: "Например: Python, аналитика, продажи…", en: "E.g.: Python, analytics, sales…" },
  "cv.languages.label": { ru: "Языки", en: "Languages" },
  "cv.languages.placeholder": { ru: "Например: русский, английский B2", en: "E.g.: Russian, English B2" },
  "cv.certifications.label": { ru: "Сертификаты", en: "Certifications" },
  "cv.certifications.placeholder": { ru: "Например: iGaming School", en: "E.g.: iGaming School" },
  "cv.experience.title": { ru: "Опыт работы", en: "Work experience" },
  "cv.experience.empty": { ru: "Пока не добавлено ни одного места работы.", en: "No work experience added yet." },
  "cv.experience.present": { ru: "сейчас", en: "present" },
  "cv.experience.addBtn": { ru: "+ Добавить опыт", en: "+ Add experience" },
  "cv.experience.limitReached": {
    ru: "Достигнут лимит записей об опыте работы.",
    en: "You've reached the work experience entry limit.",
  },
  "cv.experience.form.title": { ru: "Новое место работы", en: "New work experience" },
  "cv.experience.form.required": {
    ru: "Укажите компанию и должность",
    en: "Enter company and position",
  },
  "cv.experience.form.companyLabel": { ru: "Компания", en: "Company" },
  "cv.experience.form.companyPlaceholder": { ru: "Название компании", en: "Company name" },
  "cv.experience.form.positionLabel": { ru: "Должность", en: "Position" },
  "cv.experience.form.positionPlaceholder": { ru: "Например: Head of Marketing", en: "E.g.: Head of Marketing" },
  "cv.experience.form.datesLabel": { ru: "Период работы", en: "Employment period" },
  "cv.experience.form.dateFromPlaceholder": { ru: "С (напр. 2020)", en: "From (e.g. 2020)" },
  "cv.experience.form.dateToPlaceholder": { ru: "По (напр. 2023 или сейчас)", en: "To (e.g. 2023 or present)" },
  "cv.experience.form.locationLabel": { ru: "Локация", en: "Location" },
  "cv.experience.form.locationPlaceholder": { ru: "Город, страна", en: "City, country" },
  "cv.experience.form.descriptionLabel": { ru: "Обязанности", en: "Responsibilities" },
  "cv.experience.form.descriptionPlaceholder": {
    ru: "Чем занимались на этой позиции",
    en: "What you did in this role",
  },

  // --- Мои офферы ---
  "offers.title": { ru: "Мои офферы", en: "My offers" },
  "offers.lookingForLabel": { ru: "Я ищу", en: "I'm looking for" },
  "offers.lookingForPlaceholder": {
    ru: "Например: ищу трафик на GB, CA, ES…",
    en: "E.g.: looking for traffic on GB, CA, ES…",
  },
  "offers.offeringLabel": { ru: "Я полезен", en: "I can offer" },
  "offers.offeringPlaceholder": {
    ru: "Например: могу подключить трафик, есть база рекламодателей…",
    en: "E.g.: can connect traffic, have an advertiser base…",
  },
  "offers.privacyHint": {
    ru: "Управляет показом обоих полей разом — «ищу» и «полезен».",
    en: "Controls visibility of both fields at once — \"looking for\" and \"can offer\".",
  },

  // --- Мои контакты ---
  "contacts.title": { ru: "Мои контакты", en: "My contacts" },
  "contacts.telegram": { ru: "Telegram", en: "Telegram" },
  "contacts.linkedinEmpty": { ru: "LinkedIn не указан в анкете", en: "LinkedIn not specified in the questionnaire" },
  "contacts.websiteLabel": { ru: "Сайт", en: "Website" },
  "contacts.showQr": { ru: "Показать мой QR (визитка)", en: "Show my QR (business card)" },
  "contacts.inviteBtn": { ru: "🔗 Пригласить коллегу", en: "🔗 Invite a colleague" },
  "contacts.inviteBusy": { ru: "Готовим ссылку…", en: "Preparing link…" },
  "contacts.inviteError": { ru: "Не удалось получить ссылку. Попробуйте ещё раз.", en: "Couldn't get the link. Please try again." },
  "contacts.inviteShareText": {
    ru: "Присоединяйся к Private Gambling Community через GURO ID",
    en: "Join Private Gambling Community via GURO ID",
  },
  "contacts.privacyHint": {
    ru: "Управляет показом LinkedIn и сайта. Telegram виден всегда — иначе вас не найти в поиске.",
    en: "Controls visibility of LinkedIn and website. Telegram is always visible — otherwise you couldn't be found in search.",
  },

  // --- Мой QR ---
  "qr.title": { ru: "Мой QR", en: "My QR" },
  "qr.preparing": { ru: "Готовим QR…", en: "Preparing QR…" },
  "qr.error": { ru: "Не удалось получить QR. Попробуйте позже.", en: "Couldn't get the QR. Please try again later." },
  "qr.hint": {
    ru: "Покажите этот код — сканирующий откроет ваш профиль в GURO ID через бота. Полную карточку увидят только с активной подпиской.",
    en: "Show this code — the person scanning it will open your GURO ID profile via the bot. Only viewers with an active subscription see the full card.",
  },

  // --- Мои сообщения ---
  "messages.title": { ru: "Мои сообщения", en: "My messages" },
  "messages.loading": { ru: "Загружаем…", en: "Loading…" },
  "messages.loadError": { ru: "Не удалось загрузить сообщения.", en: "Couldn't load messages." },
  "messages.empty": {
    ru: "Пока нет переписок. Найдите человека во вкладке «Поиск» и напишите ему.",
    en: "No conversations yet. Find someone on the Search tab and message them.",
  },
  "thread.loading": { ru: "Загружаем переписку…", en: "Loading conversation…" },
  "thread.loadError": { ru: "Не удалось открыть переписку.", en: "Couldn't open the conversation." },
  "thread.emptyCanSend": { ru: "Переписки пока нет — напишите первое сообщение.", en: "No messages yet — send the first one." },
  "thread.emptyCannotSend": {
    ru: "Написать первым можно только тем, чей профиль вы открыли по подписке GURO ID.",
    en: "You can message first only people whose profile you've unlocked with a GURO ID subscription.",
  },
  "thread.placeholder": { ru: "Сообщение…", en: "Message…" },
  "thread.send": { ru: "Отправить", en: "Send" },
  "thread.sending": { ru: "Отправляем…", en: "Sending…" },
  "thread.error.SUBSCRIPTION_REQUIRED": {
    ru: "Чтобы написать первым, нужна активная подписка GURO ID — вы уже видели полный профиль этого человека, если общаетесь впервые.",
    en: "You need an active GURO ID subscription to message first — you must have already seen this person's full profile.",
  },
  "thread.error.RATE_LIMITED": {
    ru: "Слишком много новых переписок за сегодня. Попробуйте завтра.",
    en: "Too many new conversations today. Please try again tomorrow.",
  },
  "thread.error.NO_RECIPIENT_PROFILE": {
    ru: "Этот пользователь ещё не проходил анкету бота.",
    en: "This user hasn't completed the bot's questionnaire yet.",
  },
  "thread.error.EMPTY_BODY": { ru: "Сообщение не может быть пустым.", en: "Message can't be empty." },
  "thread.error.generic": { ru: "Не получилось отправить сообщение.", en: "Couldn't send the message." },
  "messageBtn": { ru: "✉️ Написать", en: "✉️ Message" },
  "recruiterViewBtn": { ru: "🧑‍💼 Посмотреть как рекрутера", en: "🧑‍💼 View as recruiter" },
  "companyViewBtn": { ru: "🏢 Посмотреть как компанию", en: "🏢 View as company" },

  // --- Онбординг ---
  "onboarding.title": { ru: "Это ваша ID-карта", en: "This is your ID card" },
  "onboarding.intro": { ru: "Для загрузки CV, поиска работы, кандидатов и партнёров. А также есть рейтинг подтверждённых сделок и найма.", en: "For uploading a CV, finding jobs, candidates and partners. Plus a rating of confirmed deals and hires." },
  "onboarding.more": { ru: "Подробнее", en: "Learn more" },
  "onboarding.detail1": { ru: "Вы платите за то, чтобы быть всегда сразу в 7 вертикалях:", en: "You pay to always be present across 7 verticals at once:" },
  "onboarding.detail2": {
    ru: "У вас появится специальная ID-карта. Каждый раз, когда у вас будет успешная сделка или найм, ваш партнёр подтверждает это — и на основании этого у вас будет рейтинг. Вам достаточно отправить свой юзернейм любому участнику индустрии: он, перейдя в ваш профиль, увидит, что с вами сотрудничали разные люди, были успешные сделки, найм.",
    en: "You'll get a personal ID card. Every time you have a successful deal or hire, your partner confirms it — and that builds your rating. Just send your username to anyone in the industry: opening your profile, they'll see that different people worked with you, with real deals and hires behind it.",
  },
  "onboarding.detail3": { ru: "Также вы сможете загрузить своё резюме и найти работу. Функционал будет увеличиваться.", en: "You'll also be able to upload your resume and find a job. More features are coming." },
  "onboarding.detail4": {
    ru: "При отсутствии активной подписки ваш рейтинг в индустрии скрывается — сотни сделок и успешных наймов пропадают из виду (сами данные не удаляются: как только подписка возобновится, всё вернётся как было).",
    en: "Without an active subscription your industry rating is hidden — hundreds of deals and successful hires disappear from view (the data itself isn't deleted: as soon as the subscription is renewed, everything comes back).",
  },
  "onboarding.priceLine": { ru: "Подписка: {monthly}/месяц или {yearly}/год (в звёздах — 650⭐ / 6600⭐).", en: "Subscription: {monthly}/month or {yearly}/year (in Stars — 650⭐ / 6600⭐)." },
  "onboarding.ctaHint": {
    ru: "Чтобы начать строить репутацию и карьеру — заполните анкету. В конце у вас будет выбор, какая информация будет общедоступна, а какая нет.",
    en: "To start building your reputation and career — fill in the questionnaire. At the end you'll choose what information is public and what isn't.",
  },
  "onboarding.ctaBtn": { ru: "Заполнить анкету в боте", en: "Fill in the questionnaire in the bot" },

  // --- Поиск ---
  "search.title": { ru: "Поиск", en: "Search" },
  // 25.08.2026 (фидбек владельца, "Правки.pdf"): поиск по описанию убран из
  // личного профиля — тут только точный юзернейм. Описание/параметры/резюме —
  // теперь функционал кабинетов Рекрутер/Компания (см. search.cabinetsHint).
  "search.hint": { ru: "Точный поиск по юзернейму участника.", en: "Exact search by a member's username." },
  "search.placeholder": { ru: "Юзернейм", en: "Username" },
  "search.submit": { ru: "Найти", en: "Search" },
  "search.submitting": { ru: "Ищем…", en: "Searching…" },
  "search.cabinetsHint": {
    ru: "Чтобы находить резюме по категориям, профессиям и навыкам — активируйте кабинет «Рекрутер». А чтобы находить клиентов, кандидатов и представлять бренд — активируйте кабинет «Компания».",
    en: "To find résumés by category, profession or skill — activate the Recruiter cabinet. To find clients, candidates and represent a brand — activate the Company cabinet.",
  },
  "search.demoLabel": { ru: "Демо версия", en: "Demo version" },
  "search.browseHint": { ru: "Или посмотрите по вертикали, если не знаете юзернейм (по подписке):", en: "Or browse by vertical if you don't know the username (subscription required):" },
  "search.paywallTitle": { ru: "Поиск по вертикалям — по подписке", en: "Vertical search — subscription only" },
  "search.paywallText": { ru: "Без подписки доступен только точный поиск по юзернейму.", en: "Without a subscription only exact username search is available." },
  "search.notFound": { ru: "Такой участник не найден в GURO ID.", en: "No such member found in GURO ID." },
  "search.genericError": { ru: "Ошибка поиска.", en: "Search error." },
  "search.viewLimitReached": {
    ru: "Дневной лимит просмотров профилей исчерпан. Обновится {date}.",
    en: "Daily profile view limit reached. Resets on {date}.",
  },
  "search.topToggle": { ru: "🏆 Сначала высокий рейтинг", en: "🏆 Highest rating first" },
  "search.emptyList": { ru: "Ничего не нашлось. Попробуйте другое описание или вертикаль.", en: "Nothing found. Try another description or vertical." },
  "search.truncated": { ru: "Показаны не все совпадения — уточните запрос.", en: "Not all matches shown — refine your query." },
  "search.resumesToggle": {
    ru: "🎯 Только те, кто ищет работу (для вертикалей выше и кнопки ниже)",
    en: "🎯 Only people looking for work (applies to verticals above and the button below)",
  },
  "search.resumesShowAll": { ru: "Показать всех, кто ищет работу", en: "Show everyone looking for work" },
  "identity.vertical": { ru: "Вертикаль: ", en: "Vertical: " },
  "identity.company": { ru: "Компания: ", en: "Company: " },
  "recruiterCard.company": { ru: "Компания: ", en: "Company: " },
  "recruiterCard.vertical": { ru: "Вертикаль: ", en: "Vertical: " },
  "recruiterCard.profession": { ru: "Должность: ", en: "Position: " },
  "recruiterCard.website": { ru: "Сайт: ", en: "Website: " },
  "recruiterCard.offering": { ru: "Чем полезен: ", en: "Can offer: " },
  "companyCard.vertical": { ru: "Вертикаль: ", en: "Vertical: " },
  "companyCard.website": { ru: "Сайт: ", en: "Website: " },

  // --- Подтвердить партнёрство ---
  "confirm.title": { ru: "Подтвердить партнёрство", en: "Confirm partnership" },
  // Кабинет "Рекрутер" (26.08.2026, ТЗ раздел 4) — переименование экрана,
  // тип партнёрства тут жёстко "Найм", переключатель скрыт.
  "confirm.title.hire": { ru: "Подтвердить найм", en: "Confirm a hire" },
  "confirm.asCompanyHint": {
    ru: "✓ Вы действуете от лица компании — сделка попадёт в общую историю бренда.",
    en: "✓ You're acting on behalf of the company — the deal will go into the brand's shared history.",
  },
  "confirm.hint": {
    ru: "Укажите юзернейм человека, с которым уже состоялось сотрудничество. Ему придёт запрос на подтверждение от бота — запись появится в профилях обоих только после его ответа. Офер и отзыв видны всем чужим (в этом и смысл — проверить репутацию контакта), суммы — только если включите показ ниже.",
    en: "Enter the username of someone you've already worked with. They'll get a confirmation request from the bot — the record appears in both profiles only after they respond. The offer and review are visible to everyone (that's the point — checking a contact's reputation), amounts only if you enable showing them below.",
  },
  "confirm.usernameLabel": { ru: "Юзернейм контрагента", en: "Counterparty's username" },
  "confirm.usernamePlaceholder": { ru: "Например: @username", en: "E.g.: @username" },
  "confirm.ptypeLabel": { ru: "Тип партнёрства", en: "Partnership type" },
  "confirm.ptype.deal": { ru: "Сделка", en: "Deal" },
  "confirm.ptype.hire": { ru: "Найм", en: "Hire" },
  "confirm.verticalLabel": { ru: "Вертикаль (необязательно)", en: "Vertical (optional)" },
  "confirm.geoLabel": { ru: "Гео (необязательно)", en: "Geo (optional)" },
  "confirm.geoPlaceholder": { ru: "Одесса, Кипр…", en: "Odesa, Cyprus…" },
  "confirm.offerLabel": { ru: "Оффер — суть сделки (необязательно)", en: "Offer — deal summary (optional)" },
  "confirm.offerPlaceholder": { ru: "Например: привёл байера на казино-трафик", en: "E.g.: brought in a buyer for casino traffic" },
  "confirm.amountLabel": { ru: "Сумма (необязательно)", en: "Amount (optional)" },
  "confirm.amountReceivedPlaceholder": { ru: "Я получил, $", en: "I received, $" },
  "confirm.amountPaidPlaceholder": { ru: "Я заплатил, $", en: "I paid, $" },
  "confirm.amountVisible": { ru: "Показывать сумму чужим (по умолчанию скрыта)", en: "Show amount to others (hidden by default)" },
  "confirm.txHashLabel": { ru: "Хэш транзакции (необязательно)", en: "Transaction hash (optional)" },
  "confirm.txHashPlaceholder": { ru: "Например: 0x71c4…e9a3", en: "E.g.: 0x71c4…e9a3" },
  "confirm.txHashHint": {
    ru: "Подтверждает реальность перевода. Виден вместе с суммой — по той же галочке выше.",
    en: "Backs up the transfer as real. Shown together with the amount — same checkbox above.",
  },
  "confirm.txNetworkLabel": { ru: "Сеть транзакции", en: "Transaction network" },
  "confirm.txNetworkPlaceholder": { ru: "Выберите сеть…", en: "Select network…" },
  "confirm.submit": { ru: "Отправить на подтверждение", en: "Send for confirmation" },
  "confirm.submitting": { ru: "Отправляем…", en: "Sending…" },
  "confirm.sentOk": { ru: "Заявка отправлена. Ждём подтверждения от контрагента.", en: "Request sent. Waiting for the counterparty to confirm." },
  "confirm.error.SELF_PARTNERSHIP": { ru: "Нельзя подтвердить партнёрство с самим собой.", en: "You can't confirm a partnership with yourself." },
  "confirm.error.RATE_LIMITED": { ru: "Заявка с этим человеком уже отправлялась за последние 24 часа.", en: "A request to this person was already sent in the last 24 hours." },
  "confirm.error.NO_CONFIRMER_PROFILE": {
    ru: "Этот пользователь ещё не проходил анкету @GamblingCommunitybot — бот не может ему написать.",
    en: "This user hasn't filled in the @GamblingCommunitybot questionnaire yet — the bot can't message them.",
  },
  "confirm.error.generic": { ru: "Не получилось отправить заявку.", en: "Couldn't send the request." },
  "confirm.error.DAILY_REQUEST_LIMIT_REACHED": {
    ru: "Дневной лимит новых заявок исчерпан. Обновится {date}.",
    en: "Daily limit of new requests reached. Resets on {date}.",
  },

  // --- Подписка ---
  "subscribe.titleGuro": { ru: "Подписка GURO ID", en: "GURO ID subscription" },
  "subscribe.titleRecruiter": { ru: "Подписка на кабинет рекрутера", en: "Recruiter cabinet subscription" },
  "subscribe.titleCompany": { ru: "Подписка на кабинет компании", en: "Company cabinet subscription" },
  "subscribe.active": { ru: "Подписка активна", en: "Subscription active" },
  "subscribe.activeUntil": { ru: " до {date}", en: " until {date}" },
  "subscribe.hintGuro": {
    ru: "Без активной подписки ваш рейтинг и история сделок скрыты — ни вам, ни другим (данные не удаляются, подписка просто держит их видимыми). Полный поиск и просмотр чужих профилей — тоже по подписке.",
    en: "Without an active subscription your rating and deal history are hidden — not to you, not to others (data isn't deleted, the subscription just keeps it visible). Full search and viewing other profiles also require a subscription.",
  },
  "subscribe.hintRecruiter": {
    ru: "Кабинет рекрутера — отдельная подписка поверх базовой GURO ID: своя витрина (имя/компания/CV), не влияет на личный профиль. Рейтинг и партнёрства остаются общими.",
    en: "The recruiter cabinet is a separate subscription on top of the base GURO ID: its own showcase (name/company/CV), doesn't affect your personal profile. Rating and partnerships stay shared.",
  },
  "subscribe.compare.workStatus": { ru: "Статус трудоустройства (виден всем)", en: "Employment status (visible to everyone)" },
  "subscribe.compare.rating": { ru: "Ваш рейтинг и история сделок/найма", en: "Your rating and deal/hire history" },
  "subscribe.compare.search": { ru: "Полный поиск по юзернейму", en: "Full username search" },
  "subscribe.compare.history": { ru: "История партнёрств контрагента", en: "Counterparty's partnership history" },
  "subscribe.compareRecruiter.rating": { ru: "Рейтинг и партнёрства (общие с личным профилем)", en: "Rating and partnerships (shared with personal profile)" },
  "subscribe.compareRecruiter.showcase": { ru: "Отдельная витрина: имя/компания/CV рекрутера", en: "Separate showcase: recruiter name/company/CV" },
  "subscribe.compareRecruiter.visibility": { ru: "Видимость витрины другим участникам GURO ID", en: "Showcase visibility to other GURO ID members" },
  "subscribe.hintCompany": {
    ru: "Кабинет компании — отдельная подписка поверх базовой GURO ID: бренд-страница работодателя (логотип/описание/сайт), не связана с кабинетом рекрутера. Публикация вакансий остаётся у кабинета рекрутера.",
    en: "The company cabinet is a separate subscription on top of the base GURO ID: an employer brand page (logo/description/website), unrelated to the recruiter cabinet. Vacancy publishing stays with the recruiter cabinet.",
  },
  "subscribe.compareCompany.brand": { ru: "Бренд-страница компании", en: "Company brand page" },
  "subscribe.compareCompany.showcase": { ru: "Логотип, описание, сайт, вертикаль", en: "Logo, description, website, vertical" },
  "subscribe.compareCompany.visibility": { ru: "Видимость витрины другим участникам GURO ID", en: "Showcase visibility to other GURO ID members" },
  // Basic/Pro (27.08.2026, ТЗ "Тарифы и лимиты") — два тира, см. CompanyHub.jsx.
  "subscribe.titleCompanyBasic": { ru: "Подписка на кабинет компании — Basic", en: "Company cabinet subscription — Basic" },
  "subscribe.titleCompanyPro": { ru: "Подписка на кабинет компании — Pro", en: "Company cabinet subscription — Pro" },
  "subscribe.hintCompanyBasic": {
    ru: "Basic (до 5 участников команды): бренд-страница работодателя, публикация вакансий и поиск кандидатов от лица компании, до 20 активных вакансий, 30 просмотров/день на участника.",
    en: "Basic (up to 5 team members): employer brand page, posting vacancies and searching candidates as the company, up to 20 active vacancies, 30 profile views/day per member.",
  },
  "subscribe.hintCompanyPro": {
    ru: "Pro (до 15-20 участников команды): то же самое, что Basic, с увеличенными лимитами — до 50 активных вакансий, 50 просмотров/день на участника.",
    en: "Pro (up to 15-20 team members): same as Basic with higher limits — up to 50 active vacancies, 50 profile views/day per member.",
  },
  "subscribe.free": { ru: "бесплатно", en: "free" },
  "subscribe.paid": { ru: "по подписке", en: "subscription only" },
  "subscribe.economy": { ru: "экономия {amount} ⭐", en: "save {amount} ⭐" },
  "subscribe.payStars": { ru: "Оформить · {price} ⭐ Telegram Stars", en: "Subscribe · {price} ⭐ Telegram Stars" },
  "subscribe.preparingInvoice": { ru: "Готовим счёт…", en: "Preparing invoice…" },
  "subscribe.payCrypto": { ru: "Оплатить {amount} {asset} (крипто)", en: "Pay {amount} {asset} (crypto)" },
  "subscribe.starsError": { ru: "Не получилось создать счёт. Попробуйте ещё раз.", en: "Couldn't create an invoice. Please try again." },
  "subscribe.cryptoError": { ru: "Не получилось создать крипто-счёт. Попробуйте ещё раз.", en: "Couldn't create a crypto invoice. Please try again." },

  // --- Кабинет рекрутера ---
  "recruiter.title": { ru: "Кабинет рекрутера", en: "Recruiter cabinet" },
  "recruiter.upsellText": {
    ru: "Отдельная витрина поверх личного профиля — своё имя, компания и CV для рабочего режима, независимо от того, что видно в личном профиле. Рейтинг и история сделок остаются общими для обоих режимов.",
    en: "A separate showcase on top of your personal profile — your own name, company and CV for work mode, independent of what's visible in your personal profile. Rating and deal history stay shared between both modes.",
  },
  "recruiter.field.name": { ru: "Имя / подпись", en: "Name / title" },
  "recruiter.field.namePlaceholder": { ru: "Например: Иван Петров, HR отдел", en: "E.g.: John Smith, HR department" },
  "recruiter.field.company": { ru: "Компания", en: "Company" },
  "recruiter.field.companyPlaceholder": { ru: "Название компании", en: "Company name" },
  "recruiter.field.vertical": { ru: "Вертикаль", en: "Vertical" },
  "recruiter.field.verticalPlaceholder": { ru: "Gambling, Crypto…", en: "Gambling, Crypto…" },
  "recruiter.field.profession": { ru: "Должность", en: "Position" },
  "recruiter.field.professionPlaceholder": { ru: "HR Manager, Talent Lead…", en: "HR Manager, Talent Lead…" },
  "recruiter.field.cv": { ru: "О себе / агентстве", en: "About me / agency" },
  "recruiter.field.cvPlaceholder": { ru: "Кого и как вы нанимаете", en: "Who and how you hire" },
  "recruiter.field.website": { ru: "Сайт", en: "Website" },
  "recruiter.field.websitePlaceholder": { ru: "example.com", en: "example.com" },
  "recruiter.field.offering": { ru: "Чем полезен", en: "What you offer" },
  "recruiter.field.offeringPlaceholder": { ru: "Какие вакансии/услуги предлагаете", en: "What roles/services you offer" },
  "recruiter.field.logoUrl": { ru: "Логотип (ссылка на картинку)", en: "Logo (image link)" },
  "recruiter.field.logoUrlPlaceholder": { ru: "https://…/logo.png", en: "https://…/logo.png" },
  "recruiter.privacy.name": { ru: "Имя / подпись", en: "Name / title" },
  "recruiter.privacy.company": { ru: "Компания", en: "Company" },
  "recruiter.privacy.vertical": { ru: "Вертикаль", en: "Vertical" },
  "recruiter.privacy.profession": { ru: "Должность", en: "Position" },
  "recruiter.privacy.cv": { ru: "О себе / агентстве", en: "About me / agency" },
  "recruiter.privacy.contacts": { ru: "Сайт", en: "Website" },
  "recruiter.privacy.offers": { ru: "Чем полезен", en: "What you offer" },
  "recruiter.privacyHint": {
    ru: "Управляет тем, что видят чужие в кабинете рекрутера (независимо от тумблеров личного профиля). По умолчанию скрыто — включите то, что хотите показать.",
    en: "Controls what others see in your recruiter cabinet (independent of your personal profile toggles). Hidden by default — turn on what you want to show.",
  },
  "recruiter.loading": { ru: "Загружаем кабинет рекрутера…", en: "Loading recruiter cabinet…" },
  "recruiter.loadError": { ru: "Не удалось загрузить кабинет рекрутера.", en: "Couldn't load the recruiter cabinet." },

  // Главный экран кабинета "Рекрутер" (26.08.2026, ТЗ "Гуро рекрутер каб").
  "recruiter.roleBadge": { ru: "HR / Рекрутер", en: "HR / Recruiter" },
  "recruiter.settingsBtn": { ru: "Настройки", en: "Settings" },
  "recruiter.characteristic.title": { ru: "Характеристика", en: "Characteristic" },
  "recruiter.characteristic.hires": { ru: "Успешных наймов", en: "Successful hires" },
  "recruiter.characteristic.vacancies": { ru: "Активных вакансий", en: "Active vacancies" },
  "recruiter.characteristic.responses": { ru: "Откликов за 7 дней", en: "Responses (7 days)" },
  "recruiter.characteristic.tenure": { ru: "Стаж в роли рекрутера, дней", en: "Days as recruiter" },
  "recruiter.activity.label": { ru: "Статус", en: "Status" },
  "recruiter.activity.hiring": { ru: "Активно нанимаю", en: "Actively hiring" },
  "recruiter.activity.notHiring": { ru: "Не набираю сейчас", en: "Not hiring right now" },
  "recruiter.percentile.top": { ru: "Топ-{tier}% рекрутеров", en: "Top {tier}% of recruiters" },
  "recruiter.percentile.goodText": {
    ru: "Вы входите в число самых результативных рекрутеров вертикали.",
    en: "You're among the most effective recruiters in this vertical.",
  },
  "recruiter.percentile.ctaTitle": { ru: "Поднимите рейтинг за 2 минуты", en: "Raise your rating in 2 minutes" },
  "recruiter.percentile.ctaText": {
    ru: "Подтвердите наймы, которые уже состоялись до GURO ID — это сразу увеличит ваш рейтинг.",
    en: "Confirm hires that already happened before GURO ID — this immediately raises your rating.",
  },
  "recruiter.percentile.ctaButton": { ru: "Подтвердить прошлый найм →", en: "Confirm a past hire →" },
  "recruiter.quickPublish": { ru: "+ Опубликовать вакансию", en: "+ Publish a vacancy" },
  "recruiter.quickFind": { ru: "Найти кандидата", en: "Find a candidate" },
  "recruiter.menu.messages": { ru: "Сообщения", en: "Messages" },
  "recruiter.menu.responses": { ru: "Отклики", en: "Responses" },
  "recruiter.menu.qr": { ru: "Мой QR", en: "My QR" },
  "recruiter.history.title": { ru: "История наймов", en: "Hiring history" },
  "recruiter.history.empty": { ru: "Подтверждённых наймов пока нет.", en: "No confirmed hires yet." },
  "recruiter.responses.title": { ru: "Отклики", en: "Responses" },
  "recruiter.responses.comingSoon": {
    ru: "Скоро здесь будут отклики кандидатов на ваши вакансии.",
    en: "Candidate responses to your vacancies will appear here soon.",
  },
  "recruiter.candidates.title": { ru: "Найти кандидата", en: "Find a candidate" },
  "recruiter.candidates.hint": {
    ru: "Просмотр по вертикали или среди тех, кто ищет работу.",
    en: "Browse by vertical or among those looking for work.",
  },
  "recruiter.candidates.showAllResumes": { ru: "Показать всех, кто ищет работу", en: "Show everyone looking for work" },
  "thread.viaWorkspace": { ru: "Написал(а) через кабинет: {workspace}", en: "Sent via cabinet: {workspace}" },

  // --- Кабинет "Компания" (Фаза 5, 16-17.08.2026) ---
  "company.title": { ru: "Кабинет компании", en: "Company cabinet" },
  "company.upsellText": {
    ru: "Бренд-страница работодателя — логотип, описание, сайт и вертикаль. Отдельно от кабинета рекрутера: компания — это бренд, рекрутер — конкретный человек внутри неё.",
    en: "An employer brand page — logo, description, website and vertical. Separate from the recruiter cabinet: the company is the brand, the recruiter is a specific person inside it.",
  },
  "company.tier.basic": { ru: "Basic", en: "Basic" },
  "company.tier.pro": { ru: "Pro", en: "Pro" },
  "company.tier.basicHint": {
    ru: "До 5 участников команды, до 20 активных вакансий, 30 просмотров/день на участника — $49/мес.",
    en: "Up to 5 team members, up to 20 active vacancies, 30 profile views/day per member — $49/mo.",
  },
  "company.tier.proHint": {
    ru: "До 15-20 участников команды, до 50 активных вакансий, 50 просмотров/день на участника — $99/мес.",
    en: "Up to 15-20 team members, up to 50 active vacancies, 50 profile views/day per member — $99/mo.",
  },
  "company.field.name": { ru: "Название компании", en: "Company name" },
  "company.field.namePlaceholder": { ru: "Например: GURO Casino Ltd", en: "E.g.: GURO Casino Ltd" },
  "company.field.vertical": { ru: "Вертикаль", en: "Vertical" },
  "company.field.verticalPlaceholder": { ru: "Gambling, Crypto…", en: "Gambling, Crypto…" },
  "company.field.website": { ru: "Сайт", en: "Website" },
  "company.field.websitePlaceholder": { ru: "example.com", en: "example.com" },
  "company.field.description": { ru: "Описание", en: "Description" },
  "company.field.descriptionPlaceholder": { ru: "Чем занимается компания", en: "What the company does" },
  "company.field.logoUrl": { ru: "Логотип (ссылка на картинку, PNG)", en: "Logo (image link, PNG)" },
  "company.field.logoUrlPlaceholder": { ru: "https://…/logo.png", en: "https://…/logo.png" },
  "company.field.coverUrl": { ru: "Обложка (ссылка на картинку, PNG)", en: "Cover banner (image link, PNG)" },
  "company.field.coverUrlPlaceholder": { ru: "https://…/cover.png", en: "https://…/cover.png" },
  "company.settingsBtn": { ru: "Настройки кабинета", en: "Cabinet settings" },
  "company.quickPublish": { ru: "➕ Опубликовать вакансию", en: "➕ Post a vacancy" },
  "company.quickConfirm": { ru: "🤝 Подтвердить сделку/найм", en: "🤝 Confirm deal/hire" },
  "company.activeVacancies": { ru: "Активных вакансий: {n}", en: "Active vacancies: {n}" },
  // Создание компании (27.08.2026, ТЗ "Роли и управление командой", раздел 1)
  "company.create.title": { ru: "Создать компанию", en: "Create a company" },
  "company.create.hint": {
    ru: "Вы станете Владельцем — сможете пригласить команду, публиковать вакансии и подтверждать сделки от лица бренда.",
    en: "You'll become the Owner — you can invite a team, post vacancies, and confirm deals on behalf of the brand.",
  },
  "company.create.nameLabel": { ru: "Название компании", en: "Company name" },
  "company.create.namePlaceholder": { ru: "Например: 1xBet", en: "E.g.: 1xBet" },
  "company.create.submit": { ru: "Создать", en: "Create" },
  "company.create.submitting": { ru: "Создаём…", en: "Creating…" },
  "company.create.error": { ru: "Не получилось создать компанию.", en: "Couldn't create the company." },
  "company.create.similarWarning": {
    ru: "Похожие названия уже есть в GURO ID: {names}. Если это не вы — возможно, стоит выбрать другое название.",
    en: "Similar names already exist in GURO ID: {names}. If that's not you, consider a different name.",
  },
  "company.create.joinHint": {
    ru: "Хотите присоединиться к уже существующей компании? Найдите её карточку через доску вакансий или поиск и нажмите «Запросить присоединение».",
    en: "Want to join an existing company instead? Find its card via the vacancy board or search and tap \"Request to join\".",
  },
  "company.types.title": { ru: "Тип компании", en: "Company type" },
  "company.types.hint": {
    ru: "Можно выбрать несколько — используется как фильтр в поиске и на доске вакансий.",
    en: "You can select several — used as a filter in search and on the vacancy board.",
  },
  "company.types.filterAll": { ru: "Все типы компаний", en: "All company types" },
  "company.types.otherLabel": { ru: "Другое", en: "Other" },
  "company.types.otherPlaceholder": { ru: "Свой вариант", en: "Your own type" },
  "company.types.operator_casino": { ru: "Оператор/Казино", en: "Operator/Casino" },
  "company.types.bookmaker": { ru: "Букмекер", en: "Bookmaker" },
  "company.types.cpa_network": { ru: "CPA-сеть", en: "CPA network" },
  "company.types.hr_agency": { ru: "HR / Рекрутинговое агентство", en: "HR / Recruiting agency" },
  "company.types.media_buying": { ru: "Арбитражная команда (Media Buying)", en: "Media buying team" },
  "company.types.b2b_platform": { ru: "B2B платформа/поставщик решений", en: "B2B platform/solutions provider" },
  "company.types.investor_fund": { ru: "Инвестор/фонд", en: "Investor/fund" },
  "company.verify.title": { ru: "Верификация", en: "Verification" },
  "company.verify.hint": {
    ru: "Напишите на verify@guroid.app с почты вашего корпоративного домена (не Gmail/публичные сервисы), указав название компании в GURO ID — администратор вручную сверит домен и включит бейдж.",
    en: "Email verify@guroid.app from your corporate domain address (not Gmail/public services), stating your GURO ID company name — an admin will manually check the domain and enable the badge.",
  },
  "company.verify.verified": { ru: "Верифицирована", en: "Verified" },
  "company.verify.pending": { ru: "Заявка отправлена, ожидает проверки администратором.", en: "Request sent, awaiting admin review." },
  "company.verify.submitBtn": { ru: "Подать заявку на верификацию", en: "Request verification" },
  "vacancies.officialCompanyBadge": { ru: "Официальная вакансия компании", en: "Official company vacancy" },
  "company.privacy.name": { ru: "Название компании", en: "Company name" },
  "company.privacy.vertical": { ru: "Вертикаль", en: "Vertical" },
  "company.privacy.description": { ru: "Описание", en: "Description" },
  "company.privacy.website": { ru: "Сайт", en: "Website" },
  "company.privacyHint": {
    ru: "Управляет тем, что видят чужие в кабинете компании (независимо от тумблеров личного профиля и кабинета рекрутера). По умолчанию скрыто — включите то, что хотите показать.",
    en: "Controls what others see in your company cabinet (independent of your personal profile and recruiter cabinet toggles). Hidden by default — turn on what you want to show.",
  },
  "company.loading": { ru: "Загружаем кабинет компании…", en: "Loading company cabinet…" },
  "company.loadError": { ru: "Не удалось загрузить кабинет компании.", en: "Couldn't load the company cabinet." },
  "company.addressTitle": { ru: "Крипто-адрес компании", en: "Company crypto address" },
  "company.addressHint": {
    ru: "Привяжите адрес — сделки с хешем от/на этот адрес получат повышенный бонус к рейтингу. Проверяется модератором вручную.",
    en: "Link an address — deals with a hash from/to it get a higher rating bonus. Reviewed manually by a moderator.",
  },
  "company.addressPlaceholder": { ru: "Адрес кошелька", en: "Wallet address" },
  "company.addressSubmit": { ru: "Отправить на проверку", en: "Submit for review" },
  "company.addressError": { ru: "Не получилось отправить адрес.", en: "Couldn't submit the address." },
  "company.addressStatus.pending": { ru: "на проверке", en: "pending review" },
  "company.addressStatus.approved": { ru: "подтверждён", en: "approved" },
  "company.addressStatus.rejected": { ru: "отклонён", en: "rejected" },

  // --- Роли и команда (27.08.2026, ТЗ "Роли и управление командой") ---
  "team.title": { ru: "Команда", en: "Team" },
  "team.counter": { ru: "{count} из {limit} участников", en: "{count} of {limit} members" },
  "team.tabRequests": { ru: "Запросы", en: "Requests" },
  "team.tabMembers": { ru: "Участники", en: "Members" },
  "team.approvalsLeftToday": { ru: "Одобрений сегодня осталось: {n}", en: "{n} approvals left today" },
  "team.requestsEmpty": { ru: "Пока нет заявок на присоединение.", en: "No join requests yet." },
  "team.approveBtn": { ru: "Принять", en: "Accept" },
  "team.rejectBtn": { ru: "Отклонить", en: "Reject" },
  "team.removeBtn": { ru: "Удалить из команды", en: "Remove from team" },
  "team.transferBtn": { ru: "Передать владение", en: "Transfer ownership" },
  "team.removeConfirm": { ru: "Удалить {name} из команды?", en: "Remove {name} from the team?" },
  "team.transferConfirm": {
    ru: "Передать роль владельца {name}? Вы станете Админом, {name} получит полный контроль над компанией, включая управление подпиской.",
    en: "Transfer the Owner role to {name}? You'll become an Admin, {name} will get full control of the company, including subscription management.",
  },
  "team.loadError": { ru: "Не удалось загрузить команду.", en: "Couldn't load the team." },
  "team.role.owner": { ru: "Владелец", en: "Owner" },
  "team.role.admin": { ru: "Админ/Рекрутер", en: "Admin/Recruiter" },
  "team.errors.generic": { ru: "Не получилось выполнить действие.", en: "Couldn't complete the action." },
  "team.errors.memberLimitReached": {
    ru: "Достигнут лимит участников по тарифу ({limit}). Удалите неактивного участника или перейдите на тариф Компания Pro.",
    en: "Reached the tariff's member limit ({limit}). Remove an inactive member or upgrade to Company Pro.",
  },
  "team.errors.dailyApprovalLimitReached": {
    ru: "Лимит одобрений на сегодня исчерпан. Следующие можно одобрить {date}.",
    en: "Today's approval limit is used up. You can approve more on {date}.",
  },
  "team.join.requestBtn": { ru: "Запросить присоединение", en: "Request to join" },
  "team.join.positionLabel": { ru: "Ваша должность в компании", en: "Your position at the company" },
  "team.join.positionPlaceholder": { ru: "Например: Affiliate Manager", en: "E.g.: Affiliate Manager" },
  "team.join.submitBtn": { ru: "Отправить запрос", en: "Send request" },
  "team.join.submitting": { ru: "Отправляем…", en: "Sending…" },
  "team.join.sentOk": { ru: "Запрос отправлен — ждите одобрения от владельца компании.", en: "Request sent — wait for the company owner to approve it." },
  "team.join.alreadyRequested": { ru: "Вы уже подали заявку на присоединение.", en: "You've already sent a join request." },
  "team.join.alreadyInCompany": { ru: "Вы уже состоите в другой компании.", en: "You're already a member of another company." },
  "team.join.alreadyMember": { ru: "Вы уже участник этой компании.", en: "You're already a member of this company." },
  "team.join.error": { ru: "Не получилось отправить запрос.", en: "Couldn't send the request." },

  // --- Вакансии (Фаза 4, 12.08.2026; переписано 26.08.2026 под ТЗ
  // "Recruitment — ВАКАНСИИ") ---
  "tab.vacancies": { ru: "Вакансии", en: "Jobs" },
  "vacancies.title": { ru: "Вакансии", en: "Vacancies" },
  "vacancies.hint": {
    ru: "Доска вакансий GURO ID — публикуют подписчики кабинетов Рекрутер и Компания, смотреть может любой с подпиской GURO ID.",
    en: "GURO ID job board — posted by Recruiter and Company cabinet subscribers, visible to any GURO ID subscriber.",
  },
  "vacancies.allVerticals": { ru: "Все", en: "All" },
  "vacancies.publishBtn": { ru: "➕ Опубликовать вакансию", en: "➕ Post a vacancy" },
  "vacancies.upsellText": {
    ru: "Публиковать вакансии могут подписчики кабинета Рекрутер или Компания — оформите в «Профиль».",
    en: "Only Recruiter or Company cabinet subscribers can post vacancies — subscribe under \"Profile\".",
  },
  "vacancies.empty": { ru: "Пока нет активных вакансий по этому фильтру.", en: "No active vacancies match this filter." },
  "vacancies.loadError": { ru: "Не удалось загрузить вакансии.", en: "Couldn't load vacancies." },
  "vacancies.salaryNegotiable": { ru: "По договорённости", en: "Negotiable" },
  "vacancies.applyBtn": { ru: "✉️ Откликнуться", en: "✉️ Apply" },
  "vacancies.externalApplyBtn": { ru: "Откликнуться по внешней ссылке", en: "Apply via external link" },
  "vacancies.respondSentOk": { ru: "Отклик отправлен ✅", en: "Response sent ✅" },
  "vacancies.respondError.ALREADY_RESPONDED": { ru: "Вы уже откликались на эту вакансию.", en: "You've already applied to this vacancy." },
  "vacancies.respondError.generic": { ru: "Не получилось отправить отклик. Попробуйте ещё раз.", en: "Couldn't send the response. Please try again." },
  "vacancies.tabBoard": { ru: "Доска", en: "Board" },
  "vacancies.tabMine": { ru: "Мои вакансии", en: "My vacancies" },
  "vacancies.mineTitle": { ru: "Мои вакансии", en: "My vacancies" },
  "vacancies.mineEmpty": { ru: "Вы ещё не публиковали вакансий.", en: "You haven't posted any vacancies yet." },
  "vacancies.closeBtn": { ru: "Закрыть", en: "Close" },
  "vacancies.statusClosed": { ru: "Закрыта", en: "Closed" },
  "vacancies.status.active": { ru: "Активна", en: "Active" },
  "vacancies.status.paused": { ru: "На паузе", en: "Paused" },
  "vacancies.status.closed": { ru: "Закрыта", en: "Closed" },
  "vacancies.verifiedCompany": { ru: "верифицированная компания", en: "verified company" },
  "vacancies.postedToday": { ru: "Опубликована сегодня", en: "Posted today" },
  "vacancies.postedAgo": { ru: "Опубликована {days} дн. назад", en: "Posted {days}d ago" },
  "vacancies.viewsLabel": { ru: "{n} просмотров", en: "{n} views" },
  "vacancies.responsesLabel": { ru: "{n} откликов", en: "{n} responses" },
  "vacancies.searchPlaceholder": { ru: "Поиск по названию/описанию…", en: "Search title/description…" },
  "vacancies.truncatedHint": {
    ru: "Показаны не все результаты — уточните фильтры.",
    en: "Not all results are shown — narrow down your filters.",
  },
  "vacancies.showDescription": { ru: "Показать описание", en: "Show description" },
  "vacancies.writeBtn": { ru: "✉️ Написать", en: "✉️ Message" },
  "vacancies.workFormat.remote": { ru: "Удалённо", en: "Remote" },
  "vacancies.workFormat.office": { ru: "Офис", en: "Office" },
  "vacancies.workFormat.hybrid": { ru: "Гибрид", en: "Hybrid" },
  "vacancies.employment.full": { ru: "Полная занятость", en: "Full-time" },
  "vacancies.employment.part": { ru: "Частичная занятость", en: "Part-time" },
  "vacancies.employment.project": { ru: "Проектная работа", en: "Project-based" },
  "vacancies.manage.edit": { ru: "Редактировать", en: "Edit" },
  "vacancies.manage.pause": { ru: "Пауза", en: "Pause" },
  "vacancies.manage.resume": { ru: "Возобновить", en: "Resume" },
  "vacancies.manage.extend": { ru: "Продлить", en: "Extend" },
  "vacancies.manage.close": { ru: "Закрыть", en: "Close" },
  "vacancies.responses.title": { ru: "Отклики", en: "Responses" },
  "vacancies.responses.empty": { ru: "По этой вакансии пока нет откликов.", en: "No responses yet for this vacancy." },
  "vacancies.responses.errorGeneric": { ru: "Не получилось выполнить действие.", en: "Couldn't complete the action." },
  "vacancies.responses.statusAll": { ru: "Все", en: "All" },
  "vacancies.responses.status.new": { ru: "Новый", en: "New" },
  "vacancies.responses.status.reviewing": { ru: "На рассмотрении", en: "Reviewing" },
  "vacancies.responses.status.interview": { ru: "Собеседование", en: "Interview" },
  "vacancies.responses.status.offer": { ru: "Оффер отправлен", en: "Offer sent" },
  "vacancies.responses.status.hired": { ru: "Найм подтверждён", en: "Hired" },
  "vacancies.responses.status.rejected": { ru: "Отказ", en: "Rejected" },
  "vacancies.responses.confirmHireBtn": { ru: "✅ Подтвердить найм", en: "✅ Confirm hire" },
  "vacancies.form.title": { ru: "Опубликовать вакансию", en: "Post a vacancy" },
  "vacancies.form.editTitle": { ru: "Редактировать вакансию", en: "Edit vacancy" },
  "vacancies.form.authorWorkspaceLabel": { ru: "Публиковать от имени", en: "Post as" },
  "vacancies.form.titleLabel": { ru: "Название позиции", en: "Job title" },
  "vacancies.form.titlePlaceholder": { ru: "Например: Senior Product Manager", en: "E.g.: Senior Product Manager" },
  "vacancies.form.mismatchWarning": {
    ru: "Название разошлось с выбранной должностью — не страшно, просто проверьте вертикаль/грейд/должность ниже.",
    en: "The title no longer matches the selected position — no problem, just double-check the vertical/grade/position below.",
  },
  "vacancies.form.verticalLabel": { ru: "Вертикаль", en: "Vertical" },
  "vacancies.form.gradeLabel": { ru: "Грейд", en: "Grade" },
  "vacancies.form.gradePlaceholder": { ru: "Выберите грейд", en: "Select grade" },
  "vacancies.form.positionLabel": { ru: "Должность", en: "Position" },
  "vacancies.form.positionPlaceholder": { ru: "Выберите должность", en: "Select position" },
  "vacancies.form.positionOther": { ru: "Другое…", en: "Other…" },
  "vacancies.form.positionOtherPlaceholder": { ru: "Укажите должность", en: "Enter the position" },
  "vacancies.form.locationLabel": { ru: "Локация", en: "Location" },
  "vacancies.form.locationPlaceholder": { ru: "Malta, Cyprus…", en: "Malta, Cyprus…" },
  "vacancies.form.workFormatLabel": { ru: "Формат работы", en: "Work format" },
  "vacancies.form.employmentLabel": { ru: "Занятость", en: "Employment type" },
  "vacancies.form.salaryLabel": { ru: "Зарплатная вилка", en: "Salary range" },
  "vacancies.form.salaryFromPlaceholder": { ru: "От, $", en: "From, $" },
  "vacancies.form.salaryToPlaceholder": { ru: "До, $", en: "To, $" },
  "vacancies.form.salaryNegotiableLabel": { ru: "По договорённости (не указывать вилку)", en: "Negotiable (don't show a range)" },
  "vacancies.form.salaryVisibleLabel": { ru: "Показывать сумму всем", en: "Show amount to everyone" },
  "vacancies.form.descriptionLabel": { ru: "Описание вакансии", en: "Job description" },
  "vacancies.form.descriptionPlaceholder": {
    ru: "Обязанности, требования, что предлагаете",
    en: "Responsibilities, requirements, what you offer",
  },
  "vacancies.form.contactMethodLabel": { ru: "Как откликаться", en: "How to apply" },
  "vacancies.form.contactGuroId": { ru: "Через GURO ID", en: "Via GURO ID" },
  "vacancies.form.contactExternal": { ru: "Внешняя ссылка", en: "External link" },
  "vacancies.form.contactUrlPlaceholder": { ru: "Ссылка для отклика", en: "Application link" },
  "vacancies.form.durationLabel": { ru: "Срок размещения", en: "Listing duration" },
  "vacancies.form.durationDays": { ru: "{days} дн.", en: "{days}d" },
  "vacancies.form.langLabel": { ru: "Язык публикации", en: "Posting language" },
  "vacancies.form.submit": { ru: "Опубликовать", en: "Publish" },
  "vacancies.form.saveBtn": { ru: "Сохранить", en: "Save" },
  "vacancies.form.submitting": { ru: "Публикуем…", en: "Publishing…" },
  "vacancies.form.titleRequired": { ru: "Укажите название позиции.", en: "Job title is required." },
  "vacancies.form.error": { ru: "Не получилось опубликовать вакансию. Попробуйте ещё раз.", en: "Couldn't post the vacancy. Please try again." },
  "vacancies.form.recruiterSubRequired": {
    ru: "Нужна подписка кабинета Рекрутер.",
    en: "A Recruiter cabinet subscription is required.",
  },
  "vacancies.form.companySubRequired": {
    ru: "Нужна подписка кабинета Компания.",
    en: "A Company cabinet subscription is required.",
  },
  "vacancies.form.dailyLimitReached": {
    ru: "Дневной лимит новых публикаций исчерпан. Обновится {date}.",
    en: "Daily limit of new postings reached. Resets on {date}.",
  },
  "vacancies.form.activeLimitReached": {
    ru: "Достигнут потолок одновременно активных вакансий ({limit}). Закройте одну из старых, чтобы опубликовать новую.",
    en: "Reached the limit of simultaneously active vacancies ({limit}). Close one of the older ones to post a new one.",
  },
  "recruiter.responses.empty": { ru: "Пока нет откликов на ваши вакансии.", en: "No responses to your vacancies yet." },
  "recruiter.responses.loadError": { ru: "Не удалось загрузить отклики.", en: "Couldn't load responses." },

  // --- Приватность (общее) ---
  "privacy.title": { ru: "Приватность", en: "Privacy" },
  "privacy.visible": { ru: "Видно всем в поиске", en: "Visible to everyone in search" },
  "privacy.hidden": { ru: "Скрыто от чужого поиска", en: "Hidden from search" },
  "privacy.saveError": { ru: "Не получилось сохранить настройку. Попробуйте ещё раз.", en: "Couldn't save the setting. Please try again." },
  "privacy.label.show_name": { ru: "Имя", en: "Name" },
  "privacy.label.show_company": { ru: "Компания", en: "Company" },
  "privacy.label.show_vertical": { ru: "Вертикаль / специализация", en: "Vertical / specialization" },
  "privacy.label.show_profession": { ru: "Должность", en: "Position" },
  "privacy.label.show_tenure": { ru: "Стаж в комьюнити", en: "Time in community" },
  "privacy.label.show_reputation": { ru: "Рейтинг", en: "Rating" },
  "privacy.label.show_cv": { ru: "CV", en: "CV" },
  "privacy.label.show_contacts": { ru: "Контакты (LinkedIn, сайт)", en: "Contacts (LinkedIn, website)" },
  "privacy.label.show_offers": { ru: "Офферы (ищу / полезен)", en: "Offers (looking for / can offer)" },

  "workStatusBadge.free": { ru: "Виден всем бесплатно", en: "Visible to everyone for free" },

  "locked.title": { ru: "Полная карточка профиля", en: "Full profile card" },
  "locked.note": { ru: "Полный профиль, партнёры и история — по подписке GURO ID", en: "Full profile, partners and history — GURO ID subscription only" },

  "onboardingScreen.profileNotFound": { ru: "Профиль не найден. Попробуйте позже.", en: "Profile not found. Please try again later." },
  "profileScreen.loading": { ru: "Загружаем профиль…", en: "Loading profile…" },
  "profileScreen.loadError": { ru: "Не удалось загрузить профиль. Попробуйте позже.", en: "Couldn't load profile. Please try again later." },
};

// Список вертикалей в питче онбординга (не строка, отдельно от STRINGS) —
// та же семёрка, что была в исходном питче владельца, RU/EN пара.
export const ONBOARDING_VERTICALS = {
  ru: ["Гемблинг", "Бейтинг", "Крипто", "Нутра", "Дейтинг", "Е-коммерс", "Другое"],
  en: ["Gambling", "Betting", "Crypto", "Nutra", "Dating", "E-Commerce", "Other"],
};

export function translate(lang, key, vars) {
  const entry = STRINGS[key];
  let str = entry ? (entry[lang] || entry.ru) : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replaceAll(`{${k}}`, v);
    }
  }
  return str;
}

const LangContext = createContext({ lang: "ru", setLang: () => {}, t: (key) => key });

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(readStoredLang);

  function setLang(next) {
    setLangState(next);
    writeStoredLang(next);
  }

  function t(key, vars) {
    return translate(lang, key, vars);
  }

  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}
