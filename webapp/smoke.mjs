// Dev-only smoke test: строит dist/ (запустить `npm run build` заранее),
// поднимает vite preview, мокает /api/* и Telegram.WebApp, кликает по всем
// табам, ловит console-ошибки, сохраняет скриншоты каждого экрана. НЕ часть
// продакшн-сборки. Перед запуском: `npm install --no-save playwright &&
// npx playwright install chromium` (не сохраняем в package.json — незачем
// таскать браузер в зависимостях мини-приложения).
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const PORT = 4173;
const BASE = `http://localhost:${PORT}`;

const ME_PAYLOAD = {
  user_id: 100,
  username: "initiator",
  name: "Pavel Test",
  company: "GURO Labs",
  vertical: "iGaming",
  profession: "Product Manager",
  linkedin: "linkedin.com/in/pavel-test",
  looking_for: "ищу партнёров по трафику",
  cv_text: "5 лет в iGaming, руководил командой из 10 человек",
  website: "pavel-test.example",
  offering: "могу подключить трафик, есть база рекламодателей",
  // Расширение "Моё CV" (12.08.2026) — все новые поля пустые в фикстуре,
  // заполняются шагами теста (см. step "cv-expansion-fields").
  cv_profession: null,
  cv_verticals: null,
  cv_grade: null,
  cv_location: null,
  cv_relocation_ready: null,
  cv_polygraph_consent: null,
  cv_salary_from: null,
  cv_salary_to: null,
  cv_salary_negotiable: false,
  cv_skills: null,
  cv_languages: null,
  cv_certifications: null,
  cv_experience: [],
  work_status: null,
  verified_screening: true,
  joined_community_at: "2026-01-01 00:00:00",
  days_in_community: 221,
  // «Рейтинг сгорает без подписки» — is_subscribed=false у ME_PAYLOAD ниже
  // ЗНАЧИТ реальный бэкенд отдал бы null/[] здесь. Реальные числа держим в
  // SUBSCRIBED_EXTRAS и подмешиваем их отдельным шагом теста (см.
  // profile-subscription-gate), а не тут — иначе мок разъедется с бэкендом.
  reputation_score: null,
  confirmed_partnerships: null,
  partners: [],
  subscription_status: "inactive",
  subscription_expires_at: null,
  is_subscribed: false,
  unread_messages: 2,
  privacy: {
    show_name: false,
    show_company: false,
    show_vertical: false,
    show_profession: false,
    show_tenure: false,
    show_reputation: false,
    show_cv: false,
    show_contacts: false,
    show_offers: false,
  },
};

const SUBSCRIBED_EXTRAS = {
  reputation_score: 87.5,
  confirmed_partnerships: 2,
  partners: [
    {
      user_id: 200,
      username: "bob",
      name: "Bob Partner",
      confirmed_at: "2026-07-01 12:00:00",
      counts_toward_rating: true,
      vertical: "iGaming",
      geo: "Malta",
      offer: "Помог с интеграцией платёжки",
      review: "Быстро и по делу",
      amount_received: 800,
      amount_paid: null,
      initiator_id: 100,
    },
    {
      user_id: 300,
      username: "carl",
      name: null,
      confirmed_at: "2026-08-01 09:30:00",
      counts_toward_rating: false,
    },
  ],
};

const SEARCH_LOCKED = {
  mode: "profile",
  user_id: 555,
  username: "target",
  name: "Target User",
  reputation_score: 61.2,
  confirmed_partnerships: 1,
  work_status: "looking",
  locked: true,
};

// Разблокированный профиль (11.08.2026) — для проверки кнопки "Написать"
// (появляется только когда locked=false, см. ResultCard в SearchScreen.jsx).
const SEARCH_UNLOCKED = {
  mode: "profile",
  user_id: 888,
  username: "unlockeduser",
  name: "Unlocked User",
  company: "Acme",
  vertical: "iGaming",
  reputation_score: 70,
  confirmed_partnerships: 2,
  work_status: null,
  days_in_community: 100,
  locked: false,
  partners: [],
  has_recruiter_profile: true,
  // CV чужого профиля (16.08.2026) — проверка, что CvReadOnly реально
  // рендерится в ResultCard, не только в собственном "Посмотреть моё CV".
  cv_profession: "Head of Partnerships",
  cv_grade: "Lead (8+ years)",
  cv_location: "Malta",
  cv_skills: "Affiliate marketing, negotiations",
};

// Мок кабинета рекрутера (Фаза 3, 12.08.2026) — простое in-memory
// состояние своего кабинета + статичная карточка чужого (unlockeduser).
let recruiterState = {
  workspace: "recruiter",
  user_id: 100,
  name: null, company: null, vertical: null, profession: null,
  cv_text: null, website: null, offering: null,
  recruiter_subscription_status: "inactive",
  recruiter_subscription_expires_at: null,
  is_recruiter_subscribed: false,
  privacy: {
    show_name: false, show_company: false, show_vertical: false, show_profession: false,
    show_tenure: false, show_reputation: false, show_cv: false, show_contacts: false, show_offers: false,
  },
};

let privacyState = { ...ME_PAYLOAD.privacy };
// Мок личных сообщений (Фаза 1) — простое in-memory состояние на весь прогон.
let messageThreads = [];
let messagesByUser = {};

const server = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], {
  stdio: "pipe",
});
server.stdout.on("data", (d) => process.stdout.write(`[preview] ${d}`));
server.stderr.on("data", (d) => process.stderr.write(`[preview] ${d}`));

await sleep(1500);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 420, height: 860 } });

const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

await page.addInitScript(() => {
  window.Telegram = {
    WebApp: {
      initData: "mock_init_data",
      ready() {},
      expand() {},
      setHeaderColor() {},
      setBackgroundColor() {},
      HapticFeedback: {
        impactOccurred() {},
        notificationOccurred() {},
        selectionChanged() {},
      },
      openInvoice(url, cb) {
        cb && cb("paid");
      },
      openTelegramLink(url) {
        window.__openedLinks = window.__openedLinks || [];
        window.__openedLinks.push(url);
      },
    },
  };
});

