"""Раздел «🪪 GURO ID» дашборда /admin — статистика по партнёрствам/репутации/
подписке. Только чтение (сам GURO ID живёт в отдельном сервисе guro_id_api.py
и в handlers/guro_partnerships.py, guro_payments.py) — здесь просто витрина
цифр поверх той же БД, без дублирования модуля (Clean & Live Manifest)."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, filters

import guro_constants as GC
import guro_crypto as GCR
from handlers import admin_ui

logger = logging.getLogger(__name__)


def _back_to_guro_kb() -> InlineKeyboardMarkup:
    """Возврат в раздел GURO ID, а не на главную панель: экран открыт
    изнутри раздела, и человеку нужны остальные его пункты."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Назад", callback_data="acms_guro")]])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")]])


async def _stars_line(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Заработано звёзд — через нативный реестр Telegram Stars (у бота нет
    своей таблицы платежей, см. аналогичное решение в Taki Vmeste). Отдаёт
    последние до 100 операций — на старте продукта этого достаточно."""
    try:
        tx = await context.bot.get_star_transactions(limit=100)
        earned = sum(t.amount for t in tx.transactions if t.amount > 0)
        return f"\n⭐ Звёзд получено (последние операции): {earned}"
    except Exception:  # noqa: BLE001
        logger.debug("admin_guro: get_star_transactions failed", exc_info=True)
        return ""


async def _crypto_line(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Получено в крипте (11.09.2026, просьба владельца) — рядом со
    звёздами. Считаем только "бизнес"-токен (GCR.business_token) — личная
    доля владельца сюда не попадает, тот же принцип, что у
    active_subscriptions в dashboard_stats(). Молча пропускаем строку,
    если крипта не настроена вовсе — как и звёзды при сбое API."""
    settings = context.bot_data["settings"]
    token = GCR.business_token(settings)
    if not token:
        return ""
    try:
        earned = await GCR.get_paid_total(token, GC.CRYPTO_ASSET)
        return f"\n💰 Получено в {GC.CRYPTO_ASSET} (крипта): {earned:.2f}"
    except Exception:  # noqa: BLE001
        logger.debug("admin_guro: get_paid_total failed", exc_info=True)
        return ""


def _dashboard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Подписки", callback_data="acms_guro_subs")],
        [InlineKeyboardButton("🚩 Подозрительная активность", callback_data="acms_guro_flagged")],
        [InlineKeyboardButton("🏢 Адреса компаний на проверку", callback_data="acms_guro_addr")],
        [InlineKeyboardButton("✅ Верификация компаний", callback_data="acms_guro_companyverify")],
        [InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")],
    ])


async def nav_guro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    s = guro.dashboard_stats()

    text = (
        "🪪 <b>GURO ID — статистика</b>\n\n"
        f"Партнёрств всего: <b>{s['total']}</b>\n"
        f"  ├ подтверждено: {s['confirmed']}\n"
        f"  ├ в ожидании: {s['pending']}\n"
        f"  └ отклонено: {s['declined']}\n"
        f"Новых заявок сегодня: {s['created_today']}\n\n"
        f"Отслеживается пользователей: {s['tracked_users']}\n"
        f"Средняя репутация: {s['avg_reputation']:.1f}\n"
        f"Активных подписок: {s['active_subscriptions']}"
        f"{await _stars_line(context)}"
        f"{await _crypto_line(context)}"
        "\n\n🔢 Тарифы и лимиты — команда /guro_limit (без аргументов — список текущих значений)."
    )
    await admin_ui.edit_screen(context, text, _dashboard_kb())
    return admin_ui.BROWSE


# --- антифрод поиска (ТЗ 7.3, 25.08.2026) — подозрительная активность -----

def _flagged_row_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❄️ Заморозить на 24ч", callback_data=f"guro_freeze:{user_id}"),
        InlineKeyboardButton("✅ Снять флаг", callback_data=f"guro_unflag:{user_id}"),
    ]])


