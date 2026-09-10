"""Выдача доступа в сообщество после оплаты (09.09.2026).

Модуль общий для ДВУХ процессов, и это не прихоть архитектуры, а следствие
того, как устроены платежи:

  • звёзды подтверждаются в боте (successful_payment);
  • крипта — вебхуком в процессе API мини-приложения.

Человек проходит анкету в боте, но если он платит криптой, подтверждение
приходит в другой процесс, и бот сам никогда не узнает, что пора выдавать
ссылку. Поэтому «выдать доступ» вынесено сюда и вызывается из обоих мест с
тем экземпляром Bot, который есть под рукой.

ССЫЛКА ОДНОРАЗОВАЯ (member_limit=1) и создаётся В МОМЕНТ ВЫДАЧИ, а не
заранее: ссылка, созданная до оплаты, утекает к неоплатившим — её можно
переслать кому угодно.

ПРИЗНАК community_access_granted ЗДЕСЬ НЕ СТАВИТСЯ. Он означает «доступ без
оплаты навсегда» и принадлежит старым участникам и ручным выдачам. У
оплатившего доступ держится подпиской: поставь мы флаг — человек стал бы
неприкосновенным для выселения, и правило «не продлил, значит вышел»
перестало бы работать.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

logger = logging.getLogger(__name__)


async def make_invite_link(bot, chat_id: int, user_id: int, fallback: str = "") -> str:
    """Одноразовая ссылка в группу. При сбое — запасная общая ссылка, если
    она настроена: остаться без ссылки после оплаты хуже, чем выдать общую.
    """
    if not chat_id:
        return fallback
    try:
        link = await bot.create_chat_invite_link(
            chat_id, member_limit=1, name=f"pgc_{user_id}"[:32],
        )
        return link.invite_link
    except Exception:  # noqa: BLE001
        logger.exception("доступ: не удалось создать одноразовую ссылку для %s", user_id)
        return fallback


async def grant_access(bot, settings, user_id: int, text: str,
                       join_label: str, app_label: str) -> bool:
    """Выдаёт доступ: создаёт ссылку и отправляет её человеку.

    Тексты приходят снаружи — они лежат в CMS бота, а этот модуль вызывается
    и из процесса API, где содержимого CMS под рукой нет.

    Возвращает False при любом сбое отправки и не поднимает исключение:
    вызывается из обработчика платежа и из вебхука, где падение означало бы
    повтор платежа или потерю подтверждения.
    """
    chat_id = getattr(settings, "community_chat_id", 0)
    fallback = getattr(settings, "community_invite_url", "") or ""
    invite = await make_invite_link(bot, chat_id, user_id, fallback)

    rows = []
    if invite:
        rows.append([InlineKeyboardButton(join_label, url=invite)])
    app_url = getattr(settings, "guro_id_webapp_url", "") or ""
    if app_url:
        rows.append([InlineKeyboardButton(app_label, web_app=WebAppInfo(url=app_url))])

    try:
        await bot.send_message(
            user_id, text, reply_markup=InlineKeyboardMarkup(rows) if rows else None,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("доступ: не удалось отправить ссылку пользователю %s", user_id)
        return False


async def revoke_access(bot, settings, user_id: int) -> bool:
    """Выселение из группы по истечении подписки.

    Кик, а не вечный бан: ban + unban убирает из группы, не оставляя в
    чёрном списке. Человек, оплативший заново, должен войти по новой ссылке
    сразу — с вечным баном его пришлось бы ещё и разбанивать, и любой сбой
    оставил бы оплатившего за дверью.
    """
    chat_id = getattr(settings, "community_chat_id", 0)
    if not chat_id:
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("доступ: не удалось выселить %s из группы", user_id)
        return False