await page.route("**/api/me**", (route) => {
  const url = new URL(route.request().url());
  if (url.searchParams.get("workspace") === "recruiter") {
    return route.fulfill({ json: recruiterState });
  }
  return route.fulfill({ json: { ...ME_PAYLOAD, privacy: privacyState } });
});
await page.route("**/api/recruiter/profile", async (route) => {
  const body = route.request().postDataJSON();
  recruiterState[body.field] = body.value;
  route.fulfill({ json: { [body.field]: body.value } });
});
await page.route("**/api/recruiter/privacy", async (route) => {
  const body = route.request().postDataJSON();
  recruiterState.privacy = { ...recruiterState.privacy, [body.field]: body.value };
  route.fulfill({ json: recruiterState.privacy });
});
await page.route("**/api/subscribe", (route) =>
  route.fulfill({ json: { invoice_link: "https://t.me/fake_invoice_link" } }),
);
// Универсальный поиск (10.08.2026): один эндпоинт /api/search?q= — точный
// юзернейм "target" отдаёт тизер-профиль (mode=profile), любой другой
// текст трактуется как описание (mode=list, платный directory-режим).
await page.route("**/api/search**", (route) => {
  const url = new URL(route.request().url());
  if (url.searchParams.get("workspace") === "recruiter") {
    return route.fulfill({
      json: {
        mode: "profile", workspace: "recruiter", locked: false,
        user_id: 888, username: "unlockeduser", name: "Unlocked Recruiter",
        company: "Acme Talent", vertical: "iGaming", profession: "Talent Lead",
        cv_text: "Нанимаю продакт-менеджеров и байеров.", website: "acme-talent.example",
        offering: "Быстрый подбор под iGaming",
      },
    });
  }
  if (url.searchParams.get("user_id")) {
    return route.fulfill({ json: SEARCH_LOCKED });
  }
  const q = url.searchParams.get("q") || "";
  if (q === "target") {
    return route.fulfill({ json: SEARCH_LOCKED });
  }
  if (q === "unlockeduser") {
    return route.fulfill({ json: SEARCH_UNLOCKED });
  }
  const vertical = url.searchParams.get("vertical") || "";
  if (vertical) {
    if (!ME_PAYLOAD.is_subscribed) {
      return route.fulfill({ status: 402, json: { error: "SUBSCRIPTION_REQUIRED" } });
    }
    const top = url.searchParams.get("top") === "1";
    const results = [
      {
        user_id: 710, username: "gambler_low", name: "Low Rep Gambler", vertical,
        profession: "Manager", company: null, work_status: null,
        reputation_score: 55.0, confirmed_partnerships: 1,
      },
      {
        user_id: 720, username: "gambler_high", name: "High Rep Gambler", vertical,
        profession: "Director", company: null, work_status: "looking",
        reputation_score: 91.0, confirmed_partnerships: 5,
      },
    ];
    if (top) results.sort((a, b) => b.reputation_score - a.reputation_score);
    return route.fulfill({ json: { mode: "list", results, truncated: false } });
  }
  if (!ME_PAYLOAD.is_subscribed) {
    return route.fulfill({ status: 402, json: { error: "SUBSCRIPTION_REQUIRED" } });
  }
  return route.fulfill({
    json: {
      mode: "list",
      results: [
        {
          user_id: 700, username: "cryptoguy", name: "Crypto Guy", vertical: "Крипто",
          profession: "Manager", company: null, work_status: "looking",
          reputation_score: 72.0, confirmed_partnerships: 3,
        },
      ],
      truncated: false,
    },
  });
});
await page.route("**/api/privacy", async (route) => {
  const body = route.request().postDataJSON();
  privacyState = { ...privacyState, [body.field]: body.value };
  route.fulfill({ json: privacyState });
});
await page.route("**/api/profile", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD[body.field] = body.value;
  route.fulfill({ json: { [body.field]: body.value } });
});
// Расширение "Моё CV" (12.08.2026) — простые in-memory моки /api/cv/*, тот
// же приём, что /api/profile выше.
let cvExperience = [];
let cvExperienceNextId = 1;
await page.route("**/api/cv/field", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD[body.field] = body.value;
  route.fulfill({ json: { [body.field]: body.value } });
});
await page.route("**/api/cv/profession", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD.cv_profession = body.value;
  route.fulfill({ json: { cv_profession: body.value } });
});
await page.route("**/api/cv/grade", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD.cv_grade = body.value;
  route.fulfill({ json: { cv_grade: body.value } });
});
await page.route("**/api/cv/flag", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD[body.field] = body.value;
  route.fulfill({ json: { [body.field]: body.value } });
});
await page.route("**/api/cv/salary", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD.cv_salary_from = body.salary_from;
  ME_PAYLOAD.cv_salary_to = body.salary_to;
  ME_PAYLOAD.cv_salary_negotiable = body.negotiable;
  route.fulfill({
    json: {
      cv_salary_from: body.salary_from, cv_salary_to: body.salary_to, cv_salary_negotiable: body.negotiable,
    },
  });
});
await page.route("**/api/cv/experience/*/delete", async (route) => {
  const id = Number(route.request().url().match(/\/experience\/(\d+)\/delete/)[1]);
  cvExperience = cvExperience.filter((e) => e.id !== id);
  ME_PAYLOAD.cv_experience = cvExperience;
  route.fulfill({ json: { status: "deleted" } });
});
await page.route("**/api/cv/experience", async (route) => {
  const body = route.request().postDataJSON();
  const entry = { id: cvExperienceNextId++, ...body };
  cvExperience = [entry, ...cvExperience];
  ME_PAYLOAD.cv_experience = cvExperience;
  route.fulfill({ json: entry });
});
await page.route("**/api/work_status", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD.work_status = body.status;
  route.fulfill({ json: { work_status: body.status } });
});
await page.route("**/api/qr", (route) =>
  route.fulfill({ json: { deeplink: "https://t.me/GamblingCommunitybot?start=guro_100" } }),
);
await page.route("**/api/invite_link", (route) =>
  route.fulfill({ json: { link: "https://t.me/GamblingCommunitybot?start=ref_100_1" } }),
);
await page.route("**/api/partnerships", (route) =>
  route.fulfill({ json: { id: 999, status: "pending" } }),
);
await page.route("**/api/messages/with/**", (route) => {
  const url = new URL(route.request().url());
  const otherId = Number(url.pathname.split("/").pop());
  route.fulfill({
    json: {
      other_user_id: otherId,
      other_name: otherId === 888 ? "Unlocked User" : `User ${otherId}`,
      other_username: otherId === 888 ? "unlockeduser" : `user${otherId}`,
      messages: messagesByUser[otherId] || [],
      can_send_first: true,
    },
  });
});
await page.route("**/api/messages", async (route) => {
  const req = route.request();
  if (req.method() === "GET") {
    return route.fulfill({ json: { threads: messageThreads } });
  }
  const reqBody = req.postDataJSON();
  const createdAt = new Date().toISOString();
  const id = messagesByUser[reqBody.recipient_id]?.length
    ? messagesByUser[reqBody.recipient_id].length + 1
    : 1;
  messagesByUser[reqBody.recipient_id] = [
    ...(messagesByUser[reqBody.recipient_id] || []),
    { id, sender_id: ME_PAYLOAD.user_id, body: reqBody.body, created_at: createdAt, mine: true },
  ];
  const preview = {
    other_user_id: reqBody.recipient_id,
    other_name: reqBody.recipient_id === 888 ? "Unlocked User" : `User ${reqBody.recipient_id}`,
    other_username: reqBody.recipient_id === 888 ? "unlockeduser" : `user${reqBody.recipient_id}`,
    last_message: reqBody.body,
    last_message_at: createdAt,
    unread_count: 0,
  };
  const idx = messageThreads.findIndex((t) => t.other_user_id === reqBody.recipient_id);
  if (idx >= 0) messageThreads[idx] = preview;
  else messageThreads.push(preview);
  route.fulfill({ json: { id, created_at: createdAt } });
});
await page.route("**/api/plans**", (route) => {
  const url = new URL(route.request().url());
  if (url.searchParams.get("product") === "recruiter") {
    return route.fulfill({
      json: {
        plans: {
          monthly: { label: "Месяц", duration_days: 30, stars_price: 800, crypto_price_usd: 12, crypto_asset: "USDT" },
          yearly: {
            label: "Год", duration_days: 365, stars_price: 7000, stars_price_full: 9600,
            crypto_price_usd: 105, crypto_asset: "USDT",
          },
        },
        crypto_enabled: true,
      },
    });
  }
  return route.fulfill({
    json: {
      plans: {
        monthly: { label: "Месяц", duration_days: 30, stars_price: 650, crypto_price_usd: 9.75, crypto_asset: "USDT" },
        yearly: {
          label: "Год", duration_days: 365, stars_price: 6600, stars_price_full: 7800,
          crypto_price_usd: 99, crypto_asset: "USDT",
        },
      },
      crypto_enabled: true,
    },
  });
});
// Вакансии (Фаза 4, 12.08.2026) — единый обработчик разбирает путь сам,
// чтобы не воевать за приоритет между **/api/vacancies** и более узкими
// /mine, /<id>/close (Playwright матчит по своим правилам, проще не рисковать).
let vacancies = [
  {
    id: 1, author_id: 100, company: "GURO Labs", recruiter_name: "Init HR",
    title: "Existing QA Lead", vertical: "Betting", seniority: "Lead", location: "Remote",
    remote: true, relocation: false, salary_from: null, salary_to: null, salary_negotiable: true,
    description: "Уже существующая вакансия для проверки списка", lang: "ru", status: "active",
    created_at: "2026-08-01 10:00:00",
  },
];
await page.route("**/api/vacancies**", (route) => {
  const req = route.request();
  const url = new URL(req.url());
  const path = url.pathname;

  if (path === "/api/vacancies/mine") {
    return route.fulfill({ json: { vacancies } });
  }
  const closeMatch = path.match(/^\/api\/vacancies\/(\d+)\/close$/);
  if (closeMatch) {
    const v = vacancies.find((x) => x.id === Number(closeMatch[1]));
    if (v) v.status = "closed";
    return route.fulfill({ json: { status: "closed" } });
  }
  if (req.method() === "POST") {
    const body = req.postDataJSON();
    const nv = {
      id: vacancies.length + 1, author_id: 100, company: "GURO Labs", recruiter_name: "Init HR",
      title: body.title, vertical: body.vertical, seniority: body.seniority, location: body.location,
      remote: !!body.remote, relocation: !!body.relocation,
      salary_from: body.salary_from, salary_to: body.salary_to, salary_negotiable: !!body.salary_negotiable,
      description: body.description, lang: body.lang, status: "active", created_at: new Date().toISOString(),
    };
    vacancies.push(nv);
    return route.fulfill({ json: nv });
  }
  if (!ME_PAYLOAD.is_subscribed) {
    return route.fulfill({ status: 402, json: { error: "SUBSCRIPTION_REQUIRED" } });
  }
  const lang = url.searchParams.get("lang");
  const vertical = url.searchParams.get("vertical");
  let results = vacancies.filter((v) => v.status === "active");
  if (lang) results = results.filter((v) => v.lang === lang);
  if (vertical) results = results.filter((v) => v.vertical === vertical);
  route.fulfill({ json: { vacancies: results } });
});
await page.route("**://telegram.org/js/telegram-web-app.js", (route) => route.abort());