def _fmt_until(value: str | None) -> str:
    """Срок в виде «до 5 окт 2026». Столетние сроки (их проставляли вручную
    прямо в базе) показываем как есть — по ним и видно, что это не покупка."""
    if not value:
        return "бессрочно"
    text = str(value)[:10]
    months = ("янв", "фев", "мар", "апр", "мая", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек")
    try:
        y, m, d = text.split("-")
        return f"до {int(d)} {months[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return f"до {text}"


async def nav_guro_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    data = guro.list_active_subscriptions()
    items, hidden = data["items"], data["hidden_personal_cut"]

    if not items:
        await admin_ui.edit_screen(context, "⭐ Действующих подписок нет.", _back_to_guro_kb())
        return admin_ui.BROWSE

    lines = [f"⭐ <b>Действующие подписки — {len(items)}</b>\n"]
    for kind in ("GURO ID", "Рекрутер", "Компания"):
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        lines.append(f"\n<b>{kind}</b> — {len(group)}")
        for i in group:
            who = f"@{i['username']}" if i["username"] else (i["name"] or f"id{i['user_id']}")
            cycle = f" · цикл {i['cycle']} дн." if i["cycle"] else ""
            lines.append(f"• {who} — <code>{i['user_id']}</code>\n"
                         f"   {_fmt_until(i['exp'])}{cycle}")

    if hidden:
        lines.append(
            f"\n<i>Не показано: {hidden} — оплата ушла на личный кошелёк "
            f"(кольцо 5:1), в бизнес-статистику такие не идут.</i>"
        )
    await admin_ui.edit_screen(context, "\n".join(lines), _back_to_guro_kb())
    return admin_ui.BROWSE


async def nav_guro_flagged(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    rows = guro.list_flagged_accounts()
    if not rows:
        await admin_ui.edit_screen(context, "🚩 Подозрительной активности не найдено.", _back_kb())
        return admin_ui.BROWSE

    lines = ["🚩 <b>Подозрительная активность (скрапинг поиска)</b>\n"]
    kb_rows = []
    for row in rows[:15]:
        frozen = " · ❄️ заморожен" if guro.is_frozen(row["user_id"]) else ""
        lines.append(f"• <code>{row['user_id']}</code> — флаг {row['scraping_flagged_at']}{frozen}")
        kb_rows.append([
            InlineKeyboardButton(f"❄️ {row['user_id']}", callback_data=f"guro_freeze:{row['user_id']}"),
            InlineKeyboardButton(f"✅ {row['user_id']}", callback_data=f"guro_unflag:{row['user_id']}"),
        ])
    kb_rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_guro")])
    await admin_ui.edit_screen(context, "\n".join(lines), InlineKeyboardMarkup(kb_rows))
    return admin_ui.BROWSE


async def guro_freeze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("Заморожено на 24ч")
    guro = context.bot_data["guro_storage"]
    user_id = int(q.data.split(":")[1])
    guro.freeze_account(user_id)
    return await nav_guro_flagged(update, context)


async def guro_unflag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("Флаг снят")
    guro = context.bot_data["guro_storage"]
    user_id = int(q.data.split(":")[1])
    guro.unfreeze_account(user_id)
    return await nav_guro_flagged(update, context)


# --- верификация адреса компании (ТЗ 5.5, 25.08.2026) ----------------------

def _addr_row_kb(address_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"guro_addr_ok:{address_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"guro_addr_no:{address_id}"),
    ]])


async def nav_guro_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    rows = guro.list_pending_company_addresses()
    if not rows:
        await admin_ui.edit_screen(context, "🏢 Адресов на проверку нет.", _back_kb())
        return admin_ui.BROWSE

    lines = ["🏢 <b>Адреса компаний на проверку</b>\n"]
    kb_rows = []
    for row in rows[:15]:
        lines.append(f"• #{row['id']} компания <code>{row['company_user_id']}</code> — {row['network']}: <code>{row['address']}</code>")
        kb_rows.append([
            InlineKeyboardButton(f"✅ #{row['id']}", callback_data=f"guro_addr_ok:{row['id']}"),
            InlineKeyboardButton(f"❌ #{row['id']}", callback_data=f"guro_addr_no:{row['id']}"),
        ])
    kb_rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_guro")])
    await admin_ui.edit_screen(context, "\n".join(lines), InlineKeyboardMarkup(kb_rows))
    return admin_ui.BROWSE


