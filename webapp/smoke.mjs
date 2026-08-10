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
  verified_screening: true,
  joined_community_at: "2026-01-01 00:00:00",
  days_in_community: 221,
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
  subscription_status: "inactive",
  subscription_expires_at: null,
  is_subscribed: false,
  privacy: {
    hide_name: false,
    hide_company: false,
    hide_vertical: false,
    hide_tenure: false,
    hide_reputation: false,
  },
};

const SEARCH_LOCKED = {
  user_id: 555,
  username: "target",
  name: "Target User",
  reputation_score: 61.2,
  confirmed_partnerships: 1,
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
await page.route("**/api/search**", (route) => route.fulfill({ json: SEARCH_LOCKED }));
await page.route("**/api/privacy", async (route) => {
  const body = route.request().postDataJSON();
  privacyState = { ...privacyState, [body.field]: body.value };
  route.fulfill({ json: privacyState });
});

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
  await page.fill('input[placeholder="Поиск по юзернейму"]', "target");
  await page.getByRole("button", { name: "Найти" }).click();
  await sleep(500);
  await page.screenshot({ path: "smoke_2b_search_result.png" });
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
  const toggles = await page.$$(".switch .slider");
  console.log("privacy toggles found:", toggles.length);
  if (toggles.length > 0) {
    await toggles[0].click();
    await sleep(400);
    await page.screenshot({ path: "smoke_5_privacy_toggled.png" });
    console.log("privacy state after toggle:", JSON.stringify(privacyState));
  }
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

console.log("CONSOLE_ERRORS:", JSON.stringify(consoleErrors, null, 2));

await browser.close();
server.kill();
process.exit(0);