await page.goto(BASE, { waitUntil: "networkidle" });

// дождаться слот-анимации интро
await sleep(2200);

await page.screenshot({ path: "smoke_1_profile.png" });
console.log("tab=profile ok, screenshot saved");
const unreadBadgeText = await page.locator(".thread-unread-badge").textContent().catch(() => null);
console.log("unread messages badge on hub (expect 2):", unreadBadgeText);

async function step(name, fn) {
  try {
    await fn();
    console.log(`step ${name}: ok`);
  } catch (e) {
    console.log(`step ${name}: FAILED -> ${e.message}`);
    await page.screenshot({ path: `smoke_FAIL_${name}.png` }).catch(() => {});
  }
}

await step("goto-search", async () => {
  await page.getByRole("button", { name: "Поиск" }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_2a_search_tab.png" });
});
await step("search-fill", async () => {
  await page.fill('input[placeholder="Юзернейм или описание"]', "target");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(500);
  await page.screenshot({ path: "smoke_2b_search_result.png" });
});
await step("directory-search-locked", async () => {
  await page.fill('input[placeholder="Юзернейм или описание"]', "менеджер крипто");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(400);
  const locked = await page.$(".directory-paywall");
  console.log("directory search without subscription -> paywall shown:", !!locked);
  await page.screenshot({ path: "smoke_2c_directory_locked.png" });
});

await step("search-unlocked-write-message", async () => {
  // Уже на вкладке "Поиск" (предыдущий шаг directory-search-locked её не
  // покидал) — повторный клик по УЖЕ активному табу не нужен и ненадёжен
  // (капля-индикатор с z-index выше кнопки перехватывает pointer events
  // именно на активном табе, см. TabBar.jsx).
  await page.fill('input[placeholder="Юзернейм или описание"]', "unlockeduser");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(500);
  const writeBtn = page.getByRole("button", { name: "✉️ Написать" });
  console.log("write button visible on unlocked profile:", await writeBtn.isVisible().catch(() => false));
  const otherCvText = await page.locator(".cv-readonly").innerText().catch(() => "");
  console.log("other user's CV visible on unlocked profile:", otherCvText.includes("Head of Partnerships"));
  await page.screenshot({ path: "smoke_2f_unlocked_profile.png" });

  await writeBtn.click();
  await sleep(500);
  console.log("clicking write opens thread with correct person:",
    await page.getByText("Unlocked User").isVisible().catch(() => false));
  await page.screenshot({ path: "smoke_2g_thread_empty.png" });

  await page.fill('textarea[placeholder="Сообщение…"]', "Здравствуйте, интересно обсудить сотрудничество");
  await page.getByRole("button", { name: "Отправить" }).click();
  await sleep(500);
  console.log("sent message bubble visible:",
    await page.getByText("Здравствуйте, интересно обсудить сотрудничество").isVisible().catch(() => false));
  await page.screenshot({ path: "smoke_2h_thread_sent.png" });

  await page.getByRole("button", { name: "‹ Сообщения" }).click();
  await sleep(300);
  console.log("thread appears in messages list after sending:",
    await page.getByText("Unlocked User").isVisible().catch(() => false));
  await page.screenshot({ path: "smoke_2i_messages_list.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("goto-confirm", async () => {
  await page.getByRole("button", { name: "Сделки", exact: true }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_3_confirm.png" });
});
await step("confirm-partnership-form-fields", async () => {
  // Фаза 2 (11.08.2026): офер/суммы/отзыв в форме "Подтвердить партнёрство".
  await page.fill('input[placeholder="Юзернейм контрагента"]', "confirmer");
  await page.fill('input[placeholder="Например: привёл байера на казино-трафик"]', "Свёл с байером");
  await page.fill('input[placeholder="Я получил, $"]', "500");
  await page.fill('input[placeholder="Я заплатил, $"]', "50");
  await page.getByRole("checkbox").click();
  await page.fill('textarea[placeholder="Как прошло сотрудничество"]', "Отличная сделка");
  await page.screenshot({ path: "smoke_3b_confirm_filled.png" });
  await page.getByRole("button", { name: "Отправить на подтверждение" }).click();
  await sleep(400);
  console.log("partnership form submitted ok:",
    await page.getByText("Заявка отправлена").isVisible().catch(() => false));
  await page.screenshot({ path: "smoke_3c_confirm_sent.png" });
});
await step("goto-subscribe", async () => {
  await page.getByRole("button", { name: "Подписка" }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_4_subscribe.png" });
});
await step("back-to-profile-toggle", async () => {
  await page.getByRole("button", { name: "Профиль" }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_5_profile_hub.png" });
  const toggles = await page.$$(".switch .slider");
  console.log("privacy toggles found:", toggles.length);
  if (toggles.length > 0) {
    await toggles[0].click();
    await sleep(400);
    await page.screenshot({ path: "smoke_5b_privacy_toggled.png" });
    console.log("privacy state after toggle:", JSON.stringify(privacyState));
  }
});

for (const [key, label] of [
  ["rating", "Мой рейтинг"],
  ["cv", "Моё CV"],
  ["contacts", "Мои контакты"],
  ["offers", "Мои офферы"],
]) {
  await step(`profile-subscreen-${key}`, async () => {
    await page.getByRole("button", { name: label }).click();
    await sleep(300);
    await page.screenshot({ path: `smoke_5c_sub_${key}.png` });
    await page.getByRole("button", { name: "‹ Профиль" }).click();
    await sleep(300);
  });
}

await step("profile-work-status", async () => {
  // Переделано 15.08.2026 (фидбек владельца): один ряд из 3 сегментов
  // без цветного эмодзи, цвет несёт сама кнопка через класс work-status-*;
  // повторный тап по активному сегменту снимает статус. Отдельная кнопка
  // "Выкл" и текстовая ссылка "Выключить" под рядом (промежуточный вариант
  // того же дня) обе убраны — владелец счёл ссылку лишней, раз повторный
  // тап уже делает то же самое.
  const lookingBtn = page.getByRole("button", { name: "Ищу работу", exact: true });
  await lookingBtn.click();
  await sleep(300);
  console.log("work_status after click:", ME_PAYLOAD.work_status);
  console.log("looking segment has color class:",
    await lookingBtn.evaluate((el) => el.classList.contains("work-status-looking") && el.classList.contains("active")));
  await page.screenshot({ path: "smoke_5e_work_status.png" });

  await lookingBtn.click(); // тап по уже активному сегменту -> снимает статус
  await sleep(300);
  console.log("work_status after re-click (expect null):", ME_PAYLOAD.work_status);
});

await step("profile-my-qr", async () => {
  await page.getByRole("button", { name: "Мой QR" }).click();
  await sleep(400);
  const img = await page.$(".qr-card img");
  console.log("qr image rendered:", !!img);
  await page.screenshot({ path: "smoke_5f_my_qr.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("contacts-qr-shortcut-and-invite", async () => {
  await page.getByRole("button", { name: "Мои контакты" }).click();
  await sleep(300);
  await page.screenshot({ path: "smoke_5i_contacts.png" });

  await page.getByRole("button", { name: "Показать мой QR (визитка)" }).click();
  await sleep(400);
  console.log("contacts -> QR shortcut opens QR screen:",
    await page.$(".qr-card img").then((el) => !!el).catch(() => false));
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
  await page.getByRole("button", { name: "Мои контакты" }).click();
  await sleep(300);

  await page.getByRole("button", { name: "🔗 Пригласить коллегу" }).click();
  await sleep(400);
  const openedLinks = await page.evaluate(() => window.__openedLinks || []);
  console.log("invite colleague opened share link:", openedLinks[openedLinks.length - 1]);
  await page.screenshot({ path: "smoke_5j_invite_colleague.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("recruiter-workspace-subscribe-and-edit", async () => {
  await page.getByRole("button", { name: "Рекрутер", exact: true }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_6a_recruiter_upsell.png" });
  console.log("recruiter upsell shows correct price (800⭐):",
    await page.getByText("800 ⭐").isVisible().catch(() => false));

  await page.getByRole("button", { name: /Оформить/ }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_6b_recruiter_editor.png" });
  console.log("recruiter editor visible right after subscribe:",
    await page.getByText("Имя / подпись").isVisible().catch(() => false));

  await page.getByRole("button", { name: "Заполнить" }).first().click();
  await sleep(200);
  await page.fill('input[placeholder="Например: Иван Петров, HR отдел"]', "Init HR");
  await page.getByRole("button", { name: "Сохранить" }).click();
  await sleep(300);
  console.log("recruiter name field saved:", await page.getByText("Init HR").isVisible().catch(() => false));

  const toggles = await page.$$(".switch .slider");
  console.log("recruiter privacy toggles rendered (expect 7):", toggles.length);
  await page.screenshot({ path: "smoke_6c_recruiter_filled.png" });

  await page.getByRole("button", { name: "Личный", exact: true }).click();
  await sleep(300);
});

await step("view-recruiter-card-of-other-user", async () => {
  await page.getByRole("button", { name: "Поиск" }).click();
  await sleep(300);
  await page.fill('input[placeholder="Юзернейм или описание"]', "unlockeduser");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(500);
  const viewRecruiterBtn = page.getByRole("button", { name: "🧑‍💼 Посмотреть как рекрутера" });
  console.log("view-as-recruiter button visible:", await viewRecruiterBtn.isVisible().catch(() => false));
  await viewRecruiterBtn.click();
  await sleep(400);
  console.log("recruiter card of other user shown:",
    await page.getByText("Unlocked Recruiter").isVisible().catch(() => false));
  await page.screenshot({ path: "smoke_2m_other_recruiter_card.png" });
  await page.getByRole("button", { name: "‹ Личный профиль" }).click();
  await sleep(400);
  console.log("back to personal card:",
    await page.getByText("Unlocked User").isVisible().catch(() => false));

  // Возвращаемся на вкладку "Профиль" — следующий по сценарию шаг
  // (profile-subscription-gate) ожидает именно это состояние.
  await page.getByRole("button", { name: "Профиль" }).click();
  await sleep(300);
});

await step("profile-hub-rating-preview", async () => {
  // Кружок рейтинга + счётчик сделок на самой визитке (14.08.2026, фидбек
  // владельца по PDF от 11.08 — эти элементы были в исходном макете на
  // ГЛАВНОМ экране, редизайн 10.08 унёс их только внутрь "Мой рейтинг").
  // До подписки: ME_PAYLOAD.reputation_score/confirmed_partnerships = null
  // (гейт), кружок должен показывать замок и подсказку "как исправить".
  const circleLocked = await page.locator(".rating-preview-circle").textContent();
  const dealsLocked = await page.locator(".rating-summary-deals").textContent();
  const hintLockedVisible = await page.locator(".rating-summary-hint").isVisible().catch(() => false);
  console.log("rating preview (unsubscribed) circle:", circleLocked, "| deals:", dealsLocked, "| hint visible:", hintLockedVisible);
  await page.screenshot({ path: "smoke_1b_hub_rating_preview_locked.png" });

  await page.getByRole("button", { name: "Мой рейтинг" }).click();
  await sleep(300);
  console.log("rating preview click -> opened rating subscreen:",
    await page.locator("h3", { hasText: "Мой рейтинг" }).isVisible().catch(() => false));
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("profile-subscription-gate", async () => {
  await page.getByRole("button", { name: "Мой рейтинг" }).click();
  await sleep(300);
  const gateNoteBefore = await page.$(".subscription-gate-note");
  console.log("subscription-gate note visible (unsubscribed):", !!gateNoteBefore);
  await page.screenshot({ path: "smoke_5g_rating_gated.png" });

  // симулируем реактивацию подписки (как реальный бэкенд отдал бы после
  // оплаты) — те же числа возвращаются, ничего не потеряно
  Object.assign(ME_PAYLOAD, SUBSCRIBED_EXTRAS, { is_subscribed: true, subscription_status: "active" });
  await page.reload({ waitUntil: "networkidle" });
  await sleep(2200); // интро снова

  // тот же кружок теперь должен показать реальные числа (87.5 округляется
  // до 88, 2 сделки) и СПРЯТАТЬ подсказку "низкий рейтинг" (есть подписка
  // И есть подтверждённые сделки).
  const circleUnlocked = await page.locator(".rating-preview-circle").textContent();
  const dealsUnlocked = await page.locator(".rating-summary-deals").textContent();
  const hintUnlockedVisible = await page.locator(".rating-summary-hint").isVisible().catch(() => false);
  console.log("rating preview (subscribed, 87.5 rep / 2 deals) circle:", circleUnlocked, "| deals:", dealsUnlocked, "| hint visible:", hintUnlockedVisible);
  await page.screenshot({ path: "smoke_1c_hub_rating_preview_unlocked.png" });

  await page.getByRole("button", { name: "Мой рейтинг" }).click();
  await sleep(300);
  const gateNoteAfter = await page.$(".subscription-gate-note");
  console.log("subscription-gate note visible (subscribed):", !!gateNoteAfter);
  await page.screenshot({ path: "smoke_5h_rating_visible.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("rating-circle-color-tiers", async () => {
  // Цветовые пороги кружка рейтинга (15.08.2026, по прямому запросу
  // владельца — рейтинг стартует с 0, а не с базовых 50): 0=красный,
  // 1-4=жёлтый, 5+=зелёный.
  async function tierAt(score) {
    ME_PAYLOAD.reputation_score = score;
    await page.reload({ waitUntil: "networkidle" });
    await sleep(2200); // интро
    const cls = await page.locator(".rating-preview-circle").getAttribute("class");
    return cls;
  }
  const red = await tierAt(0);
  console.log("reputation=0 -> circle class:", red, "| has rep-red:", red.includes("rep-red"));
  const yellow = await tierAt(3);
  console.log("reputation=3 -> circle class:", yellow, "| has rep-yellow:", yellow.includes("rep-yellow"));
  const green = await tierAt(5);
  console.log("reputation=5 -> circle class:", green, "| has rep-green:", green.includes("rep-green"));
  await page.screenshot({ path: "smoke_1d_rating_tier_green.png", clip: await page.locator(".rating-preview").boundingBox() });
});

await step("directory-search-subscribed", async () => {
  await page.getByRole("button", { name: "Поиск" }).click();
  await sleep(400);
  await page.fill('input[placeholder="Юзернейм или описание"]', "менеджер крипто");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(400);
  const rows = await page.$$(".directory-row");
  console.log("directory search results found (subscribed):", rows.length);
  await page.screenshot({ path: "smoke_2d_directory_results.png" });
  if (rows.length > 0) {
    await rows[0].click();
    await sleep(400);
    await page.screenshot({ path: "smoke_2e_directory_opened_profile.png" });
  }
});

await step("browse-by-vertical-and-top-sort", async () => {
  // Уже на вкладке "Поиск" (предыдущий шаг её не покидал) — см. заметку
  // про клик по уже активному табу в search-unlocked-write-message выше.
  await page.getByRole("button", { name: "Gambling", exact: true }).click();
  await sleep(400);
  const rows = await page.$$(".directory-row");
  console.log("browse by vertical results found:", rows.length);
  await page.screenshot({ path: "smoke_2j_browse_vertical.png" });

  const topCheckbox = page.getByRole("checkbox", { name: /Сначала высокий рейтинг/ });
  console.log("top-rating toggle visible:", await topCheckbox.isVisible().catch(() => false));
  await topCheckbox.click();
  await sleep(400);
  const namesAfterTop = await page.$$eval(".directory-row-name", (els) => els.map((e) => e.textContent));
  console.log("order after top=1 toggle (expect High Rep first):", namesAfterTop);
  await page.screenshot({ path: "smoke_2k_browse_top_sorted.png" });
});

await step("resumes-filter", async () => {
  // Всё ещё на "Поиск" — "Резюме" (Фаза 4) это чекбокс поверх browse по
  // вертикали, не отдельная вкладка.
  await page.getByRole("checkbox", { name: /ищет работу/ }).click();
  await sleep(200);
  await page.getByRole("button", { name: "Показать всех, кто ищет работу" }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_2l_resumes.png" });
  console.log("resumes filter step ran without crash (mock has no looking-for-work fixtures)");
});

await step("vacancies-tab-upsell", async () => {
  await page.getByRole("button", { name: "Вакансии", exact: true }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_11a_vacancies_upsell.png" });
  console.log("existing vacancy card visible:",
    await page.getByText("Existing QA Lead").isVisible().catch(() => false));
  console.log("publish button hidden without recruiter subscription:",
    await page.getByRole("button", { name: "➕ Опубликовать вакансию" }).isVisible().catch(() => false));
});

await step("vacancies-publish-and-close", async () => {
  // Симулируем активную подписку рекрутера на моке (тот же приём, что и в
  // profile-subscription-gate выше — прямая мутация мок-состояния).
  recruiterState.is_recruiter_subscribed = true;
  await page.getByRole("button", { name: "Профиль" }).click();
  await sleep(300);
  await page.getByRole("button", { name: "Вакансии", exact: true }).click();
  await sleep(400);

  const publishBtn = page.getByRole("button", { name: "➕ Опубликовать вакансию" });
  console.log("publish button visible with recruiter subscription:",
    await publishBtn.isVisible().catch(() => false));
  await publishBtn.click();
  await sleep(300);

  await page.fill('input[placeholder="Например: Senior Product Manager"]', "New Talent Lead");
  // "Gambling" встречается дважды на странице (фильтр доски + чип формы) —
  // берём именно тот, что внутри формы (form -> getByRole сужает поиск).
  await page.locator("form").getByRole("button", { name: "Gambling", exact: true }).click();
  await page.selectOption("select", "Senior");
  await page.fill('input[placeholder="Malta, Cyprus…"]', "Cyprus");
  await page.getByText("Можно удалённо").click();
  await page.getByText("По договорённости (не указывать вилку)").click();
  await page.fill("textarea", "Ищем сильного лида в казино-направление");
  await page.screenshot({ path: "smoke_11b_vacancy_form_filled.png" });

  await page.getByRole("button", { name: "Опубликовать", exact: true }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_11c_vacancy_published.png" });
  console.log("new vacancy visible in public list:",
    await page.getByText("New Talent Lead").isVisible().catch(() => false));
  console.log("new vacancy visible in Мои вакансии:",
    await page.getByText("Мои вакансии").isVisible().catch(() => false));

  const closeButtons = page.getByRole("button", { name: "Закрыть" });
  const closeCount = await closeButtons.count();
  console.log("close buttons in Мои вакансии:", closeCount);
  if (closeCount > 0) {
    await closeButtons.first().click();
    await sleep(400);
    await page.screenshot({ path: "smoke_11d_vacancy_closed.png" });
    console.log("closed badge visible:", await page.getByText("Закрыта").isVisible().catch(() => false));
  }
});

await step("onboarding-no-profile", async () => {
  const page3 = await browser.newPage({ viewport: { width: 420, height: 860 } });
  await page3.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "mock_init_data",
        ready() {},
        expand() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
        openInvoice(url, cb) {
          cb && cb("paid");
        },
        openTelegramLink() {},
      },
    };
  });
  await page3.route("**/api/me", (route) => route.fulfill({ status: 404, json: { error: "NO_PROFILE" } }));
  await page3.route("**://telegram.org/js/telegram-web-app.js", (route) => route.abort());
  await page3.goto(BASE, { waitUntil: "networkidle" });
  await sleep(2200); // интро
  await page3.screenshot({ path: "smoke_8a_onboarding.png" });
  await page3.getByRole("button", { name: "Подробнее" }).click();
  await sleep(200);
  const detailVisible = await page3.getByText("7 вертикалях").isVisible().catch(() => false);
  console.log("onboarding: detail expanded after 'Подробнее':", detailVisible);
  await page3.screenshot({ path: "smoke_8b_onboarding_expanded.png" });
  await page3.close();
});

await step("edit-cv-field", async () => {
  await page.getByRole("button", { name: "Профиль" }).click();
  await sleep(300);
  await page.getByRole("button", { name: "Моё CV" }).click();
  await sleep(300);
  await page.getByRole("button", { name: "Изменить" }).click();
  await sleep(200);
  await page.fill("textarea", "обновлённый текст CV из smoke-теста");
  // .first() — расширение "Моё CV" (12.08.2026) добавило постоянно видимую
  // кнопку "Сохранить" у блока зарплатных ожиданий (SalaryField), она идёт
  // ПОСЛЕ формы cv_text в DOM, .first() детерминированно берёт нужную.
  await page.getByRole("button", { name: "Сохранить" }).first().click();
  await sleep(300);
  await page.screenshot({ path: "smoke_5d_cv_edited.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("cv-expansion-fields", async () => {
  // Профиль уже активная вкладка (предыдущий шаг вернулся туда кнопкой
  // "‹ Профиль") — повторный клик по табу словит каплю-индикатор поверх
  // кнопки (известная особенность, см. drag-tab-blob), поэтому не кликаем.
  await page.getByRole("button", { name: "Моё CV" }).click();
  await sleep(300);

  // Должность (с лимитом смен, см. GuroStorage.set_cv_profession) — 2-е
  // поле .editable-field на экране (0=cv_text, 1=должность, 2=локация).
  const professionField = page.locator(".editable-field").nth(1);
  await professionField.getByRole("button", { name: "Заполнить" }).click();
  await sleep(150);
  await professionField.locator("input[type=text]").fill("Head of Marketing");
  await professionField.getByRole("button", { name: "Сохранить" }).click();
  await sleep(200);
  const professionSaved = await professionField.getByText("Head of Marketing").isVisible().catch(() => false);
  console.log("cv: profession saved:", professionSaved);

  const locationField = page.locator(".editable-field").nth(2);
  await locationField.getByRole("button", { name: "Заполнить" }).click();
  await sleep(150);
  await locationField.locator("input[type=text]").fill("Odesa");
  await locationField.getByRole("button", { name: "Сохранить" }).click();
  await sleep(200);
  const locationSaved = await locationField.getByText("Odesa").isVisible().catch(() => false);
  console.log("cv: location saved:", locationSaved);

  await page.getByRole("button", { name: "Gambling", exact: true }).click();
  await sleep(150);
  await page.getByRole("button", { name: "Crypto", exact: true }).click();
  await sleep(200);
  const verticalsSelected = await page.locator(".vertical-chip.is-selected").count();
  console.log("cv: verticals selected count (expect 2):", verticalsSelected);

  await page.locator("select").selectOption({ index: 3 }); // Senior (5-8 years)
  await sleep(200);

  const relocationCard = page.locator(".card").filter({ hasText: "Готовность к релокации" });
  await relocationCard.getByRole("button", { name: "Да" }).click();
  await sleep(200);
  const polygraphCard = page.locator(".card").filter({ hasText: "Согласие на полиграф" });
  await polygraphCard.getByRole("button", { name: "Нет" }).click();
  await sleep(200);

  const salaryCard = page.locator(".card").filter({ hasText: "Зарплатные ожидания" });
  await salaryCard.locator('input[type="number"]').nth(0).fill("2000");
  await salaryCard.locator('input[type="number"]').nth(1).fill("3500");
  await salaryCard.getByRole("button", { name: "Сохранить" }).click();
  await sleep(200);

  await page.screenshot({ path: "smoke_5k_cv_expansion_fields.png" });

  const experienceCard = page.locator(".card").filter({ hasText: "Опыт работы" });
  await experienceCard.getByRole("button", { name: "+ Добавить опыт" }).click();
  await sleep(150);
  const expInputs = experienceCard.locator('input[type="text"]');
  await expInputs.nth(0).fill("GURO Co");
  await expInputs.nth(1).fill("Marketing Lead");
  await experienceCard.getByRole("button", { name: "Сохранить" }).click();
  await sleep(200);
  const entryVisible = await experienceCard.getByText("Marketing Lead — GURO Co").isVisible().catch(() => false);
  console.log("cv: experience entry added:", entryVisible);
  await page.screenshot({ path: "smoke_5l_cv_experience_added.png" });

  await experienceCard.getByRole("button", { name: "Удалить" }).click();
  await sleep(200);
  const entryGone = !(await experienceCard.getByText("Marketing Lead — GURO Co").isVisible().catch(() => false));
  console.log("cv: experience entry deleted after removal:", entryGone);

  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("cv-view-and-share", async () => {
  // "Посмотреть моё CV" (16.08.2026) — read-only показ уже заполненных
  // (предыдущим шагом) полей + кнопка "Поделиться". Профиль -> Моё CV уже
  // содержит Head of Marketing/Odesa/Senior/релокация Да/зарплата 2000-3500
  // из cv-expansion-fields.
  await page.getByRole("button", { name: "Моё CV" }).click();
  await sleep(300);
  await page.getByRole("button", { name: "👁 Посмотреть моё CV" }).click();
  await sleep(300);
  const viewText = await page.locator(".cv-readonly").innerText().catch(() => "");
  console.log("cv view shows profession:", viewText.includes("Head of Marketing"),
    "| location:", viewText.includes("Odesa"),
    "| grade:", viewText.includes("Senior"));
  await page.screenshot({ path: "smoke_5m_cv_view.png" });

  await page.getByRole("button", { name: "📤 Поделиться CV" }).click();
  await sleep(300);
  const openedLinks = await page.evaluate(() => window.__openedLinks || []);
  const shareLink = openedLinks[openedLinks.length - 1] || "";
  console.log("cv share opened t.me/share link:", shareLink.includes("t.me/share/url"),
    "| contains deeplink to guro_:", shareLink.includes(encodeURIComponent("start=guro_")));

  await page.getByRole("button", { name: "‹ К редактированию" }).click();
  await sleep(300);
  console.log("back to edit mode:",
    await page.getByRole("button", { name: "👁 Посмотреть моё CV" }).isVisible().catch(() => false));
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
});

await step("drag-tab-blob", async () => {
  const blob = await page.$(".tab-blob");
  const box = await blob.boundingBox();
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  // тащим каплю через весь таббар вправо, до последнего раздела ("Подписка") —
  // намеренный ЗАВЕДОМЫЙ перебор (не x2.6, а x10 ширины капли), а не число,
  // подогнанное под конкретное количество табов: dragConstraints={barRef}
  // всё равно клэмпит каплю к правому краю бара, так что перебор безопасен
  // и переживёт добавление новых вкладок (5 табов после Фазы 4 вместо 4).
  await page.mouse.move(startX + box.width * 10, startY, { steps: 12 });
  await page.mouse.up();
  await sleep(700); // дать пружине довертеться/успокоиться
  await page.screenshot({ path: "smoke_6_blob_dragged.png" });
  console.log("active tab after drag: check screenshot");
});

await step("deep-link-target", async () => {
  const page2 = await browser.newPage({ viewport: { width: 420, height: 860 } });
  await page2.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "mock_init_data",
        ready() {},
        expand() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
        openInvoice(url, cb) {
          cb && cb("paid");
        },
        openTelegramLink() {},
      },
    };
  });
  await page2.route("**/api/me", (route) => route.fulfill({ json: { ...ME_PAYLOAD, privacy: privacyState } }));
  await page2.route("**/api/search**", (route) => route.fulfill({ json: SEARCH_LOCKED }));
  await page2.route("**://telegram.org/js/telegram-web-app.js", (route) => route.abort());
  await page2.goto(`${BASE}/?target=555`, { waitUntil: "networkidle" });
  await sleep(2200); // интро

  const searchTabActive = await page2.$("button:has-text('Поиск').active, .tab.active:has-text('Поиск')");
  const cardVisible = await page2.getByText("Target User").isVisible().catch(() => false);
  console.log("deep-link: search tab landed automatically:", !!searchTabActive || cardVisible);
  console.log("deep-link: locked target card visible:", cardVisible);
  await page2.screenshot({ path: "smoke_7_deeplink_target.png" });
  const urlAfterLoad = page2.url();
  console.log("deep-link: URL cleaned (no ?target=):", !urlAfterLoad.includes("target="));
  await page2.close();
});

await step("deep-link-thread", async () => {
  const page3 = await browser.newPage({ viewport: { width: 420, height: 860 } });
  await page3.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "mock_init_data",
        ready() {},
        expand() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
        openInvoice(url, cb) {
          cb && cb("paid");
        },
        openTelegramLink() {},
      },
    };
  });
  await page3.route("**/api/me", (route) => route.fulfill({ json: { ...ME_PAYLOAD, privacy: privacyState } }));
  await page3.route("**/api/messages/with/**", (route) => {
    const url = new URL(route.request().url());
    const otherId = Number(url.pathname.split("/").pop());
    route.fulfill({
      json: {
        other_user_id: otherId,
        other_name: "Unlocked User",
        other_username: "unlockeduser",
        messages: messagesByUser[otherId] || [],
        can_send_first: true,
      },
    });
  });
  await page3.route("**://telegram.org/js/telegram-web-app.js", (route) => route.abort());
  // Уведомление о новом сообщении ведёт на ?thread=<id_отправителя> — та же
  // механика, что ?target= у QR, но открывает переписку, а не Поиск.
  await page3.goto(`${BASE}/?thread=888`, { waitUntil: "networkidle" });
  await sleep(2200); // интро

  console.log("thread deep-link: opens conversation directly:",
    await page3.getByText("Unlocked User").isVisible().catch(() => false));
  await page3.screenshot({ path: "smoke_9_deeplink_thread.png" });
  const urlAfterLoad3 = page3.url();
  console.log("thread deep-link: URL cleaned (no ?thread=):", !urlAfterLoad3.includes("thread="));
  await page3.close();
});

await step("language-switch", async () => {
  // Переключатель RU/EN в правом верхнем углу (12.08.2026). Проверяем на
  // ГЛАВНОЙ странице (page), которая всё ещё жива после предыдущих шагов —
  // переключаем на EN, смотрим на несколько экранов, возвращаем RU (иначе
  // сломает финальные проверки CONSOLE_ERRORS ниже — впрочем, к этому
  // моменту сценарий уже закончен, но оставляем по дисциплине).
  // Уже на вкладке "Поиск" с предыдущего шага (browse-by-vertical-and-top-sort) —
  // после переключения на EN она же станет активной "Search", повторный
  // клик по уже активному табу ненадёжен (см. заметки выше про tab-blob).
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await sleep(300);
  await page.screenshot({ path: "smoke_10a_lang_en_profile.png" });
  console.log("EN: tab label translated:",
    await page.getByRole("button", { name: "Search" }).isVisible().catch(() => false));
  // Сейчас мы на вкладке "Подписка"/Subscribe (утащена туда drag-tab-blob
  // выше) — проверяем перевод именно этого экрана, не Поиска.
  console.log("EN: subscribe screen translated:",
    await page.getByText("GURO ID subscription").isVisible().catch(() => false));

  // Предыдущий шаг (drag-tab-blob) утащил каплю на последний таб
  // ("Подписка"/Subscribe) — кликаем "Profile" (гарантированно ДРУГОЙ таб,
  // не активный сейчас), а не "Subscribe" (был бы клик по уже активному).
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  await sleep(300);
  await page.screenshot({ path: "smoke_10c_lang_en_profile_hub.png" });
  console.log("EN: profile hub translated:",
    await page.getByText("My rating").isVisible().catch(() => false));

  await page.getByRole("button", { name: "RU", exact: true }).click();
  await sleep(300);
  console.log("RU: switched back, hub label restored:",
    await page.getByText("Мой рейтинг").isVisible().catch(() => false));
});

console.log("CONSOLE_ERRORS:", JSON.stringify(consoleErrors, null, 2));

await browser.close();
server.kill();
process.exit(0);