async def guro_addr_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    approve = q.data.startswith("guro_addr_ok:")
    address_id = int(q.data.split(":")[1])
    guro = context.bot_data["guro_storage"]
    ok = guro.review_company_address(address_id, update.effective_user.id, approve)
    await q.answer("Одобрено" if approve and ok else ("Отклонено" if ok else "Уже обработано"))
    return await nav_guro_addresses(update, context)


# --- верификация бейджа компании (ТЗ "Компания. каб", раздел 2, 26.08.2026) -
# Ручной MVP: владелец шлёт письмо с корпоративного домена на выделенный
# адрес (см. company.verify.* в i18n.jsx — фронт показывает адрес/формат),
# админ лично сверяет домен с сайтом/брендом в карточке и тут переключает
# бейдж. Автоматической проверки на этом этапе нет.

async def nav_guro_company_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    rows = guro.list_companies_for_verification()
    if not rows:
        await admin_ui.edit_screen(context, "✅ Компаний на верификацию нет.", _back_kb())
        return admin_ui.BROWSE

    lines = ["✅ <b>Верификация компаний</b>\n"]
    kb_rows = []
    for row in rows[:15]:
        status = "верифицирована" if row["verified"] else "ожидает"
        requested = row["verification_requested_at"] or "—"
        name = row["name"] or "(без названия)"
        website = row["website"] or "—"
        lines.append(
            f"• <code>{row['user_id']}</code> {name} — {website} — {status} "
            f"(заявка: {requested})"
        )
        kb_rows.append([
            InlineKeyboardButton(
                f"{'↩️ Снять' if row['verified'] else '✅ Верифицировать'} — {name[:20]}",
                callback_data=f"guro_cv_{'off' if row['verified'] else 'on'}:{row['user_id']}",
            ),
        ])
    kb_rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_guro")])
    await admin_ui.edit_screen(context, "\n".join(lines), InlineKeyboardMarkup(kb_rows))
    return admin_ui.BROWSE


async def guro_company_verify_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    verify = q.data.startswith("guro_cv_on:")
    user_id = int(q.data.split(":")[1])
    guro = context.bot_data["guro_storage"]
    ok = guro.set_company_verified(user_id, verify)
    await q.answer("Верифицировано" if verify and ok else ("Верификация снята" if ok else "Кабинет не найден"))
    return await nav_guro_company_verify(update, context)


# --- лимиты — глобальный конфиг + оверрайд на аккаунт (ТЗ "Тарифы и
# лимиты", раздел 3, 27.08.2026) ------------------------------------------
# ВНЕ ConversationHandler-состояний (обычный CommandHandler, group=1, тот же
# приём, что у build_admin_users_handlers) — работает сразу, без захода в
# /admin, полезно для быстрой точечной правки "прямо сейчас, в чате".
#
# /guro_limit — список всех ключей + текущее ГЛОБАЛЬНОЕ значение (конфиг
# или дефолт-константа).
# /guro_limit <user_id> — оверрайды конкретного аккаунта.
# /guro_limit <user_id> <key> <value> — задать глобальный оверрайд НА
# аккаунт (value целое число).
# /guro_limit <user_id> <key> reset — снять оверрайд (вернуться к
# глобальному значению).
# /guro_limit global <key> <value> — поменять ГЛОБАЛЬНЫЙ дефолт (влияет на
# всех, у кого нет собственного оверрайда).
_LIMIT_DEFAULTS = {
    GC.LIMIT_KEY_VIEWS_RECRUITER: GC.LIMIT_VIEWS_PER_DAY_RECRUITER,
    GC.LIMIT_KEY_VIEWS_COMPANY_BASIC: GC.LIMIT_VIEWS_PER_DAY_COMPANY_BASIC,
    GC.LIMIT_KEY_VIEWS_COMPANY_PRO: GC.LIMIT_VIEWS_PER_DAY_COMPANY_PRO,
    GC.LIMIT_KEY_REQUESTS_PERSONAL: GC.LIMIT_NEW_REQUESTS_PER_DAY_PERSONAL,
    GC.LIMIT_KEY_REQUESTS_RECRUITER: GC.LIMIT_NEW_REQUESTS_PER_DAY_RECRUITER,
    GC.LIMIT_KEY_REQUESTS_COMPANY: GC.LIMIT_NEW_REQUESTS_PER_DAY_COMPANY,
    GC.LIMIT_KEY_NEW_VACANCIES: GC.LIMIT_NEW_VACANCIES_PER_DAY,
    GC.LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER: GC.LIMIT_ACTIVE_VACANCIES_RECRUITER,
    GC.LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_BASIC: GC.LIMIT_ACTIVE_VACANCIES_COMPANY_BASIC,
    GC.LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_PRO: GC.LIMIT_ACTIVE_VACANCIES_COMPANY_PRO,
}


