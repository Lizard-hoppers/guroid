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

let privacyState = { ...ME_PAYLOAD.privacy };

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
      openTelegramLink() {},
    },
  };
});

await page.route("**/api/me", (route) => route.fulfill({ json: { ...ME_PAYLOAD, privacy: privacyState } }));
// Универсальный поиск (10.08.2026): один эндпоинт /api/search?q= — точный
// юзернейм "target" отдаёт тизер-профиль (mode=profile), любой другой
// текст трактуется как описание (mode=list, платный directory-режим).
await page.route("**/api/search**", (route) => {
  const url = new URL(route.request().url());
  if (url.searchParams.get("user_id")) {
    return route.fulfill({ json: SEARCH_LOCKED });
  }
  const q = url.searchParams.get("q") || "";
  if (q === "target") {
    return route.fulfill({ json: SEARCH_LOCKED });
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
await page.route("**/api/work_status", async (route) => {
  const body = route.request().postDataJSON();
  ME_PAYLOAD.work_status = body.status;
  route.fulfill({ json: { work_status: body.status } });
});
await page.route("**/api/qr", (route) =>
  route.fulfill({ json: { deeplink: "https://t.me/GamblingCommunitybot?start=guro_100" } }),
);
await page.route("**/api/plans", (route) => route.fulfill({
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
}));
await page.route("**://telegram.org/js/telegram-web-app.js", (route) => route.abort());

await page.goto(BASE, { waitUntil: "networkidle" });

// дождаться слот-анимации интро
await sleep(2200);

await page.screenshot({ path: "smoke_1_profile.png" });
console.log("tab=profile ok, screenshot saved");

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

await step("goto-confirm", async () => {
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await sleep(400);
  await page.screenshot({ path: "smoke_3_confirm.png" });
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
  await page.getByRole("button", { name: "🟢 Ищу работу" }).click();
  await sleep(300);
  await page.screenshot({ path: "smoke_5e_work_status.png" });
  console.log("work_status after click:", ME_PAYLOAD.work_status);
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
  await page.getByRole("button", { name: "Мой рейтинг" }).click();
  await sleep(300);
  const gateNoteAfter = await page.$(".subscription-gate-note");
  console.log("subscription-gate note visible (subscribed):", !!gateNoteAfter);
  await page.screenshot({ path: "smoke_5h_rating_visible.png" });
  await page.getByRole("button", { name: "‹ Профиль" }).click();
  await sleep(300);
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
  await page.getByRole("button", { name: "Сохранить" }).click();
  await sleep(300);
  await page.screenshot({ path: "smoke_5d_cv_edited.png" });
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
  // тащим каплю через весь таббар вправо, до раздела "Подписка"
  await page.mouse.move(startX + box.width * 2.6, startY, { steps: 12 });
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

console.log("CONSOLE_ERRORS:", JSON.stringify(consoleErrors, null, 2));

await browser.close();
server.kill();
process.exit(0);
