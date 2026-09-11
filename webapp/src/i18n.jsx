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
  // 07.09.2026: название «Сделки» возвращено по решению владельца. В
  // перечне дизайн-системы вкладка названа «Подтвердить» — расхождение
  // осознанное, вопрос вынесен дизайнеру. Иконка остаётся галочкой: её
  // просили отдельно и привязывали к разделу, а не к слову.
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
  "hub.menu.edit": { ru: "Редактировать", en: "Edit profile" },
  "editProfile.title": { ru: "Анкета", en: "Profile details" },
  "editProfile.name": { ru: "Имя / подпись", en: "Name" },
  "editProfile.company": { ru: "Компания", en: "Company" },
  "editProfile.profession": { ru: "Должность", en: "Position" },
  "editProfile.vertical": { ru: "Вертикаль", en: "Vertical" },
  "editProfile.grade": { ru: "Грейд", en: "Grade" },
  "editProfile.choosePlaceholder": { ru: "Не выбрано", en: "Not selected" },
  "editProfile.verticalHint": {
    ru: "Вертикаль и грейд выбираются из списка: по ним работает поиск, и произвольное значение сделает вас ненаходимым.",
    en: "Vertical and grade are picked from a list: search relies on them, and a free-form value would make you unfindable.",
  },
  "editProfile.lockedHint": {
    ru: "Юзернейм подставляется из Telegram, а страну меняет бот — она хранится вместе с кодом страны, который используется в рассылках.",
    en: "The username comes from Telegram, and the country is changed via the bot — it is stored together with a country code used for mailings.",
  },
  "hub.menu.offers": { ru: "Мои офферы", en: "My offers" },
  "hub.menu.messages": { ru: "Мои сообщения", en: "My messages" },
  "hub.menu.qr": { ru: "Мой QR", en: "My QR" },
  // hub.ratingLocked снят 07.09.2026: строка состояла из одного эмодзи,
  // а замок в этом месте рисуется иконкой (Shared.jsx, скрытое значение).
  "hub.daysInCommunity": { ru: "В сообществе {count} {unit}", en: "{count} {unit} in the community" },
  // Карточка рейтинга на главном экране Профиля (28.08.2026, макет
  // "01 · Профиль (личный)") — кольцо-прогресс 0/100 + название уровня,
  // вместо прежнего маленького кружка в шапке визитки.
  "hub.ratingCard.title": { ru: "Ваш рейтинг", en: "Your rating" },
  "hub.ratingCard.hint": {
    ru: "Рейтинг растёт от подтверждённых сделок и стажа в комьюнити.",
    en: "Your rating grows from confirmed deals and time in the community.",
  },
  "hub.ratingCard.partnerships": { ru: "Партнёрства", en: "Partnerships" },
  "hub.ratingCard.tenure": { ru: "Стаж, дней", en: "Tenure, days" },

  // Карточка "Первый шаг" (28.08.2026, тот же макет) — видна, пока у
  // пользователя 0 подтверждённых партнёрств: вместо демотивирующего
  // "рейтинг 0" сразу даёт действие.
  "hub.firstStep.eyebrow": { ru: "Первый шаг", en: "First step" },
  "hub.firstStep.title": {
    ru: "Подтвердите партнёрство — получите первые баллы рейтинга",
    en: "Confirm a partnership — earn your first rating points",
  },
  "hub.firstStep.text": {
    ru: "Партнёр подтверждает сделку со своей стороны — запись появляется в обоих профилях. Без ответа запись не публикуется.",
    en: "Your partner confirms the deal on their side — the record appears in both profiles. Without a response, it isn't published.",
  },
  "hub.firstStep.cta": { ru: "Подтвердить партнёрство", en: "Confirm partnership" },

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
  // Названия уровней рейтинга (5.3, guro_constants.REPUTATION_TIERS) —
  // бэкенд шлёт литералы Bronze/Silver/Gold/Platinum в reputation_tier,
  // тут только локализация подписи под кольцом (28.08.2026, макет "01 ·
  // Профиль (личный)" явно даёт готовый текст только для Bronze —
  // "Начальный уровень", остальные три — по аналогии).
  "rating.tier.bronze": { ru: "Начальный уровень", en: "Starting level" },
  "rating.tier.silver": { ru: "Уверенный уровень", en: "Confident level" },
  "rating.tier.gold": { ru: "Высокий уровень", en: "High level" },
  "rating.tier.platinum": { ru: "Топовый уровень", en: "Top level" },
  "metric.rating": { ru: "Рейтинг", en: "Rating" },
  "metric.partnerships": { ru: "Партнёрств", en: "Partnerships" },
  "metric.daysInCommunity": { ru: "Дней в комьюнити", en: "Days in community" },
  // Счётчики оборота (ТЗ «Верификация транзакций», разделы 7-8, 12).
  "turnover.title": { ru: "Оборот", en: "Turnover" },
  "turnover.received": { ru: "Получено", en: "Received" },
  "turnover.paid": { ru: "Оплачено", en: "Paid" },
  "turnover.confirmed": { ru: "подтверждено", en: "confirmed" },
  "turnover.hint": {
    ru: "Суммы, подтверждённые транзакцией в блокчейне",
    en: "Amounts confirmed by an on-chain transaction",
  },
  "turnover.empty": {
    ru: "Счётчик начнётся с первой сделки, где указан хеш транзакции.",
    en: "The counter starts with your first deal that includes a transaction hash.",
  },
  "turnover.unverified": {
    ru: "заявлено без подтверждения: {amount}",
    en: "stated without verification: {amount}",
  },
  "partner.amountReceived": { ru: "Получено", en: "Received" },
  "partner.amountPaid": { ru: "Оплачено", en: "Paid" },
  "partner.amountNote": { ru: "(со слов инициатора)", en: "(as stated by the initiator)" },
  // Атрибуция оффера/отзыва (25.08.2026, баг "Пофиксить.pdf" — офер/отзыв
  // писал инициатор о СЕБЕ, но отображалось безлико под именем контрагента).
  "partner.wordsOf": { ru: "Слова {name}", en: "{name}'s words" },
  "partner.wordsYours": { ru: "Ваши слова", en: "Your words" },
  "partner.wordsInitiator": { ru: "Слова инициатора", en: "Initiator's words" },
  "partner.notRated": { ru: "не влияет на рейтинг", en: "doesn't affect rating" },
  // Три состояния ончейн-проверки (ТЗ «Верификация транзакций», разделы
  // 2 и 10). Прежние partner.txHash/txVerified сняты вместе со старым
  // блоком, который ставил отметку без сверки суммы.
  "partner.tx.none": { ru: "Сумма со слов сторон", en: "Amount as stated by the parties" },
  // ТЗ «Hash_Uniqueness», раздел 5.
  "partner.tx.tooOld": {
    ru: "Транзакция старше 12 месяцев — ончейн-подтверждение не применяется",
    en: "The transaction is over 12 months old — on-chain confirmation doesn't apply",
  },
  "partner.tx.mismatch": { ru: "Сумма в блокчейне не совпадает", en: "On-chain amount doesn't match" },
  "partner.tx.declared": { ru: "Указано", en: "Stated" },
  "partner.tx.onchain": { ru: "В транзакции", en: "In transaction" },
  "partner.tx.verified": { ru: "Подтверждено ончейн", en: "Verified on-chain" },
  "partner.tx.copy": { ru: "Копировать", en: "Copy" },
  "partner.tx.copied": { ru: "Скопировано", en: "Copied" },
  "partner.tx.explorer": { ru: "Проверить в блокчейне →", en: "Check on the blockchain →" },
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
  "rating.otherHidden": {
    ru: "Оценка собеседника ещё скрыта — появится после его ответа или через 14 дней.",
    en: "The other side's rating is still hidden — it'll appear after they respond or in 14 days.",
  },
  "rating.error": { ru: "Не получилось отправить оценку.", en: "Couldn't submit the rating." },

  // --- Моё CV ---
  "cv.title": { ru: "Моё CV", en: "My CV" },
  // «Характеристика» (26.08.2026) — кнопка в каждом профиле, доступная
  // любому подписчику: офферы ("Я ищу"/"Я полезен") + CV просматриваемого.
  "characteristic.button": { ru: "Характеристика", en: "Characteristic" },
  "characteristic.hide": { ru: "Скрыть характеристику", en: "Hide characteristic" },
  "characteristic.offersTitle": { ru: "Офферы", en: "Offers" },
  "characteristic.emptyOffers": { ru: "Офферы не заполнены.", en: "No offers filled in." },
  "cv.viewBtn": { ru: "Посмотреть моё CV", en: "View my CV" },
  "cv.backToEdit": { ru: "‹ К редактированию", en: "‹ Back to editing" },
  "cv.shareBtn": { ru: "Поделиться CV", en: "Share CV" },
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
  "contacts.linkedinLabel": { ru: "LinkedIn", en: "LinkedIn" },
  "contacts.websiteLabel": { ru: "Сайт", en: "Website" },
  "contacts.showQr": { ru: "Показать мой QR (визитка)", en: "Show my QR (business card)" },
  "contacts.inviteBtn": { ru: "Пригласить коллегу", en: "Invite a colleague" },
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
  "messageBtn": { ru: "Написать", en: "Message" },
  "recruiterViewBtn": { ru: "Посмотреть как рекрутера", en: "View as recruiter" },
  "companyViewBtn": { ru: "Посмотреть как компанию", en: "View as company" },

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

  // First-time flow (11.09.2026) — регистрация прямо в приложении.
  "createProfile.emptyName": { ru: "Ваше имя", en: "Your name" },
  "createProfile.emptyPosition": { ru: "Должность не указана", en: "Position not set" },
  "createProfile.exampleName": { ru: "Артём Л.", en: "Artem L." },
  "createProfile.examplePosition": { ru: "Head of Affiliates · Gambling", en: "Head of Affiliates · Gambling" },
  "createProfile.ctaHint": {
    ru: "Займёт около трёх минут. Публикация профиля — по подписке, от 400 ⭐ в месяц.",
    en: "Takes about three minutes. Publishing your profile requires a subscription, from 400 ⭐ / month.",
  },
  "createProfile.ctaBtn": { ru: "Создать свой GURO ID", en: "Create your GURO ID" },
  "createProfile.stepLabel": { ru: "Шаг {step} из {total}", en: "Step {step} of {total}" },
  "createProfile.namePlaceholderCard": { ru: "Имя?", en: "Name?" },
  "createProfile.positionPlaceholderCard": { ru: "Должность?", en: "Position?" },
  "createProfile.positionTitle": { ru: "Кем вы работаете", en: "What do you do" },
  "createProfile.nameTitle": { ru: "Как вас представить", en: "What should we call you" },
  "createProfile.nameLabel": { ru: "Имя и фамилия", en: "Full name" },
  "createProfile.namePlaceholder": { ru: "Например, Юлия Черных", en: "e.g. Yulia Chernykh" },
  "createProfile.nextBtn": { ru: "Дальше · осталось {left} шага", en: "Next · {left} steps left" },
  "createProfile.reviewTitle": { ru: "Проверьте перед публикацией", en: "Review before publishing" },
  "createProfile.reviewIntro": {
    ru: "Дальше — подписка: без неё профиль не виден в поиске.",
    en: "Next is the subscription: without it your profile isn't visible in search.",
  },
  "createProfile.publishBtn": { ru: "Опубликовать профиль", en: "Publish profile" },
  "createProfile.publishing": { ru: "Публикуем…", en: "Publishing…" },
  "createProfile.reviewNextHint": { ru: "Следующий шаг — подписка.", en: "Next step — subscription." },
  "createProfile.saveError": { ru: "Не получилось сохранить. Попробуйте ещё раз.", en: "Couldn't save. Please try again." },
  "createProfile.readyEyebrow": { ru: "ПОСЛЕДНИЙ ШАГ", en: "LAST STEP" },
  "createProfile.readyTitle": { ru: "Ваш профиль готов к публикации", en: "Your profile is ready to publish" },
  "createProfile.readyIntro": {
    ru: "Оформите подписку, чтобы открыть полный GURO ID, вакансии, поиск партнёров и подтверждение сотрудничеств.",
    en: "Subscribe to unlock full GURO ID, job listings, partner search and deal confirmation.",
  },
  "createProfile.skipForNow": { ru: "Пока без подписки", en: "Skip for now" },

  // --- Поиск ---
  "search.title": { ru: "Поиск", en: "Search" },
  // 28.08.2026 (макет "03 · Поиск", Untitled-7): текст hint/placeholder/
  // cabinetsHint/browseHint обновлены на формулировки из макета — старые
  // версии (25.08.2026, "Правки.pdf") были по смыслу тем же самым, но
  // короче/без явного упоминания "какая вертикаль реально работает с
  // реальными данными" (Gambling) — макет добавляет эту деталь.
  "search.hint": {
    ru: "Поиск по юзернейму — бесплатно (тизер-карточка): показывает только то, что участник сам открыл в профиле. Поиск по описанию, должности и вертикали доступен в кабинете Рекрутер или Компания.",
    en: "Search by username is free (teaser card): shows only what the member opened up in their profile. Search by description, position and vertical is available in the Recruiter or Company cabinet.",
  },
  "search.placeholder": { ru: "Юзернейм, например @igamingschool", en: "Username, e.g. @igamingschool" },
  "search.submit": { ru: "Найти", en: "Search" },
  "search.submitting": { ru: "Ищем…", en: "Searching…" },
  "search.backToList": { ru: "‹ К списку", en: "‹ Back to list" },
  // Два режима раздела «Поиск» для владельцев кабинета (стр. 7 отчёта).
  "search.mode.classic": { ru: "Пробить по юзернейму", en: "Check by username" },
  "search.mode.candidates": { ru: "Найти кандидата", en: "Find a candidate" },
  "search.cabinetsHint": {
    ru: "Нужен поиск по описанию, должности и вертикали? Оформите кабинет Рекрутер или Компания в «Профиль».",
    en: "Need to search by description, position and vertical? Activate the Recruiter or Company cabinet in \"Profile\".",
  },
  "search.browseHint": {
    ru: "Фильтр по вертикали — демо-версия (по подписке). Сейчас с реальными данными работает только Gambling:",
    en: "Vertical filter — demo version (subscription required). Right now only Gambling works with real data:",
  },
  "search.paywallTitle": { ru: "Поиск по вертикалям — по подписке", en: "Vertical search — subscription only" },
  "search.paywallText": { ru: "Без подписки доступен только точный поиск по юзернейму.", en: "Without a subscription only exact username search is available." },
  "search.notFound": { ru: "Такой участник не найден в GURO ID.", en: "No such member found in GURO ID." },
  "search.genericError": { ru: "Ошибка поиска.", en: "Search error." },
  "search.viewLimitReached": {
    ru: "Дневной лимит просмотров профилей исчерпан. Обновится {date}.",
    en: "Daily profile view limit reached. Resets on {date}.",
  },
  "search.topToggle": { ru: "Сначала высокий рейтинг", en: "Highest rating first" },
  "search.emptyList": { ru: "Ничего не нашлось. Попробуйте другое описание или вертикаль.", en: "Nothing found. Try another description or vertical." },
  "search.truncated": { ru: "Показаны не все совпадения — уточните запрос.", en: "Not all matches shown — refine your query." },
  "search.resumesToggle": {
    ru: "Только те, кто ищет работу (для вертикалей выше и кнопки ниже)",
    en: "Only people looking for work (applies to verticals above and the button below)",
  },
  "search.resumesShowAll": { ru: "Показать всех, кто ищет работу", en: "Show everyone looking for work" },
  "identity.vertical": { ru: "Вертикаль: ", en: "Vertical: " },
  "identity.company": { ru: "Компания: ", en: "Company: " },
  "identity.visibilityHint": {
    ru: "Рейтинг и стаж видны всегда с активной подпиской — независимо от настроек приватности собеседника.",
    en: "Rating and tenure are always visible with an active subscription — regardless of the other side's privacy settings.",
  },
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
    ru: "Вы действуете от лица компании — сделка попадёт в общую историю бренда.",
    en: "You're acting on behalf of the company — the deal will go into the brand's shared history.",
  },
  // 28.08.2026 (макет "06 · Сделки — шаг 1", Untitled-9): текст был устаревшим
  // — упоминал "офер и отзыв видны всем чужим", хотя отзыв убран с этого шага
  // ещё 25.08.2026 (см. review=None в guro_id_api.py, комментарий там же —
  // факт и оценка теперь два разных шага). Новый текст явно это объясняет
  // ("без отзыва и оценки... на шаге 2"), заодно добавлена подпись "Шаг 1 из
  // 2" над этим текстом (confirm.stepLabel) — раньше нигде не было видно,
  // что подтверждение партнёрства состоит из двух шагов.
  "confirm.stepLabel": { ru: "Шаг 1 из 2 — фиксация факта сотрудничества", en: "Step 1 of 2 — recording the fact of cooperation" },
  "confirm.hint": {
    ru: "Укажите юзернейм человека, с которым уже состоялось сотрудничество. Ему придёт запрос на подтверждение от бота — запись появится в профилях обоих только после его ответа. Это только фиксация факта: без отзыва и оценки. Оценить сотрудничество можно будет отдельно на шаге 2, после того как оба подтвердят. Суммы видны только если включите показ ниже.",
    en: "Enter the username of someone you've already worked with. They'll get a confirmation request from the bot — the record appears in both profiles only after they respond. This step only records the fact: no review, no rating. You'll be able to rate the collaboration separately on step 2, once both sides confirm. Amounts are visible only if you enable showing them below.",
  },
  "confirm.usernameLabel": { ru: "Юзернейм контрагента", en: "Counterparty's username" },
  "confirm.usernamePlaceholder": { ru: "Например: @igamingschool", en: "E.g.: @igamingschool" },
  "confirm.ptypeLabel": { ru: "Тип партнёрства", en: "Partnership type" },
  "confirm.ptype.deal": { ru: "Сделка", en: "Deal" },
  "confirm.ptype.hire": { ru: "Найм", en: "Hire" },
  "confirm.ptypeHint": {
    ru: "Сделка — разовое сотрудничество (10 баллов к рейтингу) · Найм — трудоустройство (15 баллов к рейтингу)",
    en: "Deal — one-off cooperation (10 rating points) · Hire — employment (15 rating points)",
  },
  "confirm.verticalLabel": { ru: "Вертикаль", en: "Vertical" },
  "confirm.geoLabel": { ru: "Гео (необязательно)", en: "Geo (optional)" },
  "confirm.geoPlaceholder": { ru: "Одесса, Кипр…", en: "Odesa, Cyprus…" },
  "confirm.offerLabel": { ru: "Оффер — суть сделки", en: "Offer — deal summary" },
  "confirm.offerPlaceholder": { ru: "Например: привёл байера на казино-трафик", en: "E.g.: brought in a buyer for casino traffic" },
  "confirm.amountLabel": { ru: "Сумма", en: "Amount" },
  // Безоплатное партнёрство (ТЗ раздел 9.1).
  "confirm.noPaymentLabel": {
    ru: "Без прямой оплаты между нами",
    en: "No direct payment between us",
  },
  "confirm.noPaymentHint": {
    ru: "Отметьте, если денег между вами не было: платил работодатель или третья сторона, бартер, реферальная схема.",
    en: "Check this if no money changed hands between you: an employer or third party paid, barter, or a referral scheme.",
  },
  // Сумма — два поля (получил/заплатил), сделка обычно односторонняя,
  // поэтому требуем заполнить любое одно (05.09.2026).
  "confirm.amountRequiredHint": {
    ru: "Заполните хотя бы одно поле — сколько получили или сколько заплатили.",
    en: "Fill in at least one — how much you received or how much you paid.",
  },
  "confirm.amountReceivedPlaceholder": { ru: "Я получил, $", en: "I received, $" },
  "confirm.amountPaidPlaceholder": { ru: "Я заплатил, $", en: "I paid, $" },
  "confirm.amountVisible": { ru: "Показывать сумму чужим (по умолчанию скрыта)", en: "Show amount to others (hidden by default)" },
  // 28.08.2026 (макет "06 · Сделки — шаг 1"): макет рисует ссылку и хэш как
  // два отдельных поля — сознательно оставлено ОДНО (см. guro_id_api.py::
  // extract_tx_hash, решение 25.08.2026 — юзер вставляет ЛЮБОЙ формат, поле
  // само вырезает хэш из ссылки), текст поля обновлён, чтобы явно показать
  // оба принимаемых формата вместо одного только "хэш".
  "confirm.txHashLabel": { ru: "Хэш или ссылка на транзакцию", en: "Transaction hash or link" },
  "confirm.txHashPlaceholder": {
    ru: "Например: 0x71c4…e9a3 или https://etherscan.io/tx/0x71c4…e9a3",
    en: "E.g.: 0x71c4…e9a3 or https://etherscan.io/tx/0x71c4…e9a3",
  },
  "confirm.txHashHint": {
    ru: "Подтверждает реальность перевода. Виден вместе с суммой — по той же галочке выше.",
    en: "Backs up the transfer as real. Shown together with the amount — same checkbox above.",
  },
  // Формулировка владельца («рекрутер каб.pdf», стр. 4).
  "confirm.txHashRequired": {
    ru: "Нет хеша — нет сделки: мы не верим на слово. Если перевода между вами не было, отметьте «Без прямой оплаты» выше.",
    en: "No hash, no deal — we don't take your word for it. If no money changed hands, check \"No direct payment\" above.",
  },
  "confirm.error.TX_HASH_REQUIRED": {
    ru: "Добавьте хеш транзакции — без него сделка не засчитывается.",
    en: "Add the transaction hash — without it the deal doesn't count.",
  },
  // Раздел 3, случай A — объясняем, а не ругаем: человек чаще всего просто
  // не понял, что сделка уже зафиксирована с обеих сторон.
  "confirm.error.TX_HASH_USED_BY_OWN": {
    ru: "Этот перевод уже зафиксирован в партнёрстве с {partner} от {date}. Сделка засчитана вам обоим — создавать вторую запись не нужно.",
    en: "This transfer is already recorded in your partnership with {partner} from {date}. It counts for both of you — no need to create a second entry.",
  },
  "confirm.error.TX_HASH_USED_BY_OWN_SHORT": {
    ru: "Этот перевод уже зафиксирован в одном из ваших партнёрств. Создавать вторую запись не нужно.",
    en: "This transfer is already recorded in one of your partnerships. No need to create a second entry.",
  },
  // Раздел 3, случай B — строго и БЕЗ деталей чужой сделки.
  "confirm.error.TX_HASH_ALREADY_USED": {
    ru: "Этот хеш уже использован в другом партнёрстве.",
    en: "This hash is already used in another partnership.",
  },
  "confirm.txNetworkLabel": { ru: "Сеть транзакции", en: "Transaction network" },
  "confirm.txNetworkPlaceholder": { ru: "Выберите сеть…", en: "Select network…" },
  "confirm.flagFraudLabel": { ru: "Отметить как проблемную сделку (анти-фрод флаг)", en: "Flag as a problematic deal (anti-fraud flag)" },
  // Средняя точка вместо длинного тире: с тире текст 279px при 276px
  // доступной ширины и переносится на вторую строку. Короткое тире
  // влезает с запасом в 1px — ненадёжно, точка даёт 5px и совпадает с
  // разделителем, принятым в макетах.
  "confirm.submit": { ru: "Отправить на подтверждение · шаг 1", en: "Send for confirmation · step 1" },
  "confirm.submitting": { ru: "Отправляем…", en: "Sending…" },
  "confirm.sentOk": { ru: "Заявка отправлена. Ждём подтверждения от контрагента.", en: "Request sent. Waiting for the counterparty to confirm." },
  "confirm.error.SELF_PARTNERSHIP": { ru: "Нельзя подтвердить партнёрство с самим собой.", en: "You can't confirm a partnership with yourself." },
  "confirm.error.RATE_LIMITED": { ru: "Заявка с этим человеком уже отправлялась за последние 24 часа.", en: "A request to this person was already sent in the last 24 hours." },
  "confirm.error.NO_CONFIRMER_PROFILE": {
    ru: "Этот пользователь ещё не проходил анкету @GamblingCommunitybot — бот не может ему написать.",
    en: "This user hasn't filled in the @GamblingCommunitybot questionnaire yet — the bot can't message them.",
  },
  // Формулировка смягчена по ТЗ (раздел 5): это не окрик, а пояснение.
  "confirm.error.INVALID_NETWORK": {
    ru: "Укажите сеть — это нужно для проверки хеша.",
    en: "Please select the network — it's needed to verify the hash.",
  },
  "confirm.error.INVALID_TYPE": {
    ru: "Выберите тип партнёрства — «Сделка» или «Найм».",
    en: "Choose the partnership type — Deal or Hire.",
  },
  "confirm.error.COMPANY_SUBSCRIPTION_REQUIRED": {
    ru: "Действовать от лица компании можно только с активной подпиской кабинета «Компания». Оформить её можно в разделе «Подписка».",
    en: "Acting on behalf of a company requires an active Company cabinet subscription. You can get it in the Subscription tab.",
  },
  "confirm.error.generic": { ru: "Не получилось отправить заявку.", en: "Couldn't send the request." },
  "confirm.error.DAILY_REQUEST_LIMIT_REACHED": {
    ru: "Дневной лимит новых заявок исчерпан. Обновится {date}.",
    en: "Daily limit of new requests reached. Resets on {date}.",
  },

  // Оценка партнёрства, Шаг 2 — отдельный экран (28.08.2026, макет "07 ·
  // Сделки — шаг 2 (оценка)", Untitled-10). Раньше оценка была маленьким
  // виджетом внутри строки "Мой рейтинг" (RateWidget, Shared.jsx) —
  // отдельного экрана, доступного с таба "Подтвердить", не было вообще.
  // Бэкенд для списка "ждут оценки" уже существовал неиспользуемым
  // (GET /api/partnerships/pending_ratings, guro_id_api.py) — просто не
  // был подключён ни к одному экрану.
  "confirm.pendingRatingsTitle": { ru: "Ждут вашей оценки", en: "Awaiting your rating" },
  "confirm.rate.title": { ru: "Оценить партнёрство", en: "Rate the partnership" },
  "confirm.rate.stepLabel": {
    ru: "Шаг 2 из 2 — оценка (доступна после подтверждения шага 1 обеими сторонами)",
    en: "Step 2 of 2 — rating (available once both sides confirm step 1)",
  },
  "confirm.rate.hint": {
    ru: "Партнёрство уже подтверждено — теперь можно оставить независимую оценку. Ваша оценка скрыта 14 дней и не видна собеседнику. Если за это время он тоже оставит оценку — обе публикуются одновременно. Если нет — ваша публикуется по истечении срока. Так никто не может занизить оценку в отместку.",
    en: "The partnership is already confirmed — now you can leave an independent rating. Your rating is hidden for 14 days and not visible to the other side. If they also rate within that time — both are published at once. If not — yours is published once the period ends. This way no one can retaliate by lowballing a rating.",
  },
  "confirm.rate.partnershipLabel": { ru: "Партнёрство", en: "Partnership" },
  "rating.confirmedOn": { ru: "подтверждено {date}", en: "confirmed {date}" },
  "confirm.rate.verdictLabel": { ru: "Ваша оценка", en: "Your rating" },
  // Короткие подписи КНОПОК (отличаются от длинных rating.verdict.* —
  // те остаются как есть, используются в пояснительном тексте ниже и в
  // других местах, напр. PartnerRow "Ваша оценка: ✅ Успешно").
  "confirm.rate.verdictBtn.nuance": { ru: "Нюансы", en: "Nuances" },
  "confirm.rate.verdictBtn.problematic": { ru: "Проблема", en: "Problem" },
  "confirm.rate.commentRule": {
    ru: "Комментарий обязателен, если выбрано «Были нюансы» или «Проблемная сделка». При «Успешно» можно оставить пустым.",
    en: "A comment is required if you choose \"Had nuances\" or \"Problematic deal\". For \"Success\" it can be left empty.",
  },
  "confirm.rate.commentLabel": {
    ru: "Комментарий (обязателен при нюансах и проблемной сделке)",
    en: "Comment (required for nuances and problematic deals)",
  },
  "confirm.rate.commentPlaceholder": { ru: "Опишите, что пошло не так и почему", en: "Describe what went wrong and why" },
  "confirm.rate.commentRequired": { ru: "Комментарий обязателен для этой оценки.", en: "A comment is required for this rating." },
  "confirm.rate.footerNote": {
    ru: "Антифрод-механизм: оценки скрыты 14 дней и публикуются только одновременно (если хоть один участник ответит взаимностью) — это защищает от мести за честный отзыв.",
    en: "Anti-fraud mechanism: ratings are hidden for 14 days and published only simultaneously (if at least one participant reciprocates) — this protects against retaliation for an honest review.",
  },
  "confirm.rate.submitBtn": { ru: "Опубликовать оценку", en: "Publish rating" },
  "confirm.rate.submitting": { ru: "Публикуем…", en: "Publishing…" },
  "confirm.rate.sentOk": { ru: "Оценка сохранена.", en: "Rating saved." },
  "confirm.rate.loadError": { ru: "Не удалось загрузить партнёрство.", en: "Couldn't load the partnership." },

  // "История партнёрств" (28.08.2026, макет "08 · История партнёрств",
  // Untitled-11) — ссылка с таба "Подтвердить" на уже существующий список
  // (тот же, что в "Профиль -> Мой рейтинг", PartnerRow/PartnersList,
  // Shared.jsx) — тут просто НОВАЯ точка входа со сводкой счётчиков по
  // вердиктам, которой раньше не было нигде.
  "confirm.historyLink": { ru: "История партнёрств", en: "Partnership history" },
  "confirm.history.title": { ru: "История партнёрств", en: "Partnership history" },
  "confirm.history.successLabel": { ru: "успешных", en: "successful" },
  "confirm.history.nuanceLabel": { ru: "с нюансами", en: "with nuances" },
  "confirm.history.problematicLabel": { ru: "проблемных", en: "problematic" },
  "confirm.history.allTime": { ru: "за всё время", en: "all time" },
  "confirm.history.hint": {
    ru: "Отзыв виден только после того, как обе стороны его оставят (или истекут 14 дней). Удалить можно только собственный текст.",
    en: "A review is visible only after both sides leave one (or after 14 days pass). You can only delete your own text.",
  },

  // --- Подписка ---
  "subscribe.titleGuro": { ru: "Подписка GURO ID", en: "GURO ID subscription" },
  "subscribe.titleRecruiter": { ru: "Подписка на кабинет рекрутера", en: "Recruiter cabinet subscription" },
  "subscribe.titleCompany": { ru: "Подписка на кабинет компании", en: "Company cabinet subscription" },
  "subscribe.active": { ru: "Подписка активна", en: "Subscription active" },
  "subscribe.activeUntilDate": { ru: "до {date}", en: "until {date}" },
  "subscribe.daysLeft": { ru: "осталось {count} {unit}", en: "{count} {unit} left" },
  // Обзор "других" подписок на табе "Подписка" (28.08.2026) — Рекрутер и
  // Компания живут в СВОИХ кабинетах, тут только статус + переход туда.
  "subscriptions.otherTitle": { ru: "Другие подписки", en: "Other subscriptions" },
  "subscriptions.activeUntil": { ru: "Активна до {date}", en: "Active until {date}" },
  "subscriptions.notSubscribed": { ru: "Не оформлена", en: "Not subscribed" },
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
  // Чек-листы "что даёт подписка" для кабинетов (05.09.2026) — разобраны
  // из утверждённых описаний тарифов (tariffs.product.*.blurb), чтобы
  // формулировки не разошлись с экраном «Тарифы».
  "subscribe.benefitRecruiter.showcase": { ru: "Отдельная витрина рекрутера", en: "Separate recruiter showcase" },
  "subscribe.benefitRecruiter.vacancies": { ru: "Публикация вакансий на общей доске", en: "Posting vacancies on the shared board" },
  "subscribe.benefitRecruiter.candidates": { ru: "Поиск кандидатов по вертикали и грейду", en: "Candidate search by vertical and grade" },
  "subscribe.benefitRecruiter.hire": { ru: "Отклики и подтверждение найма", en: "Responses and hire confirmation" },
  "subscribe.benefitCompany.brand": { ru: "Бренд-страница компании", en: "Company brand page" },
  "subscribe.benefitCompany.recruiter": { ru: "Весь функционал рекрутера от лица бренда", en: "Full recruiter functionality on behalf of the brand" },
  "subscribe.benefitCompany.teamBasic": { ru: "Команда до 5 участников", en: "Team of up to 5 members" },
  "subscribe.benefitCompany.teamPro": { ru: "Команда до 15–20 участников", en: "Team of up to 15–20 members" },
  "subscribe.benefitCompany.limitsPro": { ru: "Увеличенные лимиты активности", en: "Higher activity limits" },
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
  "subscribe.economy": { ru: "экономия {amount} звёзд", en: "save {amount} Stars" },

  // Чек-лист "Что даёт подписка" + продление (28.08.2026, макет "10 ·
  // Подписка", Untitled-13) — только product="guro_id" пока, см.
  // SubscribeScreen.jsx::GURO_BENEFITS.
  "subscribe.benefitsTitle": { ru: "Что даёт подписка", en: "What the subscription gives you" },
  "subscribe.benefit.privacy": {
    ru: "Видны рейтинг и стаж других участников — независимо от их настроек приватности",
    en: "See other members' rating and tenure — regardless of their privacy settings",
  },
  "subscribe.benefit.partnerships": {
    ru: "Ваши партнёрства видны всем: это подтверждает вашу репутацию",
    en: "Your partnerships are visible to everyone: this confirms your reputation",
  },
  "subscribe.benefit.search": {
    ru: "Поиск по вертикалям и категориям, а не только по юзернейму",
    en: "Search by vertical and category, not just by username",
  },
  "subscribe.benefit.priority": {
    ru: "Приоритет в выдаче при равном рейтинге",
    en: "Priority in listings when ratings are equal",
  },
  "subscribe.renewSectionTitle": { ru: "Продлить", en: "Renew" },
  "subscribe.bestValueBadge": { ru: "Выгодно", en: "Best value" },
  "subscribe.renewStars": { ru: "Продлить · {price} Telegram Stars", en: "Renew · {price} Telegram Stars" },
  "subscribe.payStars": { ru: "Оформить · {price} Telegram Stars", en: "Subscribe · {price} Telegram Stars" },
  "subscribe.preparingInvoice": { ru: "Готовим счёт…", en: "Preparing invoice…" },
  "subscribe.payCrypto": { ru: "Оплатить · ${amount} {asset}", en: "Pay · ${amount} {asset}" },
  "subscribe.renewCrypto": { ru: "Продлить · ${amount} {asset}", en: "Renew · ${amount} {asset}" },
  "subscribe.orPayStars": { ru: "или {price} Telegram Stars", en: "or {price} Telegram Stars" },
  "subscribe.orStars": { ru: "или {price}", en: "or {price}" },
  "subscribe.economyUsd": { ru: "экономия ${amount}", en: "save ${amount}" },
  "subscribe.firstDayBadge": { ru: "-{pct}% сегодня", en: "-{pct}% today" },
  "subscribe.starsError": { ru: "Не получилось создать счёт. Попробуйте ещё раз.", en: "Couldn't create an invoice. Please try again." },
  "subscribe.cryptoError": { ru: "Не получилось создать крипто-счёт. Попробуйте ещё раз.", en: "Couldn't create a crypto invoice. Please try again." },

  // --- Кабинет рекрутера ---
  "recruiter.title": { ru: "Кабинет рекрутера", en: "Recruiter cabinet" },
  // Бейдж-подсказка "Кабинет: Рекрутер" (28.08.2026) — см. WorkspaceCabinetBadge, Shared.jsx.
  "workspace.badge.recruiter": { ru: "Кабинет: Рекрутер", en: "Cabinet: Recruiter" },
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
  // Поле-ссылка снято 06.09.2026, ключи оставлены неиспользуемыми:
  // логотип теперь только файлом, см. recruiter.logoInSettings.
  "recruiter.logoInSettings": {
    ru: "Логотип: нажмите на аватар в шапке кабинета и выберите файл из галереи. Квадрат, от 256×256, PNG/JPG/WEBP, до 3 МБ.",
    en: "Logo: tap the avatar at the top of the cabinet and pick a file from your gallery. Square, at least 256×256, PNG/JPG/WEBP, up to 3 MB.",
  },
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
  // 28.08.2026 (макет "11 · Рекрутер — главный экран"): короткий "HR" —
  // бейдж теперь маленькая плашка на аватаре, "HR / Рекрутер" туда не
  // помещался.
  "recruiter.roleBadge": { ru: "HR", en: "HR" },
  "recruiter.modeLabel": { ru: "Режим: Рекрутер", en: "Mode: Recruiter" },
  "recruiter.settingsBtn": { ru: "Настройки", en: "Settings" },
  "recruiter.characteristic.title": { ru: "Характеристика", en: "Characteristic" },
  "recruiter.characteristic.hires": { ru: "Успешных наймов", en: "Successful hires" },
  "recruiter.characteristic.vacancies": { ru: "Активных вакансий", en: "Active vacancies" },
  "recruiter.characteristic.responses": { ru: "Откликов за 7 дней", en: "Responses (7 days)" },
  "recruiter.characteristic.tenure": { ru: "Стаж в роли, дней", en: "Days in role" },
  "recruiter.activity.label": { ru: "Статус активности", en: "Activity status" },
  // Заголовки карточек кабинета (04.09.2026, сверка с макетом
  // "11 · Кабинет Рекрутер" — там у каждой карточки есть свой заголовок).
  "recruiter.quickActions.title": { ru: "Быстрые действия", en: "Quick actions" },
  "company.quickActions.title": { ru: "Быстрые действия", en: "Quick actions" },
  "recruiter.communication.title": { ru: "Коммуникация", en: "Communication" },
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
  // Фильтры "Поиск кандидатов" (27.08.2026, ТЗ "экраны по ТЗ от 23.08").
  // 28.08.2026 (макет "12 · Рекрутер — Поиск кандидатов", Untitled-15):
  // поле "Юзернейм" на самом деле уже поддерживает и свободное описание
  // (тот же q= на бэкенде, что у поиска по описанию — просто текст экрана
  // раньше не отражал это), макет явно подписывает оба варианта разом.
  "recruiter.candidates.usernameLabel": { ru: "Юзернейм или свободное описание", en: "Username or free-text description" },
  "recruiter.candidates.usernamePlaceholder": { ru: "Например: affiliate manager Кипр", en: "E.g.: affiliate manager Cyprus" },
  "recruiter.candidates.usernameNotFound": { ru: "Пользователь с таким юзернеймом не найден.", en: "No user with this username." },
  "recruiter.candidates.verticalLabel": { ru: "1 · Вертикаль", en: "1 · Vertical" },
  "recruiter.candidates.gradeLabel": { ru: "2 · Грейд — зависит от вертикали", en: "2 · Grade — depends on vertical" },
  "recruiter.candidates.positionLabel": {
    ru: "3 · Должность — зависит от вертикали и грейда",
    en: "3 · Position — depends on vertical and grade",
  },
  "recruiter.candidates.positionPlaceholder": { ru: "Любая должность", en: "Any position" },
  "recruiter.candidates.lookingOnlyLabel": { ru: "Только те, кто ищет работу", en: "Only those looking for work" },
  "recruiter.candidates.topRatingLabel": { ru: "Сначала высокий рейтинг", en: "Highest rating first" },
  // Живой счётчик (28.08.2026) — обновляется при каждой смене фильтра, до
  // нажатия (см. GET /api/candidates/count, guro_id_api.py). count=null,
  // пока ещё не посчитан (только что сменили фильтр) — тогда просто
  // "Показать кандидатов" без числа.
  "recruiter.candidates.submitBtn": { ru: "Показать кандидатов", en: "Show candidates" },
  "recruiter.candidates.submitBtnCount": { ru: "Показать {count} кандидатов", en: "Show {count} candidates" },
  "recruiter.candidates.foundTruncated": {
    ru: "Показано {n} — уточните фильтры, чтобы увидеть нужных",
    en: "Showing {n} — narrow the filters to find the right people",
  },
  "recruiter.candidates.foundCount": { ru: "Найдено: {n}", en: "Found: {n}" },
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
  // Загрузка лого/обложки файлом (28.08.2026) — вместо ссылок текстом.
  "company.upload.coverBtn": { ru: "Добавить обложку", en: "Add cover" },
  "company.upload.coverHint": {
    ru: "Обложка: рекомендуем 1080×300, PNG/JPG/WEBP, до 5 МБ.",
    en: "Cover: recommended 1080×300, PNG/JPG/WEBP, up to 5 MB.",
  },
  "company.upload.logoHint": {
    ru: "Логотип: квадрат, от 256×256, PNG/JPG/WEBP, до 3 МБ.",
    en: "Logo: square, at least 256×256, PNG/JPG/WEBP, up to 3 MB.",
  },
  "recruiter.upload.logoHint": {
    ru: "Логотип: квадрат, от 256×256, PNG/JPG/WEBP, до 3 МБ.",
    en: "Logo: square, at least 256×256, PNG/JPG/WEBP, up to 3 MB.",
  },
  "company.upload.tooLarge": { ru: "Файл слишком большой.", en: "File is too large." },
  "company.upload.unsupported": { ru: "Формат не поддерживается — только PNG, JPG или WEBP.", en: "Unsupported format — PNG, JPG, or WEBP only." },
  "company.upload.error": { ru: "Не получилось загрузить файл.", en: "Couldn't upload the file." },
  "company.settingsBtn": { ru: "Настройки кабинета", en: "Cabinet settings" },
  // Панель "Характеристика" (27.08.2026, ТЗ "экраны по ТЗ от 23.08") —
  // зеркало recruiter.characteristic.*, 2×2 плитки вместо старой строки текста.
  "company.characteristic.title": { ru: "Характеристика", en: "Characteristic" },
  "company.characteristic.hires": { ru: "Успешных наймов", en: "Successful hires" },
  "company.characteristic.vacancies": { ru: "Активных вакансий", en: "Active vacancies" },
  "company.characteristic.responses": { ru: "Откликов за 7 дней", en: "Responses (7 days)" },
  "company.characteristic.members": { ru: "Участников команды", en: "Team members" },
  "company.quickPublish": { ru: "+ Опубликовать вакансию от бренда", en: "+ Post a vacancy as the brand" },
  "company.quickFind": { ru: "Найти кандидата", en: "Find a candidate" },
  "company.activeVacancies": { ru: "Активных вакансий: {n}", en: "Active vacancies: {n}" },
  "company.menu.tariffs": { ru: "Тарифы", en: "Pricing" },
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
  // Раздел 3.0.1: занятое название ведёт к присоединению. Прежняя подсказка
  // «найдите её карточку через поиск» снята — теперь система показывает
  // найденную компанию сама, отправлять человека искать её вручную незачем.
  "company.create.taken": {
    ru: "Компания с таким названием уже зарегистрирована. Вы можете запросить присоединение к ней — отдельная подписка для этого не нужна.",
    en: "A company with this name is already registered. You can request to join it — no separate subscription is needed.",
  },
  "company.create.joinBtn": { ru: "Запросить присоединение", en: "Request to join" },
  "company.create.positionLabel": { ru: "Ваша должность в компании", en: "Your position at the company" },
  "company.create.positionPlaceholder": { ru: "Например: Affiliate Manager", en: "E.g.: Affiliate Manager" },
  "company.create.differentCompany": {
    ru: "Это другая компания — создать свою",
    en: "This is a different company — create my own",
  },
  "company.create.joinSent": {
    ru: "Запрос отправлен. Владелец компании получит уведомление и подтвердит ваше присоединение.",
    en: "Request sent. The company owner will get a notification and confirm your join.",
  },
  "company.join.alreadyRequested": {
    ru: "Вы уже отправляли запрос — дождитесь ответа владельца.",
    en: "You've already sent a request — wait for the owner's reply.",
  },
  "company.join.alreadyMember": {
    ru: "Вы уже состоите в компании.",
    en: "You're already part of a company.",
  },
  "company.join.error": {
    ru: "Не получилось отправить запрос. Попробуйте ещё раз.",
    en: "Couldn't send the request. Please try again.",
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
  // 29.08.2026 (макет "17b · Компания — только что создана", Untitled-21) —
  // отдельным абзацем ДО инструкции про почту: раньше нигде явно не
  // объяснялось, что видимость компании и бейдж верификации — независимые
  // вещи (видна сразу, бейдж только статус, кабинет и без него рабочий).
  "company.verify.visibilityHint": {
    ru: "Компания видна в поиске и на доске сразу после создания — статус выражается только наличием бейджа-галочки. Без бейджа кабинет полностью функционален.",
    en: "The company is visible in search and on the board right after creation — the badge is only a status marker. The cabinet is fully functional without it.",
  },
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
  // Заголовки секций (05.09.2026, сверка с макетом "18 · Компания —
  // Команда": там обе секции видны сразу, а не переключаются табами).
  "team.requestsTitle": { ru: "Входящие запросы", en: "Incoming requests" },
  // Эталонный экран 18: пояснение про две роли под списком участников.
  "team.rolesTitle": {
    ru: "Всего две роли — без градации по функциям",
    en: "Only two roles — no per-function grading",
  },
  "team.rolesOwner": {
    ru: "Владелец: управляет составом команды, передаёт владение, оплачивает подписку — и всё, что может Админ/Рекрутер.",
    en: "Owner: manages the team, transfers ownership, pays for the subscription — plus everything an Admin/Recruiter can do.",
  },
  "team.rolesAdmin": {
    ru: "Админ/Рекрутер: публикует вакансии, ищет кандидатов, подтверждает найм, редактирует бренд-страницу. Реальная должность человека прав не добавляет.",
    en: "Admin/Recruiter: posts vacancies, searches candidates, confirms hires, edits the brand page. A person's actual job title grants no extra rights.",
  },
  "team.membersTitle": { ru: "Участники", en: "Members" },
  "team.membersCounter": { ru: "{count} из {limit}", en: "{count} of {limit}" },
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
  "team.isYou": { ru: "Это вы", en: "That's you" },
  "team.errors.generic": { ru: "Не получилось выполнить действие.", en: "Couldn't complete the action." },
  // 29.08.2026 (макет "18 · Компания — Команда") — проактивное предупреждение
  // при достижении лимита (до неудачного клика "Принять", не после); proLimit
  // захардкожен (=GC.COMPANY_MEMBER_LIMIT_PRO=20 в guro_constants.py) — тот же
  // приём, что и у прочих тарифных чисел в копирайтах приложения.
  "team.limitReachedBanner": {
    ru: "Достигнут лимит участников по тарифу ({limit}/{limit}). Удалите неактивного участника или перейдите на тариф Компания Pro (до {proLimit} участников). Запрос остаётся в очереди.",
    en: "Member limit reached ({limit}/{limit}). Remove an inactive member or upgrade to Company Pro (up to {proLimit} members). The request stays queued.",
  },
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

  // --- Тарифы, единый экран (27.08.2026, ТЗ "экраны по ТЗ от 23.08",
  // "Тарифы") — сводка всех 4 продуктов + таблица лимитов на одном экране,
  // цены живые (см. getPlans), лимиты — статичные MVP-константы
  // (guro_constants.py), как и в самом макете ("MVP — гипотеза цены"). ---
  "tariffs.title": { ru: "Тарифы", en: "Pricing" },
  "tariffs.mvpBadge": { ru: "MVP — гипотеза цены", en: "MVP — price hypothesis" },
  "tariffs.loading": { ru: "Загружаем тарифы…", en: "Loading pricing…" },
  "tariffs.hitBadge": { ru: "ХИТ", en: "POPULAR" },
  "tariffs.perMonth": { ru: " / мес", en: " / mo" },
  "tariffs.perYear": { ru: " / год", en: " / yr" },
  "tariffs.product.guro_id.title": { ru: "Личный Pro", en: "Personal Pro" },
  "tariffs.product.guro_id.blurb": {
    ru: "Рейтинг, история сделок, полный поиск, история партнёрств контрагента.",
    en: "Rating, deal history, full search, counterparty partnership history.",
  },
  "tariffs.product.recruiter.title": { ru: "Рекрутер Pro", en: "Recruiter Pro" },
  "tariffs.product.recruiter.blurb": {
    ru: "Витрина рекрутера, публикация вакансий, поиск кандидатов, отклики, подтверждение найма.",
    en: "Recruiter showcase, posting vacancies, candidate search, responses, hire confirmation.",
  },
  "tariffs.product.company_basic.title": { ru: "Компания Basic", en: "Company Basic" },
  "tariffs.product.company_basic.blurb": {
    ru: "Бренд-страница, весь функционал рекрутера от лица бренда, команда до 5 участников.",
    en: "Brand page, full recruiter functionality on behalf of the brand, team of up to 5.",
  },
  "tariffs.product.company_pro.title": { ru: "Компания Pro", en: "Company Pro" },
  "tariffs.product.company_pro.blurb": {
    ru: "То же + до 15–20 участников и увеличенные лимиты активности.",
    en: "Same, plus up to 15–20 members and higher activity limits.",
  },
  "tariffs.limitsTitle": { ru: "Лимиты", en: "Limits" },
  "tariffs.limits.viewsTitle": { ru: "Просмотры чужих профилей / день", en: "Other profiles viewed / day" },
  "tariffs.limits.viewsValue": {
    ru: "Личный — без лимита · Рекрутер 30 · Компания Basic 30 на участника · Pro 50 на участника",
    en: "Personal — unlimited · Recruiter 30 · Company Basic 30 per member · Pro 50 per member",
  },
  "tariffs.limits.requestsTitle": { ru: "Новые заявки на подтверждение / день", en: "New confirmation requests / day" },
  "tariffs.limits.requestsValue": {
    ru: "Личный 10 · Рекрутер 20 · Компания 30 на аккаунт компании",
    en: "Personal 10 · Recruiter 20 · Company 30 per company account",
  },
  "tariffs.limits.vacanciesTitle": { ru: "Публикация вакансий", en: "Posting vacancies" },
  "tariffs.limits.vacanciesValue": {
    ru: "3 новые / день у всех · активных: Рекрутер 10 · Basic 20 · Pro 50",
    en: "3 new / day for everyone · active: Recruiter 10 · Basic 20 · Pro 50",
  },
  "tariffs.limits.approvalsTitle": { ru: "Одобрение в команду", en: "Team approvals" },
  "tariffs.limits.approvalsValue": { ru: "5 в день, независимо от тарифа", en: "5 per day, regardless of plan" },

  // --- Вакансии (Фаза 4, 12.08.2026; переписано 26.08.2026 под ТЗ
  // "Recruitment — ВАКАНСИИ") ---
  "tab.vacancies": { ru: "Вакансии", en: "Jobs" },
  "vacancies.title": { ru: "Вакансии", en: "Vacancies" },
  "vacancies.hint": {
    ru: "Доска вакансий GURO ID — публикуют подписчики кабинетов Рекрутер и Компания, смотреть может любой с подпиской GURO ID.",
    en: "GURO ID job board — posted by Recruiter and Company cabinet subscribers, visible to any GURO ID subscriber.",
  },
  "vacancies.allVerticals": { ru: "Все", en: "All" },
  "vacancies.publishBtn": { ru: "Опубликовать вакансию", en: "Post a vacancy" },
  "vacancies.upsellText": {
    ru: "Публиковать вакансии могут подписчики кабинета Рекрутер или Компания — оформите в «Профиль».",
    en: "Only Recruiter or Company cabinet subscribers can post vacancies — subscribe under \"Profile\".",
  },
  "vacancies.empty": { ru: "Пока нет активных вакансий по этому фильтру.", en: "No active vacancies match this filter." },
  "vacancies.loadError": { ru: "Не удалось загрузить вакансии.", en: "Couldn't load vacancies." },
  "vacancies.salaryNegotiable": { ru: "По договорённости", en: "Negotiable" },
  "vacancies.applyBtn": { ru: "Откликнуться", en: "Apply" },
  "vacancies.respondSentOk": { ru: "Отклик отправлен", en: "Response sent" },
  "vacancies.respondError.ALREADY_RESPONDED": { ru: "Вы уже откликались на эту вакансию.", en: "You've already applied to this vacancy." },
  "vacancies.respondError.generic": { ru: "Не получилось отправить отклик. Попробуйте ещё раз.", en: "Couldn't send the response. Please try again." },
  "vacancies.tabBoard": { ru: "Доска", en: "Board" },
  "vacancies.tabMine": { ru: "Мои вакансии", en: "My vacancies" },
  // Подписи под плитками верхней навигации (27.08.2026, ТЗ "экраны по ТЗ
  // от 23.08", "Вакансии").
  "vacancies.navBoardHint": { ru: "Все вакансии индустрии", en: "All vacancies in the industry" },
  "vacancies.navMineHint": { ru: "{active} активные · {responses} откликов", en: "{active} active · {responses} responses" },
  "vacancies.mineActiveBadge": { ru: "{active} из {limit} активных", en: "{active} of {limit} active" },
  "vacancies.navResponsesHint": { ru: "Все отклики по вакансиям", en: "All responses to your vacancies" },
  "vacancies.navPublishHint": { ru: "Новая вакансия", en: "New vacancy" },
  "vacancies.mineTitle": { ru: "Мои вакансии", en: "My vacancies" },
  "vacancies.mineEmpty": {
    ru: "У вас пока нет опубликованных вакансий. Опубликуйте первую — она появится на общей доске и станет видна кандидатам.",
    en: "You don't have any published vacancies yet. Publish your first one — it'll appear on the shared board and become visible to candidates.",
  },
  "vacancies.closeBtn": { ru: "Закрыть", en: "Close" },
  "vacancies.statusClosed": { ru: "Закрыта", en: "Closed" },
  // Сегменты статуса над списком своих вакансий (05.09.2026, правка в
  // Figma "P3 · Мои вакансии — сегменты статуса вверху"). Отдельно от
  // vacancies.status.* — там статус одной вакансии ("Активна"), тут
  // фильтр по группе ("Активные").
  "vacancies.mine.filterAll": { ru: "Все", en: "All" },
  "vacancies.mine.filter.active": { ru: "Активные", en: "Active" },
  "vacancies.mine.filter.paused": { ru: "На паузе", en: "Paused" },
  "vacancies.mine.filter.closed": { ru: "Закрытые", en: "Closed" },
  "vacancies.mine.filterEmpty": {
    ru: "В этой группе вакансий нет.",
    en: "No vacancies in this group.",
  },
  "vacancies.status.active": { ru: "Активна", en: "Active" },
  "vacancies.status.paused": { ru: "На паузе", en: "Paused" },
  "vacancies.status.closed": { ru: "Закрыта", en: "Closed" },
  "vacancies.posterRating": { ru: "рейтинг {n}", en: "rating {n}" },
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
  "vacancies.writeBtn": { ru: "Написать", en: "Message" },
  "vacancies.workFormat.remote": { ru: "Удалённо", en: "Remote" },
  "vacancies.workFormat.office": { ru: "Офис", en: "Office" },
  "vacancies.workFormat.hybrid": { ru: "Гибрид", en: "Hybrid" },
  "vacancies.employment.full": { ru: "Полная занятость", en: "Full-time" },
  "vacancies.employment.part": { ru: "Частичная занятость", en: "Part-time" },
  "vacancies.employment.project": { ru: "Проектная работа", en: "Project-based" },
  "vacancies.manage.preview": { ru: "Показать", en: "Preview" },
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
  // Эталонный экран 16.
  "vacancies.responses.filterTitle": {
    ru: "Фильтр по статусу воронки",
    en: "Filter by funnel status",
  },
  "vacancies.responses.hiredNoteTitle": {
    ru: "Статус «Найм подтверждён»",
    en: "The \"Hired\" status",
  },
  "vacancies.responses.hiredNoteText": {
    ru: "Активирует кнопку найма: переход в раздел «Сделки», шаг 1, с заранее заполненными полями — юзернейм кандидата и вертикаль вакансии подставляются сами.",
    en: "It activates the hire button: you go to \"Deals\", step 1, with fields pre-filled — the candidate's username and the vacancy's vertical are inserted automatically.",
  },
  "vacancies.responses.confirmHireBtn": { ru: "Подтвердить найм →", en: "Confirm hire →" },
  // 28.08.2026 (макет "16 · Рекрутер — Отклики (мини-ATS)", Untitled-20) —
  // раньше кнопка подтверждения найма была доступна ДЛЯ ЛЮБОГО отклика
  // независимо от статуса (реальный баг — можно было "подтвердить найм"
  // по только что пришедшему, ещё не рассмотренному отклику). Выноска
  // явно говорит: статус "Найм подтверждён" АКТИВИРУЕТ кнопку — теперь
  // кнопка показывается только при status="hired". Пояснительная карточка
  // ниже списка объясняет почему (сверил с владельцем: список+инлайн-
  // редактирование статуса оставлены как есть, не переделывал в
  // список+деталь с отдельным подэкраном, как на макете — заметно
  // больше работы без явной необходимости).
  "vacancies.responses.hireExplainerTitle": { ru: "Статус «Найм подтверждён»", en: "\"Hired\" status" },
  "vacancies.responses.hireExplainerText": {
    ru: "Активирует кнопку ниже: переход в раздел «Найм», Шаг 1, с предзаполненными полями — юзернейм контрагента из отклика, Вертикаль / Грейд / Должность из данных вакансии.",
    en: "Activates the button below: takes you to the \"Hire\" section, Step 1, with pre-filled fields — the counterparty's username from the response, Vertical / Grade / Position from the vacancy data.",
  },
  "vacancies.responses.today": { ru: "сегодня", en: "today" },
  "vacancies.responses.daysAgo": { ru: "{days} дн. назад", en: "{days}d ago" },
  "vacancies.form.title": { ru: "Опубликовать вакансию", en: "Post a vacancy" },
  "vacancies.form.editTitle": { ru: "Редактировать вакансию", en: "Edit vacancy" },
  "vacancies.form.authorWorkspaceLabel": { ru: "Публиковать от имени", en: "Post as" },
  // 28.08.2026 (макет "14 · Рекрутер — Опубликовать вакансию", Untitled-18):
  // нумерация полей 1/2/3/4/6/7/8/9/10/12 — сохранил ровно ЭТИ номера
  // макета (5 и 11 в нём пропущены — 11 был бы "Контакт для отклика",
  // которого больше нет, см. VACANCY_CONTACT_METHODS; 5, вероятно,
  // относится к чему-то за кадром экспорта — не гадаю, просто оставляю
  // разрыв как в макете, не перенумеровываю подряд).
  "vacancies.form.titleLabel": { ru: "1 · Название позиции *", en: "1 · Job title *" },
  "vacancies.form.titlePlaceholder": { ru: "Например: Senior Product Manager", en: "E.g.: Senior Product Manager" },
  // Умное предупреждение (28.08.2026) — раньше сравнивало название с
  // последней выбранной ПОДСКАЗКОЙ целиком (слишком общее: "разошлось",
  // без объяснения ЧЕМ). Макет явно называет КОНКРЕТНОЕ слово из
  // названия, которое противоречит выбранному грейду — см. detectGrade
  // MismatchWord в VacanciesScreen.jsx.
  "vacancies.form.mismatchWarning": {
    ru: "В названии указано «{word}», а выбран грейд «{grade}» — всё верно? Публикацию не блокируем.",
    en: "The title mentions \"{word}\", but the selected grade is \"{grade}\" — is that intentional? This won't block publishing.",
  },
  "vacancies.form.verticalLabel": { ru: "2 · Вертикаль *", en: "2 · Vertical *" },
  "vacancies.form.gradeLabel": { ru: "3 · Грейд * — зависит от вертикали", en: "3 · Grade * — depends on vertical" },
  "vacancies.form.gradePlaceholder": { ru: "Выберите грейд", en: "Select grade" },
  "vacancies.form.positionLabel": { ru: "4 · Должность * — из справочника", en: "4 · Position * — from the reference list" },
  "vacancies.form.positionPlaceholder": { ru: "Выберите должность", en: "Select position" },
  "vacancies.form.positionOther": { ru: "+ Другое → свободный ввод", en: "+ Other → free text" },
  "vacancies.form.positionOtherPlaceholder": { ru: "Укажите должность", en: "Enter the position" },
  "vacancies.form.locationLabel": { ru: "6 · Гео (необязательно)", en: "6 · Geo (optional)" },
  "vacancies.form.locationPlaceholder": { ru: "Кипр, Лимассол…", en: "Cyprus, Limassol…" },
  "vacancies.form.workFormatLabel": { ru: "7 · Формат работы", en: "7 · Work format" },
  "vacancies.form.employmentLabel": { ru: "8 · Занятость", en: "8 · Employment type" },
  "vacancies.form.salaryLabel": { ru: "10 · Вилка зарплаты (необязательно)", en: "10 · Salary range (optional)" },
  "vacancies.form.salaryFromPlaceholder": { ru: "от, $", en: "from, $" },
  "vacancies.form.salaryToPlaceholder": { ru: "до, $", en: "to, $" },
  "vacancies.form.salaryNegotiableLabel": { ru: "По договорённости (не указывать вилку)", en: "Negotiable (don't show a range)" },
  "vacancies.form.salaryVisibleLabel": { ru: "Показывать сумму всем", en: "Show amount to everyone" },
  "vacancies.form.descriptionLabel": { ru: "9 · Описание и требования (необязательно)", en: "9 · Description and requirements (optional)" },
  "vacancies.form.descriptionPlaceholder": {
    ru: "Можно не заполнять — рейтинг и история говорят за вас",
    en: "You can skip this — your rating and history speak for you",
  },
  "vacancies.form.durationLabel": { ru: "12 · Срок публикации", en: "12 · Listing duration" },
  "vacancies.form.durationDays": { ru: "{days} дней", en: "{days} days" },
  "vacancies.form.langLabel": { ru: "Язык публикации", en: "Posting language" },
  "vacancies.premium.perMonth": { ru: "В МЕСЯЦ", en: "PER MONTH" },
  "vacancies.premium.applyBtn": { ru: "Откликнуться", en: "Apply" },
  // Плашка под премиальной карточкой (04.09.2026, сверка с Figma, фрейм
  // "A2 · Карточка вакансии — компания vs рекрутер"): в макете пояснение
  // про верификацию — ОТДЕЛЬНЫЙ блок под карточкой, а не бейдж внутри неё.
  "vacancies.premium.verifiedTitle": {
    ru: "Проверено сообществом GURO",
    en: "Verified by the GURO community",
  },
  "vacancies.premium.verifiedText": {
    ru: "На основании доступных лицензионных данных. Верификация — привилегия, которая выдаётся по нашему усмотрению и может быть отозвана.",
    en: "Based on available licensing data. Verification is a privilege granted at our discretion and may be revoked.",
  },
  "vacancies.bookmark.add": { ru: "Сохранить вакансию", en: "Save vacancy" },
  "vacancies.bookmark.remove": { ru: "Убрать из сохранённых", en: "Remove from saved" },
  "vacancies.bookmark.filter": { ru: "Только сохранённые", en: "Saved only" },
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

  // Отдельный экран "Приватность профиля" (28.08.2026, макет "09 ·
  // Приватность", Untitled-12) — ProfileHub.jsx -> меню -> PrivacySubscreen.jsx.
  "profile.privacy.menuLabel": { ru: "Приватность", en: "Privacy" },
  "profile.privacy.title": { ru: "Приватность профиля", en: "Profile privacy" },
  "profile.privacy.hint": {
    ru: "Каждое поле можно скрыть от чужого поиска по отдельности. Это не влияет на Рейтинг и Стаж — см. отдельное правило ниже.",
    en: "Each field can be hidden from others' search individually. This doesn't affect Rating and Tenure — see the separate rule below.",
  },
  "profile.privacy.lockedTitle": { ru: "Рейтинг и Стаж — без переключателя", en: "Rating and Tenure — no toggle" },
  "profile.privacy.lockedText": {
    ru: "Эти два поля всегда видны участникам с активной подпиской GURO ID и не скрываются приватностью — они формируют доверие в комьюнити и не должны обходиться настройками.",
    en: "These two fields are always visible to members with an active GURO ID subscription and can't be hidden by privacy settings — they build trust in the community and shouldn't be bypassable.",
  },

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