async def guro_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    guro = context.bot_data["guro_storage"]
    args = context.args or []

    if not args:
        lines = ["🔢 Тарифы и лимиты — текущие глобальные значения\n"]
        for key, default in _LIMIT_DEFAULTS.items():
            lines.append(f"• {key} = {guro.get_config(key, default)}")
        lines.append(
            "\nИспользование:\n"
            "/guro_limit <user_id> — оверрайды аккаунта\n"
            "/guro_limit <user_id> <key> <value> — задать оверрайд\n"
            "/guro_limit <user_id> <key> reset — снять оверрайд\n"
            "/guro_limit global <key> <value> — поменять глобальный дефолт"
        )
        await update.message.reply_text("\n".join(lines))
        return

    if args[0] == "global":
        if len(args) != 3 or args[1] not in GC.LIMIT_KEYS:
            await update.message.reply_text(f"Формат: /guro_limit global <key> <value>\nКлючи: {', '.join(GC.LIMIT_KEYS)}")
            return
        try:
            value = int(args[2])
        except ValueError:
            await update.message.reply_text("value должно быть целым числом.")
            return
        guro.set_config(args[1], value)
        await update.message.reply_text(f"✅ Глобальный дефолт {args[1]} = {value}")
        return

    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return

    if len(args) == 1:
        overrides = guro.list_user_limit_overrides(user_id)
        if not overrides:
            await update.message.reply_text(f"У {user_id} нет персональных оверрайдов лимитов.")
            return
        lines = [f"Оверрайды лимитов для {user_id}:"] + [f"• {r['limit_key']} = {r['value']}" for r in overrides]
        await update.message.reply_text("\n".join(lines))
        return

    if len(args) != 3 or args[1] not in GC.LIMIT_KEYS:
        await update.message.reply_text(
            f"Формат: /guro_limit <user_id> <key> <value|reset>\nКлючи: {', '.join(GC.LIMIT_KEYS)}"
        )
        return

    key = args[1]
    if args[2] == "reset":
        ok = guro.clear_user_limit_override(user_id, key)
        await update.message.reply_text(f"{'✅ Оверрайд снят' if ok else 'Оверрайда и так не было'} ({user_id}, {key}).")
        return

    try:
        value = int(args[2])
    except ValueError:
        await update.message.reply_text("value должно быть целым числом (или 'reset').")
        return
    guro.set_user_limit_override(user_id, key, value)
    await update.message.reply_text(f"✅ Для {user_id}: {key} = {value}")


async def guro_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/guro_access <user_id> [revoke] — пустить своего в сообщество без
    оплаты (09.09.2026) или снять освобождение. То же, что кнопка в карточке
    анкеты, только без захода в /admin — когда id уже под рукой."""
    from handlers.admin_profiles import grant_access_by_admin

    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Формат: /guro_access <user_id> — пустить без оплаты\n"
            "/guro_access <user_id> revoke — снять освобождение"
        )
        return
    user_id = int(args[0])
    storage = context.bot_data["storage"]
    if len(args) > 1 and args[1] == "revoke":
        storage.revoke_community_access(user_id)
        storage.log_action(update.effective_user.id, "community_access_revoke",
                           f"user_id={user_id}: освобождение снято")
        await update.message.reply_text(f"Освобождение снято для {user_id} — теперь по общему правилу.")
        return
    result = await grant_access_by_admin(context, update.effective_user.id, user_id)
    await update.message.reply_text(f"{user_id}: {result}")


def build_guro_limits_handlers(admin_ids) -> list:
    admin_filter = filters.User(user_id=list(admin_ids))
    return [
        CommandHandler("guro_limit", guro_limit_command, filters=admin_filter),
        CommandHandler("guro_access", guro_access_command, filters=admin_filter),
    ]
