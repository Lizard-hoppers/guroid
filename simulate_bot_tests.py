"""Тесты логики/хранилища + сценарная симуляция полного флоу анкеты.

Запуск (на сервере, в venv бота):
    python simulate_bot_tests.py
Код возврата 0 — все проверки пройдены.
"""
from __future__ import annotations

import asyncio
import math
import tempfile
from pathlib import Path

import constants as C
import logic
from professions_data import PROFESSIONS
from storage import Storage

PASS = 0
FAIL = 0


def check(cond: bool, msg: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


# --- 1. Данные/константы --------------------------------------------------

def test_data():
    print("== data ==")
    for v in C.VERTICALS:
        for g in C.GRADES:
            items = C.professions_for(v, g)
            check(len(items) > 0, f"{v}/{g} пуст")
            for code, label in items:
                check(bool(code) and bool(label), f"{v}/{g} пустой code/label")
    check(C.grades_for("Gambling")[-1] == C.INVESTOR_GRADE, "у Gambling нет грейда Инвестор")
    check(C.INVESTOR_GRADE not in C.grades_for("Betting"), "Инвестор протёк в Betting")
    total = sum(len(PROFESSIONS[v][g]) for v in C.VERTICALS for g in C.GRADES)
    check(total > 1000, f"мало профессий: {total}")
    print(f"  всего профессий: {total}")


# --- 2. Логика ------------------------------------------------------------

def test_logic():
    print("== logic ==")
    check(logic.page_count(0) == 1, "page_count(0)")
    check(logic.page_count(8) == 1, "page_count(8)")
    check(logic.page_count(9) == 2, "page_count(9)")
    check(logic.clamp_page(99, 9) == 1, "clamp_page over")
    check(logic.clamp_page(-5, 9) == 0, "clamp_page under")
    sl = logic.page_slice(list(range(20)), 1)
    check(sl[0] == (8, 8) and len(sl) == 8, "page_slice page1")
    check(logic.html_escape("<b>&") == "&lt;b&gt;&amp;", "html_escape")
    check(logic.needs_to_text([0, 2]) == f"{C.INVESTOR_NEEDS[0]}; {C.INVESTOR_NEEDS[2]}", "needs_to_text")
    from google_sheets_sync import HEADERS
    row = logic.profile_to_sheet_row({"user_id": 1, "name": "X"}, "2026-01-01")
    check(len(row) == len(HEADERS), f"длина строки таблицы {len(row)} != {len(HEADERS)}")


# --- 3. Хранилище ---------------------------------------------------------

def test_storage():
    print("== storage ==")
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d) / "t.sqlite3")
        pid, created = st.save_profile(
            {"user_id": 7, "username": "u", "vertical": "Gambling",
             "grade": "C-Level", "profession": "CEO", "request": "networking",
             "name": "Ann", "company": "Acme", "linkedin": "—"}
        )
        check(pid == 1 and st.count() == 1, "save_profile")
        check(len(st.unsynced()) == 1, "unsynced before")
        st.mark_synced(pid)
        check(len(st.unsynced()) == 0, "unsynced after")
        csv = st.export_csv()
        check("Acme" in csv and "vertical" in csv, "export_csv")

        # бан — отдельно от group_mutes (см. handlers/group_captcha._gate_mute)
        check(not st.is_banned(7), "is_banned дефолт False")
        st.ban_user(7)
        check(st.is_banned(7), "ban_user")
        st.ban_user(7)  # повторный бан — идемпотентно (INSERT OR REPLACE)
        check(st.is_banned(7), "повторный ban_user не ломается")
        st.unban_user(7)
        check(not st.is_banned(7), "unban_user")
        st.unban_user(999999)  # разбан незабаненного — no-op, не должен падать
        check(True, "unban_user незабаненного не падает")

        # рассылка по странам
        check(st.country_broadcast_segments() == [], "country_broadcast_segments пусто без стран")
        st.save_profile({"user_id": 8, "username": "u8", "vertical": "Gambling",
                          "grade": "C-Level", "profession": "CEO", "request": "r",
                          "name": "Bea", "company": "Acme", "linkedin": "-",
                          "country": "Азербайджан", "country_iso2": "AZ"})
        st.save_profile({"user_id": 9, "username": "u9", "vertical": "Betting",
                          "grade": "Senior", "profession": "Manager", "request": "r",
                          "name": "Cid", "company": "Acme", "linkedin": "-",
                          "country": "Азербайджан", "country_iso2": "AZ"})
        pid_raw, _ = st.save_profile({"user_id": 10, "username": "u10", "vertical": "Crypto",
                                       "grade": "Junior / Entry", "profession": "Dev", "request": "r",
                                       "name": "Dee", "company": "Acme", "linkedin": "-",
                                       "country": "germany"})  # без iso2 — как до фичи нормализации
        segs = st.country_broadcast_segments()
        check(len(segs) == 2, "country_broadcast_segments: 2 разные страны")
        az = next(s for s in segs if s["country"] == "Азербайджан")
        check(az["n"] == 2 and az["country_iso2"] == "AZ", "country_broadcast_segments: счётчик и iso2")
        check(len(st.profiles_for_broadcast(country="Азербайджан")) == 2,
              "profiles_for_broadcast(country=) фильтрует по стране")
        check(len(st.profiles_for_broadcast(country_in=["Азербайджан", "germany"])) == 3,
              "profiles_for_broadcast(country_in=) объединяет несколько стран")
        need = st.profiles_needing_country_normalization()
        check(len(need) == 1 and need[0]["id"] == pid_raw,
              "profiles_needing_country_normalization находит только без iso2")
        st.set_profile_country(pid_raw, "Германия", "DE")
        check(st.profiles_needing_country_normalization() == [],
              "set_profile_country закрывает бэклог нормализации")
        segs2 = st.country_broadcast_segments()
        check(any(s["country"] == "Германия" and s["country_iso2"] == "DE" for s in segs2),
              "country_broadcast_segments видит обновлённую страну")
        st.close()


def test_gossip_storage():
    print("== gossip storage ==")
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d) / "g.sqlite3")
        check(st.gossip_last_submission_at(7) is None, "gossip: нет отправок изначально")
        did = st.gossip_save_draft(7, "u7", "сырой текст", "<b>рендер</b>", flagged=False)
        check(did == 1, "gossip: save_draft id")
        check(st.gossip_pending_count() == 1, "gossip: pending_count после создания")
        draft = st.gossip_get_draft(did)
        check(draft["status"] == "pending" and draft["submitter_id"] == 7, "gossip: get_draft")
        check(st.gossip_last_submission_at(7) is not None, "gossip: last_submission_at заполнен")
        st.gossip_set_admin_msg(did, 42, 999)
        check(st.gossip_get_draft(did)["admin_msg_id"] == 999, "gossip: set_admin_msg")
        st.gossip_set_status(did, "published", published=True)
        d2 = st.gossip_get_draft(did)
        check(d2["status"] == "published" and d2["published_at"], "gossip: set_status published")
        check(st.gossip_pending_count() == 0, "gossip: pending_count после публикации")
        check(st.get_flag("gossip_enabled", True) is True, "gossip: флаг по умолчанию вкл")
        st.set_flag("gossip_enabled", False)
        check(st.get_flag("gossip_enabled", True) is False, "gossip: флаг выключается")
        st.close()


def test_news_storage():
    print("== news storage (дневной лимит показов, синхронизация админов) ==")
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d) / "n.sqlite3")
        did = st.news_save_draft("guid1", "src", "http://x", "Title", "<b>Текст</b>", None)
        check(did == 1, "news: save_draft id")
        check(st.news_pending_count() == 1, "news: pending_count после создания")
        check(st.news_notified_today_count() == 0, "news: ещё не показан никому")
        unnotified = st.news_pending_unnotified(10)
        check(len(unnotified) == 1 and unnotified[0]["id"] == did, "news: черновик в очереди на показ")

        st.news_add_admin_msg(did, 42, 5001)
        st.news_add_admin_msg(did, 43, 5002)
        msgs = st.news_list_admin_msgs(did)
        check({(m["admin_chat_id"], m["admin_msg_id"]) for m in msgs} == {(42, 5001), (43, 5002)},
              "news: у каждого админа своя запись сообщения (не перезаписывают друг друга)")

        st.news_mark_notified(did)
        check(st.news_notified_today_count() == 1, "news: счётчик показов за сегодня растёт")
        check(st.news_pending_unnotified(10) == [], "news: показанный черновик выходит из очереди")

        st.news_clear_admin_msgs(did)
        check(st.news_list_admin_msgs(did) == [], "news: записи сообщений очищены после решения")

        st.news_set_status(did, "published", published=True)
        check(st.news_pending_count() == 0, "news: pending_count после публикации")
        st.close()


def test_greeting_video_pool():
    print("== greeting video pool (round-robin) ==")
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d) / "v.sqlite3")
        check(st.greeting_video_next() is None, "pool: пусто -> None (фолбэк на CMS-медиа)")
        check(st.get_int_flag("no_such_key", 7) == 7, "int_flag: дефолт, если ключа нет")

        st.greeting_video_add("file_a", "video")
        st.greeting_video_add("file_b", "video")
        st.greeting_video_add("file_c", "video")
        check([r["file_id"] for r in st.greeting_video_list()] == ["file_a", "file_b", "file_c"],
              "pool: список в порядке добавления")

        seq = [st.greeting_video_next() for _ in range(5)]
        check(seq == [
            ("file_a", "video"), ("file_b", "video"), ("file_c", "video"),
            ("file_a", "video"), ("file_b", "video"),
        ], "pool: round-robin по кругу (курсор переживает несколько вызовов)")

        st.greeting_video_clear()
        check(st.greeting_video_list() == [] and st.greeting_video_next() is None,
              "pool: clear очищает пул целиком")
        st.close()


def test_admin_panel_storage():
    print("== admin panel storage (профили/журнал) ==")
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d) / "ap.sqlite3")
        for i in range(3):
            st.save_profile({
                "user_id": 100 + i, "username": f"u{i}", "vertical": "Gambling",
                "grade": "C-Level" if i else "Инвестор", "profession": "CEO",
                "request": "r", "name": f"Name{i}", "company": "Acme", "linkedin": "-",
            })
        st.save_profile({
            "user_id": 200, "username": "other", "vertical": "Betting",
            "grade": "Senior", "profession": "Manager", "request": "r",
            "name": "Другой", "company": "OtherCo", "linkedin": "-",
        })
        check(st.count() == 4, "admin: count всего")
        check(st.count_since(24) == 4, "admin: count_since включает свежие")
        page = st.profiles_page(0, 2)
        check(len(page) == 2 and page[0]["id"] == 4, "admin: profiles_page — сначала свежие")
        found = st.search_profiles("Другой")
        check(len(found) == 1 and found[0]["id"] == 4, "admin: search по имени")
        found = st.search_profiles("200")
        check(len(found) == 1 and found[0]["user_id"] == 200, "admin: search по user_id")
        found = st.search_profiles("@u1")
        check(len(found) == 1 and found[0]["username"] == "u1", "admin: search по @username")
        found = st.search_profiles("Betting")
        check(len(found) == 1, "admin: search по вертикали")

        check(st.user_mute_chats(999) == [], "admin: user_mute_chats пусто без мутов")
        st.add_group_mute(-500, 999)
        check(st.user_mute_chats(999) == [-500], "admin: user_mute_chats видит мут (peek, не удаляет)")
        check(st.user_mute_chats(999) == [-500], "admin: повторный вызов не удаляет запись")

        check(st.get_gate_prompt(-500, 999) is None, "gate_prompt: пусто до set_gate_prompt")
        st.set_gate_prompt(-500, 999, 7001)
        check(st.get_gate_prompt(-500, 999) == 7001, "gate_prompt: get не удаляет (в отличие от pop)")
        check(st.get_gate_prompt(-500, 999) == 7001, "gate_prompt: повторный get стабилен")
        st.clear_gate_prompt(-500, 999)
        check(st.get_gate_prompt(-500, 999) is None, "gate_prompt: clear снимает отметку")
        check(st.user_mute_chats(999) == [-500], "gate_prompt: clear не трогает сам мут")

        # аудитория рассылки — до блокировки никто не потерян
        check(len(st.profiles_for_broadcast()) == 4, "admin: profiles_for_broadcast(all) до блокировки")
        check(len(st.profiles_for_broadcast(vertical="Gambling")) == 3,
              "admin: profiles_for_broadcast по вертикали")
        check(len(st.profiles_for_broadcast(grade="Инвестор")) == 1,
              "admin: profiles_for_broadcast по грейду")

        r1 = st.get_profile(1)
        check(r1["contacted"] == 0 and r1["blocked"] == 0, "admin: contacted/blocked дефолт 0")
        st.set_contacted(1, True)
        check(st.get_profile(1)["contacted"] == 1, "admin: set_contacted")
        st.mark_blocked(100)  # user_id профиля #1
        check(st.get_profile(1)["blocked"] == 1, "admin: mark_blocked")

        # заблокировавший бота больше не попадает в выборку для рассылки
        blocked_ids = {r["user_id"] for r in st.profiles_for_broadcast()}
        check(100 not in blocked_ids, "admin: mark_blocked исключает юзера из рассылки")
        check(len(st.profiles_for_broadcast()) == 3, "admin: profiles_for_broadcast(all) после блокировки")

        check(st.audit_log_count() == 0, "admin: журнал пуст изначально")
        st.log_action(42, "contacted", "анкета #1: отмечена")
        st.log_action(42, "broadcast", "все: получателей 3")
        check(st.audit_log_count() == 2, "admin: log_action пишет записи")
        rows = st.audit_log_page(0, 10)
        check(rows[0]["action"] == "broadcast", "admin: audit_log_page — сначала свежие")
        st.close()


# --- 4. Сценарная симуляция флоу (fake Telegram) --------------------------

class FakeFile:
    def __init__(self, file_id, mime_type=None):
        self.file_id = file_id
        self.mime_type = mime_type


class FakeMessage:
    _seq = 1000

    def __init__(self, text="", chat_id=555, animation=None, photo=None,
                 video=None, document=None, entities=None):
        self.text = text
        self.chat_id = chat_id
        self.animation = animation
        self.photo = photo
        self.video = video
        self.document = document
        self.entities = entities
        FakeMessage._seq += 1
        self.message_id = FakeMessage._seq
        self.deleted = False

    async def delete(self):
        self.deleted = True

    async def reply_text(self, text, **kw):
        return FakeMessage(text, self.chat_id)

    async def reply_document(self, **kw):
        return None

    async def delete(self):
        self.deleted = True


class FakeQuery:
    def __init__(self, data, chat_id=555, message=None):
        self.data = data
        self.chat_id = chat_id
        self.answered = False
        self.last_answer_text = None
        self.message = message or FakeMessage("stub", chat_id)

    async def answer(self, *a, **k):
        self.answered = True
        self.last_answer_text = a[0] if a else k.get("text")

    async def edit_message_text(self, text, reply_markup=None, **kw):
        self.message.text = text
        self.edited_markup = reply_markup
        return True

    async def edit_message_caption(self, caption=None, reply_markup=None, **kw):
        self.message.caption = caption
        self.edited_markup = reply_markup
        return True


class FakeBot:
    def __init__(self):
        self.username = "GamblingCommunitybot"
        self.edits = 0
        self.sent = []
        self.invite_links = []
        self.fail_invite = False
        self.member_status_map = {}  # user_id -> ChatMemberStatus, для get_chat_member
        self.member_usernames = {}  # user_id -> username, для get_chat_member
        self.member_tag_map = {}  # user_id -> tag, для get_chat_member/set_chat_member_tag
        self.set_tag_calls = []  # (chat_id, user_id, tag)
        self.deleted_msgs = []  # (chat_id, message_id)

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kw):
        self.edits += 1
        self.last_text = text
        self.last_markup = kw.get("reply_markup")
        return True

    async def edit_message_media(self, media=None, chat_id=None, message_id=None, **kw):
        self.media_edits = getattr(self, "media_edits", 0) + 1
        return True

    async def edit_message_reply_markup(self, chat_id=None, message_id=None, **kw):
        return True

    async def delete_message(self, chat_id, message_id):
        self.deleted_msgs.append((chat_id, message_id))
        return True

    async def send_message(self, chat_id, text="", **kw):
        self.sent.append((chat_id, text))
        self.last_send_kwargs = kw
        return FakeMessage(text, chat_id)

    async def send_animation(self, chat_id, file_id, caption="", **kw):
        self.sent.append((chat_id, "[animation]"))
        return FakeMessage(caption, chat_id)

    async def send_photo(self, chat_id, file_id, caption="", **kw):
        self.sent.append((chat_id, "[photo]"))
        return FakeMessage(caption, chat_id)

    async def send_video(self, chat_id, file_id, caption="", **kw):
        self.sent.append((chat_id, "[video]"))
        return FakeMessage(caption, chat_id)

    async def send_document(self, chat_id, document=None, filename="", caption="", **kw):
        self.sent.append((chat_id, f"[document:{filename}]"))
        self.documents = getattr(self, "documents", [])
        self.documents.append((chat_id, filename, caption))
        return FakeMessage(caption, chat_id)

    async def create_chat_invite_link(self, chat_id, member_limit=None, name=None, **kw):
        if self.fail_invite:
            raise RuntimeError("fake invite failure")
        link_value = f"https://t.me/+FAKE{len(self.invite_links) + 1}"
        self.invite_links.append((chat_id, member_limit, name, link_value))

        class _Link:
            invite_link = link_value

        return _Link()

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, **kw):
        self.restricts = getattr(self, "restricts", [])
        self.restricts.append((chat_id, user_id, permissions))
        return True

    async def get_chat(self, chat_id):
        class _FakeChat:
            permissions = None
        return _FakeChat()

    async def get_chat_member_count(self, chat_id):
        return getattr(self, "fake_member_count", 5219)

    async def get_chat_member(self, chat_id, user_id):
        from telegram.constants import ChatMemberStatus

        class _Member:
            def __init__(self, status, user, tag):
                self.status = status
                self.user = user
                self.tag = tag

        status = self.member_status_map.get(user_id, ChatMemberStatus.MEMBER)
        user = FakeUser(user_id, self.member_usernames.get(user_id, ""))
        tag = self.member_tag_map.get(user_id)
        return _Member(status, user, tag)

    async def set_chat_member_tag(self, chat_id, user_id, tag=None, **kw):
        self.set_tag_calls.append((chat_id, user_id, tag))
        self.member_tag_map[user_id] = tag
        return True

    # платный вход (09.09.2026): выселение = ban + unban, инвойс Stars из бота
    async def ban_chat_member(self, chat_id, user_id, **kw):
        self.bans = getattr(self, "bans", [])
        self.bans.append((chat_id, user_id))
        return True

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=None, **kw):
        self.unbans = getattr(self, "unbans", [])
        self.unbans.append((chat_id, user_id, only_if_banned))
        return True

    async def send_invoice(self, chat_id, **kw):
        self.invoices = getattr(self, "invoices", [])
        self.invoices.append((chat_id, kw))
        return FakeMessage("[invoice]", chat_id)


class FakeUser:
    def __init__(self, uid=42, username="tester"):
        self.id = uid
        self.username = username
        self.full_name = username or str(uid)


class FakeChat:
    def __init__(self, chat_id=555, chat_type="private"):
        self.id = chat_id
        self.type = chat_type


class FakeUpdate:
    def __init__(self, message=None, query=None, user=None):
        self.message = message
        self.callback_query = query
        self.effective_message = message or (query.message if query else None)
        self.effective_user = user or FakeUser()
        chat_id = message.chat_id if message else (query.chat_id if query else 555)
        self.effective_chat = FakeChat(chat_id)


class FakeApplication:
    """create_task как в PTB, но с сохранением task'ов — тест может дождаться
    фоновой рассылки через asyncio.gather(*ctx.application.created_tasks)."""

    def __init__(self):
        self.created_tasks = []

    def create_task(self, coro, **kw):
        task = asyncio.ensure_future(coro)
        self.created_tasks.append(task)
        return task


def kb_texts(markup) -> list[str]:
    """Плоский список подписей кнопок клавиатуры — для проверки, что кнопка есть/нет."""
    if markup is None:
        return []
    return [btn.text for row in markup.inline_keyboard for btn in row]


class FakeContext:
    def __init__(self, bot_data):
        self.bot = FakeBot()
        self.bot_data = bot_data
        self.user_data = {}
        self.chat_data = {}
        self.application = FakeApplication()


def _bot_data(tmpdir):
    from config import Settings
    settings = Settings(
        bot_token="x",
        base_dir=Path(tmpdir),
        database_path=Path(tmpdir) / "s.sqlite3",
        admin_ids=(42,),
        community_invite_url="https://t.me/+TEST",
        google_sheets_enabled=False,
        google_sheets_spreadsheet_id="",
        google_sheets_worksheet_name="Анкеты",
        google_sheets_credentials_path=None,
        community_chat_id=-100999888777,
    )
    from google_sheets_sync import SheetSync
    from content import Content
    from guro_storage import GuroStorage
    storage = Storage(settings.database_path)
    return {
        "settings": settings,
        "storage": storage,
        "sheet": SheetSync(settings),
        "content": Content(storage),
        "guro_storage": GuroStorage(settings.database_path),
    }


async def _run_scenarios():
    print("== flow simulation ==")
    import handlers.flow as F
    from telegram.ext import ConversationHandler

    # --- /start в ГРУППЕ -> редирект в личку, анкета не разворачивается ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        grp_msg = FakeMessage("/start", chat_id=-777)
        grp_update = FakeUpdate(message=grp_msg, user=FakeUser(700))
        grp_update.effective_chat.type = "supergroup"
        st = await F.start(grp_update, ctx)
        check(st == ConversationHandler.END, "start-group: /start в группе -> END, анкета не начинается")
        check(grp_msg.deleted, "start-group: команда /start в группе тоже удаляется")
        group_sent = [t for cid, t in ctx.bot.sent if cid == -777]
        check(len(group_sent) == 1 and "личном сообщении" in group_sent[0],
              "start-group: в группу ушло сообщение-редирект")
        markup = ctx.bot.last_send_kwargs.get("reply_markup")
        check(markup is not None
              and markup.inline_keyboard[0][0].to_dict().get("url") == f"https://t.me/{ctx.bot.username}",
              "start-group: кнопка ведёт на бота")
        check(markup.inline_keyboard[0][0].to_dict().get("style") == "primary",
              "start-group: кнопка синяя")

        # повторный /start в той же группе -> предыдущий редирект заменяется (singleton)
        grp_msg2 = FakeMessage("/start", chat_id=-777)
        grp_update2 = FakeUpdate(message=grp_msg2, user=FakeUser(701))
        grp_update2.effective_chat.type = "supergroup"
        await F.start(grp_update2, ctx)
        check(any(cid == -777 for cid, _mid in ctx.bot.deleted_msgs),
              "start-group: предыдущий редирект удалён (singleton)")

    # --- сценарий A: обычный путь (Gambling / C-Level / профессия) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        u = FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999))
        st = await F.start(u, ctx)
        check(st == F.S.LANG, "A: start->LANG (выбор языка)")
        check(u.message.deleted, "A: команда /start удалена (Clean Chat)")
        st = await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx)
        check(st == F.S.WELCOME and ctx.user_data["lang"] == "ru", "A: язык ru -> WELCOME")
        check("5219" in ctx.bot.last_text and "{members}" not in ctx.bot.last_text,
              "A: живой счётчик участников подставлен в welcome")

        st = await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
        check(st == F.S.VERTICAL, "A: begin->VERTICAL")

        st = await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0")), ctx)
        check(st == F.S.GRADE and ctx.user_data["vertical_key"] == "Gambling", "A: vertical Gambling")

        import ui
        vkb = ui.vertical_kb(bd["content"])
        first = vkb.inline_keyboard[0][0].to_dict()
        check(first.get("icon_custom_emoji_id") == C.VERTICAL_EMOJI_IDS[0],
              "кнопка вертикали Gambling с премиум-иконкой")
        check(len(C.VERTICAL_EMOJI_IDS) == len(C.VERTICALS), "иконка задана на каждую вертикаль")
        check(len(C.VERTICAL_STYLES) == len(C.VERTICALS), "цвет задан на каждую вертикаль")
        flat = [b.to_dict() for row in vkb.inline_keyboard for b in row]
        for i, name in enumerate(C.VERTICALS):
            expected = "primary" if name in ("Gambling", "Dating", "E-Commerce", "Other") else "success"
            check(flat[i].get("style") == expected, f"цвет вертикали {name} == {expected}")

        st = await F.pick_grade(FakeUpdate(query=FakeQuery("g:0")), ctx)
        check(st == F.S.PROFESSION, "A: grade C-Level -> PROFESSION")

        st = await F.profession_page(FakeUpdate(query=FakeQuery("pg:1")), ctx)
        check(st == F.S.PROFESSION and ctx.user_data["page"] == 1, "A: pagination")

        st = await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx)
        check(st == F.S.REQUEST and ctx.user_data["profile"]["profession"], "A: profession picked")

        st = await F.request_text(FakeUpdate(message=FakeMessage("ищу партнёров")), ctx)
        check(st == F.S.NAME, "A: request -> NAME")
        st = await F.name_text(FakeUpdate(message=FakeMessage("Иван")), ctx)
        check(st == F.S.COUNTRY, "A: name -> COUNTRY")
        st = await F.country_text(FakeUpdate(message=FakeMessage("Украина")), ctx)
        check(st == F.S.COMPANY, "A: country -> COMPANY")
        st = await F.company_text(FakeUpdate(message=FakeMessage("Acme")), ctx)
        check(st == F.S.LINKEDIN, "A: company -> LINKEDIN")
        st = await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "A: finish END")

        rows = bd["storage"].all_profiles()
        check(len(rows) == 1, "A: одна анкета в БД")
        p = rows[0]
        check(p["vertical"] == "Gambling" and p["grade"] == "C-Level", "A: поля анкеты")
        check(p["country"] == "Украина", "A: страна сохранена")
        check(p["linkedin"] == C.SKIPPED_VALUE, "A: linkedin пропущен")
        check(len(ctx.bot.sent) >= 1, "A: уведомление админу отправлено")
        # Платный вход (09.09.2026): новый человек в финале видит экран
        # оплаты, ссылку в группу получает только после оплаты.
        check(len(ctx.bot.invite_links) == 0, "A: новому ссылка в группу ДО оплаты не создаётся")
        check(ctx.bot.last_text == C.PAYWALL_TEXT, "A: финал нового — экран оплаты")
        a_btns = kb_texts(ctx.bot.last_markup)
        check(a_btns[0].startswith("Криптой") and a_btns[-1] == "Оплачу позже",
              f"A: под экраном оплаты кнопки, крипта первой: {a_btns}")
        check(len(ctx.bot.documents) == 1, "A: медиакит отправлен и перед экраном оплаты — один раз")
        doc_chat, doc_name, doc_caption = ctx.bot.documents[0]
        check(doc_name == "GURO-Mediakit-RU.pdf", "A: медиакит RU-файл (lang=ru)")
        check(doc_caption == C.MEDIA_KIT_CAPTION, "A: подпись медиакита RU из CMS-дефолта")
        check(doc_chat == 555, "A: медиакит уходит в тот же чат, что и анкета (screen_chat)")

    # --- сценарий B: инвестор-ветка (Gambling) ---
    # Платный вход (09.09.2026): у 999 подписка уже есть (оплатил в
    # приложении до конца анкеты) — он должен получить ПРЕЖНИЙ финал со
    # ссылкой, минуя экран оплаты. Подписка на id=42, а не 999: последний
    # шаг (linkedin_text) идёт через FakeUpdate без user=, и финал видит
    # дефолтного FakeUser() с id=42 — тот же нюанс, что в сценарии A.
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["guro_storage"].activate_subscription(42, 30)
        ctx = FakeContext(bd)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx)
        await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0")), ctx)
        inv_idx = len(C.GRADES)  # индекс грейда «Инвестор»
        st = await F.pick_grade(FakeUpdate(query=FakeQuery(f"g:{inv_idx}")), ctx)
        check(st == F.S.INV_TYPE, "B: -> INV_TYPE")
        st = await F.pick_investor_type(FakeUpdate(query=FakeQuery("it:0")), ctx)
        check(st == F.S.INV_AMOUNT, "B: -> INV_AMOUNT")
        st = await F.pick_investor_amount(FakeUpdate(query=FakeQuery("ia:1")), ctx)
        check(st == F.S.INV_NEEDS, "B: -> INV_NEEDS")
        await F.toggle_need(FakeUpdate(query=FakeQuery("in:0")), ctx)
        await F.toggle_need(FakeUpdate(query=FakeQuery("in:2")), ctx)
        check(ctx.user_data["needs"] == [0, 2], "B: needs выбраны")
        st = await F.investor_needs_done(FakeUpdate(query=FakeQuery("in_done")), ctx)
        check(st == F.S.REQUEST, "B: needs done -> REQUEST")
        await F.request_text(FakeUpdate(message=FakeMessage("ищу стартапы")), ctx)
        await F.name_text(FakeUpdate(message=FakeMessage("VC Ann")), ctx)
        await F.country_text(FakeUpdate(message=FakeMessage("США")), ctx)
        await F.company_text(FakeUpdate(message=FakeMessage("Fund X")), ctx)
        st = await F.linkedin_text(FakeUpdate(message=FakeMessage("linkedin.com/in/x")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "B: finish END")
        p = bd["storage"].all_profiles()[0]
        check(p["grade"] == "Инвестор" and p["investor_type"] and p["investor_amount"], "B: инвестор-поля")
        check(p["investor_needs"] == logic.needs_to_text([0, 2]), "B: needs текст")
        check(not p["profession"], "B: профессия пуста у инвестора")
        check(len(ctx.bot.invite_links) == 1, "B: оплатившему заранее — одноразовая ссылка сразу, без экрана оплаты")
        inv_chat, inv_limit, inv_name, inv_link = ctx.bot.invite_links[0]
        check(inv_chat == bd["settings"].community_chat_id, "B: ссылка на community_chat_id")
        check(inv_limit == 1, "B: member_limit=1 (одноразовая)")
        check(inv_name == "pgc_42", "B: имя ссылки помечено user_id")
        check(ctx.bot.last_markup.inline_keyboard[0][0].url == inv_link,
              "B: кнопка финала ведёт на созданную одноразовую ссылку")
        check(ctx.bot.last_text != C.PAYWALL_TEXT, "B: экран оплаты подписчику не показан")

    # --- сценарий C: Other-вертикаль + Другое-профессия + back ---
    # Подписка на 42 (см. сценарий B): иначе финал — экран оплаты, и путь
    # «сбой одноразовой ссылки → запасная общая» остался бы непроверенным.
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["guro_storage"].activate_subscription(42, 30)
        ctx = FakeContext(bd)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx)
        await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
        st = await F.pick_vertical(FakeUpdate(query=FakeQuery("v:7")), ctx)
        check(st == F.S.VERTICAL_OTHER, "C: Other -> VERTICAL_OTHER")
        # «Назад» с экрана своей вертикали — не тупик
        st = await F.vertical_other_back(FakeUpdate(query=FakeQuery("vo_back")), ctx)
        check(st == F.S.VERTICAL, "C: vo_back -> VERTICAL")
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:7")), ctx)
        st = await F.vertical_other_text(FakeUpdate(message=FakeMessage("AdTech")), ctx)
        check(st == F.S.GRADE and ctx.user_data["profile"]["vertical"] == "Other: AdTech", "C: свой текст вертикали")
        # back grade -> vertical
        st = await F.grade_back(FakeUpdate(query=FakeQuery("g_back")), ctx)
        check(st == F.S.VERTICAL, "C: grade_back -> VERTICAL")
        # снова в Other
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:7")), ctx)
        await F.vertical_other_text(FakeUpdate(message=FakeMessage("AdTech")), ctx)
        await F.pick_grade(FakeUpdate(query=FakeQuery("g:3")), ctx)  # Senior
        st = await F.profession_back(FakeUpdate(query=FakeQuery("p_back")), ctx)
        check(st == F.S.GRADE, "C: profession_back -> GRADE")
        await F.pick_grade(FakeUpdate(query=FakeQuery("g:3")), ctx)
        st = await F.profession_other(FakeUpdate(query=FakeQuery("p_other")), ctx)
        check(st == F.S.PROFESSION_OTHER, "C: -> PROFESSION_OTHER")
        # «Назад» с экрана своей должности — не тупик
        st = await F.profession_other_back(FakeUpdate(query=FakeQuery("po_back")), ctx)
        check(st == F.S.PROFESSION, "C: po_back -> PROFESSION")
        st = await F.profession_other(FakeUpdate(query=FakeQuery("p_other")), ctx)
        st = await F.profession_other_text(FakeUpdate(message=FakeMessage("Growth Lead")), ctx)
        check(st == F.S.REQUEST, "C: своя профессия -> REQUEST")
        await F.request_text(FakeUpdate(message=FakeMessage("трафик")), ctx)
        await F.name_text(FakeUpdate(message=FakeMessage("Bob")), ctx)
        await F.country_text(FakeUpdate(message=FakeMessage("Germany")), ctx)
        await F.company_text(FakeUpdate(message=FakeMessage("NDA")), ctx)
        ctx.bot.fail_invite = True  # симулируем сбой Bot API при создании ссылки
        await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        p = bd["storage"].all_profiles()[0]
        check(p["profession"] == "Growth Lead", "C: своя профессия сохранена")
        check(ctx.bot.last_markup.inline_keyboard[0][0].url == bd["settings"].community_invite_url,
              "C: сбой создания ссылки -> фолбэк на статичный community_invite_url")

    # --- сценарий D: GIF на экране (text↔media пересоздаёт экран) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].set_media("ask_vertical", "GIFV", "animation")
        ctx = FakeContext(bd)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx)
        check(ctx.user_data.get("screen_kind") == "text", "D: welcome — текстовый экран")
        await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
        check(ctx.user_data.get("screen_kind") == "media", "D: экран вертикали стал media")
        check(any(s[1] == "[animation]" for s in ctx.bot.sent), "D: отправлена анимация")
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:1")), ctx)
        check(ctx.user_data.get("screen_kind") == "text", "D: грейд — снова текстовый экран")

    # --- сценарий E: админ жмёт /start — сразу панель управления, без анкеты ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)  # admin_ids=(42,) — дефолтный FakeUser() как раз id=42
        ctx = FakeContext(bd)
        u = FakeUpdate(message=FakeMessage("/start"))
        st = await F.start(u, ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "E: админ /start -> END, без анкеты")
        check(u.message.deleted, "E: команда /start у админа тоже удаляется (Clean Chat)")
        check("Админ-панель" in ctx.bot.last_text, "E: /start сразу открывает панель управления")
        check(bd["storage"].count() == 0, "E: анкета за админом не создалась")

        # старое меню чистится, если уже было открыто (та же логика, что и у карточек)
        ctx.user_data["adm_chat"] = 555
        ctx.user_data["adm_mid"] = 8001
        u2 = FakeUpdate(message=FakeMessage("/start"))
        await F.start(u2, ctx)
        check((555, 8001) in ctx.bot.deleted_msgs, "E: повторный /start чистит старый экран /admin")

    # --- сценарий F: анкету заполнил юзер, забаненный администратором ---
    # (см. handlers/admin_users.usr_ban -> storage.ban_user) — бан НЕ должен
    # слетать от заполнения анкеты, доступ/ссылка не выдаются.
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].ban_user(999)
        ctx = FakeContext(bd)
        bu = FakeUser(999)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=bu), ctx)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru"), user=bu), ctx)
        await F.begin_form(FakeUpdate(query=FakeQuery("start_form"), user=bu), ctx)
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0"), user=bu), ctx)  # Gambling
        await F.pick_grade(FakeUpdate(query=FakeQuery("g:0"), user=bu), ctx)  # C-Level
        await F.pick_profession(FakeUpdate(query=FakeQuery("p:0"), user=bu), ctx)
        await F.request_text(FakeUpdate(message=FakeMessage("networking"), user=bu), ctx)
        await F.name_text(FakeUpdate(message=FakeMessage("Banned Guy"), user=bu), ctx)
        await F.country_text(FakeUpdate(message=FakeMessage("Nowhere"), user=bu), ctx)
        await F.company_text(FakeUpdate(message=FakeMessage("NDA"), user=bu), ctx)
        st = await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li"), user=bu), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "F: забаненный тоже доходит до конца анкеты")
        check(bd["storage"].count() == 1, "F: анкета забаненного сохранена (для истории)")
        check("ограничен" in ctx.bot.last_text.lower(), "F: показан banned_notice, не поздравление")
        check("Спасибо" not in ctx.bot.last_text, "F: обычный финальный текст НЕ показан")
        check(len(ctx.bot.invite_links) == 0, "F: одноразовая ссылка НЕ создаётся для забаненного")
        check(not any(uid == 999 and getattr(perm, "can_send_messages", None) is True
                      for _cid, uid, perm in getattr(ctx.bot, "restricts", [])),
              "F: unmute_after_profile не размутил забаненного")
        check(bd["storage"].is_banned(999), "F: бан остался в силе после заполнения анкеты")
        check(not getattr(ctx.bot, "documents", []), "F: медиакит НЕ отправляется забаненному")

    # --- сценарий G: страна проходит через GPT-нормализацию (мок) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["settings"].openai_api_key = "testkey"
        ctx = FakeContext(bd)
        import country_formatter as CF

        async def _fake_normalize(api_key, model, raw_text):
            return CF.NormalizedCountry(country_ru="Азербайджан", iso2="AZ")

        orig_normalize = F.normalize_country
        F.normalize_country = _fake_normalize
        try:
            await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx)
            await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx)
            await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
            await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0")), ctx)
            await F.pick_grade(FakeUpdate(query=FakeQuery("g:0")), ctx)
            await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx)
            await F.request_text(FakeUpdate(message=FakeMessage("networking")), ctx)
            await F.name_text(FakeUpdate(message=FakeMessage("Ali")), ctx)
            st = await F.country_text(FakeUpdate(message=FakeMessage("азер, столица баку")), ctx)
            check(st == F.S.COMPANY, "G: страна -> COMPANY")
            check(ctx.user_data["profile"]["country"] == "Азербайджан", "G: GPT нормализовал страну")
            check(ctx.user_data["profile"]["country_iso2"] == "AZ", "G: сохранён ISO-код")
            await F.company_text(FakeUpdate(message=FakeMessage("Acme")), ctx)
            await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
            p = bd["storage"].all_profiles()[0]
            check(p["country"] == "Азербайджан" and p["country_iso2"] == "AZ",
                  "G: нормализованная страна и ISO сохранены в БД")

            # GPT недоступен/вернул мусор -> фолбэк на сырой текст, iso2 пуст
            async def _fake_normalize_none(api_key, model, raw_text):
                return None

            F.normalize_country = _fake_normalize_none
            ctx2 = FakeContext(bd)
            await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(998)), ctx2)
            await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx2)
            await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx2)
            await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0")), ctx2)
            await F.pick_grade(FakeUpdate(query=FakeQuery("g:0")), ctx2)
            await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx2)
            await F.request_text(FakeUpdate(message=FakeMessage("networking")), ctx2)
            await F.name_text(FakeUpdate(message=FakeMessage("Bob")), ctx2)
            await F.country_text(FakeUpdate(message=FakeMessage("asdkjaskjd")), ctx2)
            check(ctx2.user_data["profile"]["country"] == "asdkjaskjd",
                  "G: GPT не распознал -> фолбэк на исходный текст")
            check(ctx2.user_data["profile"]["country_iso2"] == "",
                  "G: без ISO при фолбэке")
        finally:
            F.normalize_country = orig_normalize

        # без OPENAI_API_KEY GPT вообще не вызывается — как и раньше, сырой текст
        bd["settings"].openai_api_key = ""
        ctx3 = FakeContext(bd)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(997)), ctx3)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx3)
        await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx3)
        await F.pick_vertical(FakeUpdate(query=FakeQuery("v:0")), ctx3)
        await F.pick_grade(FakeUpdate(query=FakeQuery("g:0")), ctx3)
        await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx3)
        await F.request_text(FakeUpdate(message=FakeMessage("networking")), ctx3)
        await F.name_text(FakeUpdate(message=FakeMessage("Carl")), ctx3)
        await F.country_text(FakeUpdate(message=FakeMessage("Германия")), ctx3)
        check(ctx3.user_data["profile"]["country"] == "Германия",
              "G: без OPENAI_API_KEY -> GPT не вызывается, сырой текст как есть")


def test_country_formatter():
    print("== country formatter ==")
    from country_formatter import flag_from_iso2
    check(flag_from_iso2("AZ") == "🇦🇿", "flag_from_iso2 AZ")
    check(flag_from_iso2("us") == "🇺🇸", "flag_from_iso2 регистронезависимо")
    check(flag_from_iso2(None) == "", "flag_from_iso2 None -> пусто")
    check(flag_from_iso2("") == "", "flag_from_iso2 пустая строка -> пусто")
    check(flag_from_iso2("A1") == "", "flag_from_iso2 не-буквы -> пусто")
    check(flag_from_iso2("AZE") == "", "flag_from_iso2 не 2 буквы -> пусто")


def test_cms_storage():
    print("== cms storage/content ==")
    import tempfile as _tf
    from content import Content
    with _tf.TemporaryDirectory() as d:
        st = Storage(Path(d) / "c.sqlite3")
        c = Content(st)
        # дефолты
        check(c.btn("start") == C.BUTTON_DEFAULTS["start"], "btn default")
        check(c.txt("welcome") == C.TEXT_DEFAULTS["welcome"], "txt default")
        # override
        st.set_button_override("start", "Поехали")
        st.set_text_override("welcome", "Привет!")
        check(c.btn("start") == "Поехали", "btn override")
        check(c.txt("welcome") == "Привет!", "txt override")
        check("start" in st.overridden_buttons(), "overridden_buttons")
        check("welcome" in st.overridden_texts(), "overridden_texts")
        # media
        check(c.media("welcome") is None, "media default None")
        st.set_media("welcome", "FILE123", "animation")
        check(c.media("welcome") == ("FILE123", "animation"), "media set")
        check("welcome" in st.media_keys(), "media_keys")
        st.reset_media("welcome")
        check(c.media("welcome") is None, "media reset")
        # reset
        st.reset_button("start")
        st.reset_text("welcome")
        check(c.btn("start") == C.BUTTON_DEFAULTS["start"], "btn reset")
        check(c.txt("welcome") == C.TEXT_DEFAULTS["welcome"], "txt reset")
        # каталоги покрывают дефолты
        for _t, keys in C.BUTTON_CATALOG:
            for k in keys:
                check(k in C.BUTTON_DEFAULTS, f"btn catalog key {k} без дефолта")
        for k, _label in C.TEXT_CATALOG:
            check(k in C.TEXT_DEFAULTS, f"text catalog key {k} без дефолта")
        st.close()


async def _run_lang():
    print("== language selection ==")
    import handlers.flow as F

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx)
        st = await F.choose_lang(FakeUpdate(query=FakeQuery("lang:en")), ctx)
        check(st == F.S.WELCOME and ctx.user_data["lang"] == "en", "EN: язык en -> WELCOME")

        c = bd["content"].view("en")
        check(c.txt("welcome") == C.TEXT_DEFAULTS["welcome_en"], "EN: welcome берёт _en дефолт")
        check(c.txt("ask_request") == C.TEXT_DEFAULTS["ask_request_en"], "EN: ask_request _en")
        check(c.btn("skip") == "Skip" and c.btn("start") == "Get access", "EN: служебные кнопки EN")
        check(c.btn("v_0") == "Gambling" and c.btn("g_0") == "C-Level", "EN: данные не переводятся")
        check(c.btn("it_0") == C.BUTTON_DEFAULTS["it_0_en"], "EN: инвестор-кнопки EN")
        check(c.btn("g_inv") == "Investor", "EN: грейд Инвестор -> Investor")

        cru = bd["content"].view("ru")
        check(cru.txt("welcome") == C.TEXT_DEFAULTS["welcome"], "RU: базовые тексты как раньше")
        check(cru.btn("skip") == C.BUTTON_DEFAULTS["skip"], "RU: кнопки как раньше")

        # CMS-override EN-ключа применяется в EN-виде и не трогает RU
        bd["storage"].set_text_override("welcome_en", "EN OVERRIDE")
        check(c.txt("welcome") == "EN OVERRIDE", "EN: override welcome_en применился")
        check(cru.txt("welcome") == C.TEXT_DEFAULTS["welcome"], "RU: не затронут override-ом EN")

        # раскладка: обе кнопки языка в одну строку
        import ui
        lkb = ui.lang_kb(bd["content"])
        check(len(lkb.inline_keyboard) == 1 and len(lkb.inline_keyboard[0]) == 2,
              "кнопки языков в одну строку")
        en_b, ru_b = (b.to_dict() for b in lkb.inline_keyboard[0])
        check(en_b.get("style") == "success", "кнопка EN зелёная")
        check(ru_b.get("style") == "primary", "кнопка RU синяя")
        check(ru_b.get("icon_custom_emoji_id") == C.LANG_RU_EMOJI_ID,
              "кнопка RU с премиум-иконкой (не флаг РФ)")
        check("icon_custom_emoji_id" not in en_b, "кнопка EN без доп. иконки (свой флаг в тексте)")
        # кнопки выбора языка: русский БЕЗ флага, английский с флагом
        check(C.BUTTON_DEFAULTS["lang_ru"] == "Русский", "кнопка RU без флага")
        check("🇬🇧" in C.BUTTON_DEFAULTS["lang_en"], "кнопка EN с флагом")

        # полный EN-проход до конца анкеты
        st = await F.begin_form(FakeUpdate(query=FakeQuery("start_form")), ctx)
        check(st == F.S.VERTICAL, "EN: begin->VERTICAL")
        st = await F.pick_vertical(FakeUpdate(query=FakeQuery("v:1")), ctx)
        check(st == F.S.GRADE, "EN: vertical Betting")
        st = await F.pick_grade(FakeUpdate(query=FakeQuery("g:3")), ctx)
        check(st == F.S.PROFESSION, "EN: grade Senior -> PROFESSION")
        st = await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx)
        check(st == F.S.REQUEST, "EN: profession picked")
        st = await F.request_text(FakeUpdate(message=FakeMessage("networking")), ctx)
        check(st == F.S.NAME, "EN: request -> NAME")
        st = await F.name_text(FakeUpdate(message=FakeMessage("John")), ctx)
        check(st == F.S.COUNTRY, "EN: name -> COUNTRY")
        st = await F.country_text(FakeUpdate(message=FakeMessage("UK")), ctx)
        check(st == F.S.COMPANY, "EN: country -> COMPANY")
        st = await F.company_text(FakeUpdate(message=FakeMessage("Acme")), ctx)
        check(st == F.S.LINKEDIN, "EN: company -> LINKEDIN")
        st = await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "EN: finish END")
        check(len(bd["storage"].all_profiles()) == 1, "EN: анкета сохранена")
        check(len(ctx.bot.documents) == 1, "EN: медиакит отправлен один раз")
        _doc_chat, doc_name, doc_caption = ctx.bot.documents[0]
        check(doc_name == "GURO-Media-Kit-EN.pdf", "EN: медиакит EN-файл (lang=en)")
        check(doc_caption == C.MEDIA_KIT_CAPTION_EN, "EN: подпись медиакита EN из CMS-дефолта")
        fkb = ui.final_kb(bd["content"].view("ru"), "https://t.me/x")
        fbd = fkb.inline_keyboard[0][0].to_dict()
        check(fbd.get("style") == "primary", "кнопка «Вступить» синяя по умолчанию")
        check(fbd.get("icon_custom_emoji_id") == C.JOIN_BUTTON_EMOJI_ID,
              "кнопка «Вступить» с премиум-иконкой (ракета)")
        wbd = ui.welcome_kb(bd["content"].view("ru")).inline_keyboard[0][0].to_dict()
        check(wbd.get("style") == "primary"
              and wbd.get("icon_custom_emoji_id") == C.START_BUTTON_EMOJI_ID,
              "кнопка «Получить доступ»: синяя + звезда")

    # --- живой счётчик участников: сбой API -> фолбэк на статичную оценку ---
    with tempfile.TemporaryDirectory() as d:
        bd2 = _bot_data(d)
        ctx2 = FakeContext(bd2)

        async def _boom(chat_id):
            raise RuntimeError("boom")

        ctx2.bot.get_chat_member_count = _boom
        await F.start(FakeUpdate(message=FakeMessage("/start"), user=FakeUser(999)), ctx2)
        await F.choose_lang(FakeUpdate(query=FakeQuery("lang:ru")), ctx2)
        check(str(F._MEMBER_COUNT_FALLBACK) in ctx2.bot.last_text
              and "{members}" not in ctx2.bot.last_text,
              "счётчик участников: сбой API -> статичный фолбэк")


async def _run_admin_cms():
    print("== admin cms simulation ==")
    import handlers.admin_cms as A

    # РЕГРЕССИЯ 24.07.2026: у admin_open/admin_start (СВОИ entry_points,
    # отдельные от flow.start()!) не было проверки чата — админ, набравший
    # /start или /admin ПРЯМО В ГРУППЕ, разворачивал там всю панель на виду
    # у всех. Проверяем обе точки входа отдельно, т.к. flow.py их не покрывает.
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        grp_msg = FakeMessage("/start", chat_id=-777)
        grp_update = FakeUpdate(message=grp_msg, user=FakeUser(42))
        grp_update.effective_chat.type = "supergroup"
        st = await A.admin_start(grp_update, ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "cms-group: admin_start в группе -> END, панель не открыта")
        check(grp_msg.deleted, "cms-group: команда /start в группе удаляется")
        group_sent = [t for cid, t in ctx.bot.sent if cid == -777]
        check(len(group_sent) == 1 and "личном сообщении" in group_sent[0],
              "cms-group: admin_start шлёт редирект в группу")

        grp_msg2 = FakeMessage("/admin", chat_id=-777)
        grp_update2 = FakeUpdate(message=grp_msg2, user=FakeUser(42))
        grp_update2.effective_chat.type = "supergroup"
        st2 = await A.admin_open(grp_update2, ctx)
        check(st2 == ConversationHandler.END, "cms-group: admin_open в группе -> END, панель не открыта")
        check(grp_msg2.deleted, "cms-group: команда /admin в группе удаляется")
        check(any(cid == -777 for cid, _mid in ctx.bot.deleted_msgs),
              "cms-group: предыдущий редирект (от /start) заменён (singleton)")

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        # /admin от админа (id=42)
        st = await A.admin_open(FakeUpdate(message=FakeMessage("/admin"), user=FakeUser(42)), ctx)
        check(st == A.BROWSE, "cms: open -> BROWSE")
        st = await A.nav_btns(FakeUpdate(query=FakeQuery("acms_btns")), ctx)
        check(st == A.BROWSE, "cms: btns list")
        st = await A.nav_btncat(FakeUpdate(query=FakeQuery("acms_btncat:0")), ctx)
        check(st == A.BROWSE, "cms: btn category")
        st = await A.edit_btn_start(FakeUpdate(query=FakeQuery("acms_eb:start")), ctx)
        check(st == A.WAIT_TEXT and ctx.user_data["cms_target"] == ("btn", "start"), "cms: edit btn -> WAIT")
        st = await A.save_new_value(FakeUpdate(message=FakeMessage("Поехали 🚀")), ctx)
        check(bd["content"].btn("start") == "Поехали 🚀", "cms: кнопка сохранена")
        check(st == A.WAIT_TEXT, "cms: после сохранения остаёмся в WAIT")
        await A.reset_value(FakeUpdate(query=FakeQuery("acms_reset")), ctx)
        check(bd["content"].btn("start") == C.BUTTON_DEFAULTS["start"], "cms: кнопка сброшена")

        # текст
        await A.nav_texts(FakeUpdate(query=FakeQuery("acms_texts")), ctx)
        await A.edit_text_start(FakeUpdate(query=FakeQuery("acms_et:final")), ctx)
        await A.save_new_value(FakeUpdate(message=FakeMessage("Новый финал")), ctx)
        check(bd["content"].txt("final") == "Новый финал", "cms: текст сохранён")

        # медиа: установка GIF на экран приветствия
        await A.nav_media(FakeUpdate(query=FakeQuery("acms_media")), ctx)
        st = await A.edit_media_start(FakeUpdate(query=FakeQuery("acms_em:welcome")), ctx)
        check(st == A.WAIT_MEDIA and ctx.user_data["cms_target"] == ("media", "welcome"), "cms: media -> WAIT_MEDIA")
        gif_msg = FakeMessage(animation=FakeFile("GIFWELCOME"))
        st = await A.save_media(FakeUpdate(message=gif_msg), ctx)
        check(bd["content"].media("welcome") == ("GIFWELCOME", "animation"), "cms: медиа сохранено")
        await A.reset_value(FakeUpdate(query=FakeQuery("acms_reset")), ctx)
        check(bd["content"].media("welcome") is None, "cms: медиа удалено")

        # меню группы (панель ссылок)
        st = await A.nav_groupmenu(FakeUpdate(query=FakeQuery("acms_gm")), ctx)
        check(st == A.BROWSE, "cms: меню группы — список")
        st = await A.gm_open_button(FakeUpdate(query=FakeQuery("acms_gmbtn:0")), ctx)
        check(st == A.BROWSE, "cms: открыта кнопка панели")
        st = await A.gm_edit_label(FakeUpdate(query=FakeQuery("acms_gmlabel:0")), ctx)
        check(st == A.WAIT_GM_TEXT and ctx.user_data["cms_target"] == ("gm_label", 0),
              "cms: правка текста кнопки -> WAIT_GM_TEXT")
        await A.gm_save_text(FakeUpdate(message=FakeMessage("Правила")), ctx)
        check(bd["storage"].get_menu_button(0)["label"] == "Правила", "cms: текст кнопки сохранён")
        await A.gm_edit_url(FakeUpdate(query=FakeQuery("acms_gmurl:0")), ctx)
        await A.gm_save_text(FakeUpdate(message=FakeMessage("https://t.me/new")), ctx)
        check(bd["storage"].get_menu_button(0)["url"] == "https://t.me/new", "cms: ссылка сохранена")
        await A.gm_set_style(FakeUpdate(query=FakeQuery("acms_gmstyle:0:success")), ctx)
        check(bd["storage"].get_menu_button(0)["style"] == "success", "cms: цвет сохранён")

        class FakeEnt:
            def __init__(self, t, cid):
                self.type = t
                self.custom_emoji_id = cid

        await A.gm_edit_emoji(FakeUpdate(query=FakeQuery("acms_gmemoji:0")), ctx)
        await A.gm_save_emoji(
            FakeUpdate(message=FakeMessage("🔥", entities=[FakeEnt("custom_emoji", "5555")])), ctx)
        check(bd["storage"].get_menu_button(0)["emoji_id"] == "5555", "cms: премиум-эмодзи из entity")
        await A.gm_edit_emoji(FakeUpdate(query=FakeQuery("acms_gmemoji:0")), ctx)
        await A.gm_save_emoji(FakeUpdate(message=FakeMessage("7777")), ctx)
        check(bd["storage"].get_menu_button(0)["emoji_id"] == "7777", "cms: премиум-эмодзи числом")
        await A.gm_toggle(FakeUpdate(query=FakeQuery("acms_gmtoggle:0")), ctx)
        check(bd["storage"].get_menu_button(0)["enabled"] == 0, "cms: кнопка выключена")
        await A.gm_reset(FakeUpdate(query=FakeQuery("acms_gmreset:0")), ctx)
        b0 = bd["storage"].get_menu_button(0)
        check(b0["label"] == "Terms" and b0["style"] is None and b0["emoji_id"] is None
              and b0["enabled"] == 1, "cms: кнопка сброшена к умолчанию")

        exit_mid = ctx.user_data.get("adm_mid")
        st = await A.admin_exit(FakeUpdate(query=FakeQuery("acms_exit")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "cms: выход END")
        check(any(mid == exit_mid for _cid, mid in ctx.bot.deleted_msgs),
              "cms: выход удаляет сообщение, а не пишет «Готово»")

        # не-админ не входит
        ctx2 = FakeContext(bd)
        st = await A.admin_open(FakeUpdate(message=FakeMessage("/admin"), user=FakeUser(999)), ctx2)
        check(st == ConversationHandler.END, "cms: не-админ не входит")


def test_captcha_logic():
    print("== captcha logic ==")
    import random as _r
    rng = _r.Random(123)
    for _ in range(300):
        a, b = logic.make_captcha(rng)
        check(10 <= a <= 99 and 2 <= b <= 49, "captcha операнды в диапазоне")
        ans = a + b
        opts = logic.captcha_options(ans, 4, rng)
        check(len(opts) == 4, "вариантов ровно 4")
        check(len(set(opts)) == 4, "варианты различны")
        check(ans in opts, "верный ответ присутствует")
        check(all(o > 0 for o in opts), "все варианты положительны")
    t = logic.render_captcha_text("Решите: {captcha} сейчас", 15, 8)
    check("15 + 8 = ?" in t and "{captcha}" not in t, "подстановка по плейсхолдеру")
    t2 = logic.render_captcha_text("Без плейсхолдера", 2, 3)
    check(t2.endswith("2 + 3 = ?</b>"), "дописывание без плейсхолдера")
    opts6 = logic.captcha_options(20, 6, rng)
    check(len(opts6) == 6 and 20 in opts6, "вариантов можно сделать 6")


def test_menu():
    print("== group menu (panel) ==")
    import tempfile as _tf
    import ui
    b = ui.link_button("Terms", "https://t.me/x", style="success", emoji_id="123")
    d = b.to_dict()
    check(d.get("style") == "success" and d.get("icon_custom_emoji_id") == "123",
          "link_button прокидывает style/emoji")
    check(d.get("url") == "https://t.me/x", "link_button url")
    b2 = ui.link_button("📢 News", "https://t.me/y", emoji_id="55")
    check(b2.to_dict().get("text") == "News", "ведущий эмодзи срезан при premium-иконке")
    dd = ui.link_button("Plain", "https://t.me/z").to_dict()
    check(dd.get("style") == "primary" and "icon_custom_emoji_id" not in dd,
          "без стиля — синий по умолчанию, без эмодзи")
    dg = ui.link_button("Grey", "https://t.me/z", style="default").to_dict()
    check("style" not in dg, "явный «Обычный» из CMS даёт серый")
    check(ui._strip_leading_emoji("❤️") == "❤️", "кнопка-эмодзи не опустошается")

    with _tf.TemporaryDirectory() as d2:
        st = Storage(Path(d2) / "m.sqlite3")
        check(len(st.menu_buttons()) == len(C.MENU_BUTTON_DEFAULTS), "menu_buttons засеяны")
        check(st.get_menu_button(0)["label"] == "Terms", "slot 0 = Terms")
        st.update_menu_button(0, style="success", emoji_id="999")
        b0 = st.get_menu_button(0)
        check(b0["style"] == "success" and b0["emoji_id"] == "999", "update style/emoji")
        st.update_menu_button(1, enabled=0)
        check(len(st.menu_buttons(only_enabled=True)) == len(C.MENU_BUTTON_DEFAULTS) - 1,
              "выключенная не в enabled")
        kb = ui.group_menu_kb(st)
        enabled_n = len(C.MENU_BUTTON_DEFAULTS) - 1
        # +1 строка/кнопка — фиксированная реф-кнопка (не из CMS, добавляется всегда)
        check(kb is not None
              and sum(len(r) for r in kb.inline_keyboard) == enabled_n + 1
              and len(kb.inline_keyboard) == math.ceil(enabled_n / 2) + 1,
              "group_menu_kb по enabled, по 2 в ряд")
        first = kb.inline_keyboard[0][0].to_dict()
        check(first.get("style") == "success" and first.get("icon_custom_emoji_id") == "999",
              "kb-кнопка несёт оформление")
        st.reset_menu_button(0)
        b0r = st.get_menu_button(0)
        check(b0r["style"] is None and b0r["emoji_id"] is None and b0r["enabled"] == 1,
              "reset кнопки")
        st.close()


async def _run_captcha_sim():
    print("== captcha group simulation ==")
    import handlers.group_captcha as G
    from telegram.constants import ChatMemberStatus

    class CapUser:
        def __init__(self, uid, is_bot=False, full_name="New Guy"):
            self.id = uid
            self.is_bot = is_bot
            self.full_name = full_name
            self.username = "newguy"

    class CapMember:
        def __init__(self, status, is_member=None, user=None):
            self.status = status
            self.is_member = is_member
            self.user = user

    class CapChat:
        def __init__(self, cid=-1001924507124, permissions=None):
            self.id = cid
            self.permissions = permissions

    class CapCMU:
        def __init__(self, chat, old, new):
            self.chat = chat
            self.old_chat_member = old
            self.new_chat_member = new

    class CapMsg:
        _seq = 5000

        def __init__(self, chat_id, animation=None, video=None, photo=None):
            CapMsg._seq += 1
            self.message_id = CapMsg._seq
            self.chat_id = chat_id
            self.animation = animation
            self.video = video
            self.photo = photo
            self.deleted = False
            self.caption_edits = 0
            self.text_edits = 0

        async def delete(self):
            self.deleted = True

    class CapBot:
        username = "GamblingCommunitybot"

        def __init__(self):
            self.restricts = []  # (chat_id, uid, can_send_messages)
            self.sent = []
            self.markups = []
            self.thread_ids = []  # message_thread_id по каждому sent-сообщению
            self.media_ids = []  # file_id по каждому sent-сообщению (None для текстовых)
            self.reply_to_ids = []  # reply_to_message_id по каждому sent-сообщению
            self.member_status_map = {}  # uid -> статус для get_chat_member
            self.deleted_msgs = []  # (chat_id, message_id)

        async def restrict_chat_member(self, chat_id, user_id, permissions=None, **kw):
            self.restricts.append((chat_id, user_id, permissions.can_send_messages))
            return True

        async def get_chat(self, chat_id):
            return CapChat(chat_id, permissions=None)

        async def get_chat_member(self, chat_id, user_id):
            return CapMember(
                self.member_status_map.get(user_id, ChatMemberStatus.MEMBER)
            )

        async def delete_message(self, chat_id, message_id):
            self.deleted_msgs.append((chat_id, message_id))
            return True

        async def send_message(self, chat_id, text="", **kw):
            self.sent.append(("text", text))
            self.markups.append(kw.get("reply_markup"))
            self.thread_ids.append(kw.get("message_thread_id"))
            self.media_ids.append(None)
            self.reply_to_ids.append(kw.get("reply_to_message_id"))
            return CapMsg(chat_id)

        async def send_animation(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("animation", caption))
            self.markups.append(kw.get("reply_markup"))
            self.thread_ids.append(kw.get("message_thread_id"))
            self.media_ids.append(file_id)
            self.reply_to_ids.append(kw.get("reply_to_message_id"))
            return CapMsg(chat_id, animation=object())

        async def send_video(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("video", caption))
            self.markups.append(kw.get("reply_markup"))
            self.thread_ids.append(kw.get("message_thread_id"))
            self.media_ids.append(file_id)
            self.reply_to_ids.append(kw.get("reply_to_message_id"))
            return CapMsg(chat_id, video=object())

        async def send_photo(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("photo", caption))
            self.markups.append(kw.get("reply_markup"))
            self.thread_ids.append(kw.get("message_thread_id"))
            self.media_ids.append(file_id)
            self.reply_to_ids.append(kw.get("reply_to_message_id"))
            return CapMsg(chat_id, photo=object())

    class CapQuery:
        def __init__(self, data, from_user, message):
            self.data = data
            self.from_user = from_user
            self.message = message
            self.answers = []

        async def answer(self, text=None, **kw):
            self.answers.append(text)

        async def edit_message_caption(self, caption=None, **kw):
            self.message.caption_edits += 1
            self.last_text = caption
            self.last_markup = kw.get("reply_markup")

        async def edit_message_text(self, text=None, **kw):
            self.message.text_edits += 1
            self.last_text = text
            self.last_markup = kw.get("reply_markup")

    class CapUpdate:
        def __init__(self, chat_member=None, callback_query=None):
            self.chat_member = chat_member
            self.callback_query = callback_query

    class CapTextMsg:
        _seq = 9000
        sender_chat = None

        def __init__(self, message_thread_id=None):
            CapTextMsg._seq += 1
            self.message_id = CapTextMsg._seq
            self.message_thread_id = message_thread_id

    class CapMsgUpdate:
        def __init__(self, chat, user, message_thread_id=None):
            self.effective_chat = chat
            self.effective_user = user
            self.effective_message = CapTextMsg(message_thread_id)

    class CapContext:
        def __init__(self, bot_data, bot):
            self.bot = bot
            self.bot_data = bot_data
            self.chat_data = {}
            self.application = FakeApplication()

    def _join(chat, user):
        return CapUpdate(chat_member=CapCMU(
            chat,
            CapMember(ChatMemberStatus.LEFT, user=user),
            CapMember(ChatMemberStatus.MEMBER, user=user),
        ))

    # --- вход БЕЗ анкеты → мут + просьба пройти анкету ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G.on_chat_member(_join(chat, CapUser(777)), ctx)
        check((chat.id, 777, False) in bot.restricts, "вход без анкеты → мут")
        check(len(bot.sent) == 1 and "анкет" in bot.sent[0][1], "просьба пройти анкету отправлена")
        gkb = bot.markups[0]
        check(gkb is not None
              and gkb.inline_keyboard[0][0].to_dict().get("url") == "https://t.me/GamblingCommunitybot?start=gate",
              "кнопка просьбы ведёт на бота")
        check(gkb.inline_keyboard[0][0].to_dict().get("style") == "primary",
              "кнопка гейта синяя по умолчанию")
        check(gkb.inline_keyboard[0][0].to_dict().get("icon_custom_emoji_id") == C.GATE_BUTTON_EMOJI_ID,
              "кнопка гейта с премиум-иконкой (перо)")
        check(bd["storage"].pop_group_mutes(777) == [chat.id], "мут записан в group_mutes")

        # --- вход С анкетой → без мута, сразу приветствие с 5 кнопками ---
        bd["storage"].save_profile({"user_id": 778, "username": "done"})
        bot2 = CapBot()
        ctx2 = CapContext(bd, bot2)
        await G.on_chat_member(_join(chat, CapUser(778)), ctx2)
        check(not bot2.restricts, "с анкетой → без мута")
        check(len(bot2.sent) == 2 and "Главный чат" in bot2.sent[0][1], "с анкетой → приветствие")
        kb = bot2.markups[0]
        n = len(C.MENU_BUTTON_DEFAULTS)  # 5
        # +1 строка/кнопка — фиксированная реф-кнопка (не из CMS, добавляется всегда)
        check(kb is not None
              and sum(len(r) for r in kb.inline_keyboard) == n + 1
              and len(kb.inline_keyboard) == math.ceil(n / 2) + 1,
              "приветствие с 5 кнопками-ссылками, по 2 в ряд")
        styles = [btn.to_dict().get("style") for r in kb.inline_keyboard for btn in r]
        check(styles == ["primary", "success", "success", "primary", "primary", "primary"],
              "панель ссылок: шахматный порядок синий/зелёный")

    # --- сообщение в группе от юзера без анкеты → мут, просьба один раз ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        upd = CapMsgUpdate(chat, CapUser(555))
        await G.on_group_message(upd, ctx)
        check((chat.id, 555, False) in bot.restricts, "сообщение без анкеты → мут")
        check(len(bot.sent) == 1, "просьба отправлена")
        await G.on_group_message(upd, ctx)
        check(len(bot.sent) == 1, "повторное сообщение → без второй просьбы")
        check(len(bot.restricts) == 2, "повторный мут идемпотентен")

        bd["storage"].save_profile({"user_id": 556})
        await G.on_group_message(CapMsgUpdate(chat, CapUser(556)), ctx)
        check(len(bot.restricts) == 2 and len(bot.sent) == 1, "с анкетой → не трогаем")

        await G.on_group_message(CapMsgUpdate(chat, CapUser(42)), ctx)
        check(len(bot.restricts) == 2, "админ бота (ADMIN_IDS) → не мутится")

        bot.member_status_map[601] = ChatMemberStatus.ADMINISTRATOR
        await G.on_group_message(CapMsgUpdate(chat, CapUser(601)), ctx)
        check(len(bot.restricts) == 2, "админ группы → не мутится")

        # CMS: подпись кнопки гейта и медиа просьбы редактируются из /admin
        bd["storage"].set_button_override("gate", "GO FORM")
        bd["storage"].set_media("gate_prompt", "GIFID", "animation")
        bot3 = CapBot()
        ctx3 = CapContext(bd, bot3)
        await G.on_group_message(CapMsgUpdate(chat, CapUser(999)), ctx3)
        check(any(s[0] == "animation" for s in bot3.sent), "просьба гейта с CMS-медиа (гиф)")
        check(bot3.markups[0].inline_keyboard[0][0].to_dict().get("text") == "GO FORM",
              "подпись кнопки гейта из CMS")
        check("captcha_success" not in dict(C.TEXT_CATALOG), "мёртвый пункт капчи убран из CMS")
        check(C.TEXT_DEFAULTS.get("captcha_success"), "дефолт captcha_success остался (legacy)")

    # --- юзер пришёл в бота (/start) → просьба в группе удаляется ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G.on_group_message(CapMsgUpdate(chat, CapUser(555)), ctx)
        check(len(bot.sent) == 1, "просьба отправлена (для подчистки)")
        await G.delete_gate_prompts(ctx, 555)
        check(len(bot.deleted_msgs) == 1 and bot.deleted_msgs[0][0] == chat.id,
              "после /start просьба удалена в группе")
        await G.delete_gate_prompts(ctx, 555)
        check(len(bot.deleted_msgs) == 1, "повторный /start → повторно не удаляем")
        check(bd["storage"].pop_group_mutes(555) == [chat.id],
              "мут при этом сохраняется до конца анкеты")

    # --- гейт-промпт уходит в ТУ ЖЕ тему форума, где юзер написал, ответом
    # под его сообщением (24.07.2026 — раньше всегда уходил в топик по
    # умолчанию, независимо от того, в какой теме человек писал) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        upd = CapMsgUpdate(chat, CapUser(700), message_thread_id=35226)
        await G.on_group_message(upd, ctx)
        check(bot.thread_ids[0] == 35226, "gate-topic: промпт уходит в топик, где юзер написал")
        check(bot.reply_to_ids[0] == upd.effective_message.message_id,
              "gate-topic: промпт отправлен ответом на сообщение юзера")

    # --- гейт-промпт истекает через TTL, если юзер не заметил ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G.on_group_message(CapMsgUpdate(chat, CapUser(701)), ctx)
        prompt_mid = bd["storage"].get_gate_prompt(chat.id, 701)
        check(prompt_mid is not None, "gate-ttl: промпт записан в БД")

        await G._expire_gate_prompt(ctx, chat.id, 701, prompt_mid, delay=0)
        check((chat.id, prompt_mid) in bot.deleted_msgs, "gate-ttl: промпт удалён по истечении TTL")
        check(bd["storage"].get_gate_prompt(chat.id, 701) is None,
              "gate-ttl: отметка в БД снята после удаления")

        # юзер успел сделать /start ДО срабатывания таймера -> TTL не должен
        # трогать уже другой (или отсутствующий) промпт
        bot2 = CapBot()
        ctx2 = CapContext(bd, bot2)
        await G.on_group_message(CapMsgUpdate(chat, CapUser(702)), ctx2)
        second_mid = bd["storage"].get_gate_prompt(chat.id, 702)
        await G.delete_gate_prompts(ctx2, 702)  # аналог /start — уже удаляет сообщение сам
        check(bd["storage"].get_gate_prompt(chat.id, 702) is None, "gate-ttl: /start снял промпт раньше TTL")
        await G._expire_gate_prompt(ctx2, chat.id, 702, second_mid, delay=0)
        check(bot2.deleted_msgs.count((chat.id, second_mid)) == 1,
              "gate-ttl: сработавший позже TTL не удаляет уже снятый промпт повторно")

    # --- анкета пройдена → размут + приветствие, запись мута очищена ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G.on_group_message(CapMsgUpdate(chat, CapUser(555)), ctx)
        bd["storage"].save_profile({"user_id": 555})
        await G.unmute_after_profile(ctx, CapUser(555))
        check((chat.id, 555, True) in bot.restricts, "после анкеты → размут")
        check(len(bot.deleted_msgs) == 1, "подстраховка: просьба удалена при размуте")
        check(len(bot.sent) == 3 and "Главный чат" in bot.sent[1][1], "после размута → приветствие")
        check(bd["storage"].pop_group_mutes(555) == [], "запись мута очищена")

    # --- тумблеры режимов (/admin → Режимы) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        bd["storage"].set_flag("gate_enabled", False)
        await G.on_group_message(CapMsgUpdate(chat, CapUser(555)), ctx)
        check(not bot.restricts and not bot.sent, "гейт выкл → без анкеты не мутится")
        await G.on_chat_member(_join(chat, CapUser(777)), ctx)
        check(not bot.restricts and len(bot.sent) == 2, "гейт выкл → вход: приветствие без мута")
        bd["storage"].set_flag("greeting_enabled", False)
        await G.on_chat_member(_join(chat, CapUser(778)), ctx)
        check(len(bot.sent) == 2, "приветствие выкл → тишина при входе")
        bd["storage"].set_flag("greeting_enabled", True)
        bd["storage"].set_flag("gate_enabled", True)
        await G.on_group_message(CapMsgUpdate(chat, CapUser(555)), ctx)
        check((chat.id, 555, False) in bot.restricts, "гейт снова вкл → мут вернулся")

        # массовый размут при выключении гейта
        check(len(bd["storage"].all_group_mutes()) == 1, "запись мута есть")
        done = await G.gate_unmute_all(ctx)
        check(done == 1 and (chat.id, 555, True) in bot.restricts, "выключение → все размучены")
        check(bd["storage"].all_group_mutes() == [], "таблица мутов очищена")
        check(len(bot.deleted_msgs) == 1, "просьбы подчищены при массовом размуте")

    # --- забаненный админом: гейт мутит, НО не пишет в group_mutes (иначе
    # заполнение анкеты потом случайно снимет бан через unmute_after_profile) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].ban_user(779)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G.on_chat_member(_join(chat, CapUser(779)), ctx)
        check((chat.id, 779, False) in bot.restricts, "забаненный без анкеты → всё равно мутится")
        check(bd["storage"].user_mute_chats(779) == [],
              "забаненный НЕ попадает в group_mutes (анкета не должна снять бан)")
        check(not bot.sent, "забаненному не шлём бесполезную просьбу пройти анкету")

        # даже если group_mutes пуста, unmute_after_profile не должен его размутить
        # (defense in depth: banned-check живёт в flow._finish, тут просто нет записи)
        await G.unmute_after_profile(ctx, CapUser(779))
        check(not any(r[1] == 779 and r[2] is True for r in bot.restricts),
              "unmute_after_profile не размучивает забаненного (нет записи в group_mutes)")
        check(bd["storage"].is_banned(779), "бан остался в силе после всех попыток")

    # --- приветствие в группе: один активный слот на чат (Clean Chat) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].save_profile({"user_id": 850})
        bd["storage"].save_profile({"user_id": 851})
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G._send_greeting(ctx, chat.id, CapUser(850))
        # приветствие (панель) + отдельное сообщение с reply-клавиатурой
        check(len(bot.sent) == 2, "greeting-singleton: приветствие + reply-клавиатура отправлены")
        first_greet_mid = bd["storage"].get_singleton_message(chat.id, "greeting")
        first_kb_mid = bd["storage"].get_singleton_message(chat.id, "invite_keyboard")
        check(first_greet_mid is not None and first_kb_mid is not None,
              "greeting-singleton: оба слота записаны в БД")
        check(not bot.deleted_msgs, "greeting-singleton: первое приветствие ничего не удаляет")

        await G._send_greeting(ctx, chat.id, CapUser(851))
        check(len(bot.sent) == 4, "greeting-singleton: второй раунд тоже из двух сообщений")
        check((chat.id, first_greet_mid) in bot.deleted_msgs,
              "greeting-singleton: предыдущее приветствие удалено")
        check((chat.id, first_kb_mid) in bot.deleted_msgs,
              "greeting-singleton: предыдущая reply-клавиатура тоже переустановлена")
        second_greet_mid = bd["storage"].get_singleton_message(chat.id, "greeting")
        check(second_greet_mid != first_greet_mid, "greeting-singleton: слот обновлён на новое сообщение")

    # --- приветствие по языку анкеты (24.07.2026): RU -> основной топик,
    # EN -> COMMUNITY_EN_TOPIC_ID, раздельные singleton-слоты (не мешают друг другу) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["settings"].community_en_topic_id = 35226
        bd["storage"].save_profile({"user_id": 900, "lang": "ru"})
        bd["storage"].save_profile({"user_id": 901, "lang": "en"})
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()

        await G._send_greeting(ctx, chat.id, CapUser(900))
        check("Главный чат" in bot.sent[0][1] and "Main Chat" not in bot.sent[0][1],
              "lang-greeting: RU-профиль -> русский текст без англ. блока")
        check(bot.thread_ids[0] is None, "lang-greeting: RU уходит в топик по умолчанию (без message_thread_id)")
        check(bot.markups[1].keyboard[0][0].text == C.GROUP_KB_INVITE_TEXT,
              "lang-greeting: RU reply-кнопка на русском")
        ru_greet_mid = bd["storage"].get_singleton_message(chat.id, "greeting")

        await G._send_greeting(ctx, chat.id, CapUser(901))
        check("Main Chat ENG" in bot.sent[2][1] and "Главный чат" not in bot.sent[2][1],
              "lang-greeting: EN-профиль -> английский текст без рус. блока")
        check(bot.thread_ids[2] == 35226, "lang-greeting: EN уходит в COMMUNITY_EN_TOPIC_ID")
        check(bot.markups[3].keyboard[0][0].text == C.GROUP_KB_INVITE_TEXT_EN,
              "lang-greeting: EN reply-кнопка на английском")
        check((chat.id, ru_greet_mid) not in bot.deleted_msgs,
              "lang-greeting: EN-приветствие НЕ удаляет RU-приветствие (разные топики — разные слоты)")
        check(bd["storage"].get_singleton_message(chat.id, "greeting") == ru_greet_mid,
              "lang-greeting: RU-слот остаётся нетронутым")
        check(bd["storage"].get_singleton_message(chat.id, "greeting_35226") is not None,
              "lang-greeting: у EN — свой отдельный слот")

    # --- пул видео (24.07.2026): ротация по кругу вместо статичного CMS-медиа ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].greeting_video_add("vid1", "video")
        bd["storage"].greeting_video_add("vid2", "video")
        bd["storage"].save_profile({"user_id": 960, "lang": "ru"})
        bd["storage"].save_profile({"user_id": 961, "lang": "ru"})
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()

        await G._send_greeting(ctx, chat.id, CapUser(960))
        check(bot.sent[0][0] == "video" and bot.media_ids[0] == "vid1",
              "video-pool: первое приветствие -> первое видео из пула")

        await G._send_greeting(ctx, chat.id, CapUser(961))
        check(bot.sent[2][0] == "video" and bot.media_ids[2] == "vid2",
              "video-pool: второе приветствие -> следующее видео по кругу")

    # --- пул пуст -> фолбэк на прежнее CMS-медиа поведение (текст, без видео) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].save_profile({"user_id": 962, "lang": "ru"})
        bot = CapBot()
        ctx = CapContext(bd, bot)
        chat = CapChat()
        await G._send_greeting(ctx, chat.id, CapUser(962))
        check(bot.sent[0][0] == "text", "video-pool: пустой пул -> обычное текстовое сообщение")

    # --- бот-новичок игнорируется ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        await G.on_chat_member(_join(CapChat(), CapUser(888, is_bot=True)), ctx)
        check(not bot.restricts and not bot.sent, "бот-новичок игнорируется")

    # --- клик по старой капче (до отключения): pending нет → удаляем ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        msg = CapMsg(CapChat().id)
        q = CapQuery("cap:777:50", CapUser(777), msg)
        await G.on_answer(CapUpdate(callback_query=q), ctx)
        check(msg.deleted, "клик по старой капче без pending → сообщение удалено")

    # --- allowlist: чужая группа игнорируется (вход и сообщение) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["settings"].captcha_group_ids = (-100999,)
        bot = CapBot()
        ctx = CapContext(bd, bot)
        await G.on_chat_member(_join(CapChat(cid=-100111), CapUser(777)), ctx)
        await G.on_group_message(CapMsgUpdate(CapChat(cid=-100111), CapUser(777)), ctx)
        check(not bot.sent and not bot.restricts, "группа вне allowlist → игнор")

    # --- media: приветствие прошедшему анкету с CMS-видео ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["storage"].set_media("captcha_welcome", "VIDID", "video")
        bd["storage"].save_profile({"user_id": 777})
        bot = CapBot()
        ctx = CapContext(bd, bot)
        await G.on_chat_member(_join(CapChat(), CapUser(777)), ctx)
        check(any(s[0] == "video" for s in bot.sent), "приветствие с CMS-видео отправлено как видео")
        check(bot.markups and bot.markups[0] is not None, "у видео-приветствия есть кнопки")


async def _run_gossip_sim():
    print("== gossip simulation ==")
    import handlers.gossip as G
    from gossip_formatter import FormattedGossip
    from telegram.ext import ConversationHandler

    async def _fake_format(api_key, model, raw_text):
        return FormattedGossip(
            headline_ru="Заголовок", headline_en="Headline",
            summary_ru="Суть.", summary_en="Point.", tags=["news"], flagged=False,
        )

    orig_format = G.format_with_gpt
    G.format_with_gpt = _fake_format
    try:
        with tempfile.TemporaryDirectory() as d:
            bd = _bot_data(d)
            bd["settings"].openai_api_key = "testkey"
            bd["settings"].news_chat_id = -999
            bd["settings"].gossip_topic_id = 77144
            storage = bd["storage"]
            user = FakeUser(100, "noprofile")

            # без анкеты -> отказ, конверсация не начинается
            ctx = FakeContext(bd)
            st = await G.gossip_start(FakeUpdate(message=FakeMessage("/gossip"), user=user), ctx)
            check(st == ConversationHandler.END, "gossip: без анкеты -> END")

            storage.save_profile({
                "user_id": 100, "username": "noprofile", "vertical": "Gambling",
                "grade": "C-Level", "profession": "CEO", "request": "r",
                "name": "N", "company": "C", "linkedin": "-",
            })

            # с анкетой -> ждём текст
            ctx = FakeContext(bd)
            st = await G.gossip_start(FakeUpdate(message=FakeMessage("/gossip"), user=user), ctx)
            check(st == G.WAIT_TEXT, "gossip: с анкетой -> WAIT_TEXT")

            # медиа вместо текста -> просьба прислать текстом
            st = await G.gossip_non_text(
                FakeUpdate(message=FakeMessage(animation=FakeFile("A1")), user=user), ctx)
            check(st == G.WAIT_TEXT, "gossip: не-текст -> остаёмся в WAIT_TEXT")

            # слишком короткий текст
            st = await G.gossip_text(FakeUpdate(message=FakeMessage("коротко"), user=user), ctx)
            check(st == G.WAIT_TEXT, "gossip: короткий текст -> остаёмся в WAIT_TEXT")

            # нормальный текст -> черновик создан, админ уведомлён
            long_text = "Слышал, что один известный оператор задерживает выплаты партнёрам уже месяц."
            st = await G.gossip_text(FakeUpdate(message=FakeMessage(long_text), user=user), ctx)
            check(st == ConversationHandler.END, "gossip: после отправки -> END")
            check(storage.gossip_pending_count() == 1, "gossip: черновик создан")
            draft = storage.gossip_get_draft(1)
            check(draft["submitter_id"] == 100 and "Заголовок" in draft["text"],
                  "gossip: черновик содержит GPT-рендер")
            admin_sent = [t for cid, t in ctx.bot.sent if cid == 42 and "Заголовок" in t]
            check(len(admin_sent) == 1, "gossip: админ получил черновик с кнопками")

            # повторная попытка в тот же день -> кулдаун
            ctx2 = FakeContext(bd)
            st = await G.gossip_start(FakeUpdate(message=FakeMessage("/gossip"), user=user), ctx2)
            check(st == ConversationHandler.END, "gossip: кулдаун блокирует повторную отправку")

            # тумблер выключен -> отказ для другого юзера
            storage.set_flag("gossip_enabled", False)
            user2 = FakeUser(101, "second")
            storage.save_profile({
                "user_id": 101, "username": "second", "vertical": "Gambling",
                "grade": "C-Level", "profession": "CEO", "request": "r",
                "name": "N", "company": "C", "linkedin": "-",
            })
            ctx3 = FakeContext(bd)
            st = await G.gossip_start(FakeUpdate(message=FakeMessage("/gossip"), user=user2), ctx3)
            check(st == ConversationHandler.END, "gossip: тумблер выкл -> END")
            storage.set_flag("gossip_enabled", True)

            # групповой чат -> отказ
            ctx4 = FakeContext(bd)
            grp_update = FakeUpdate(message=FakeMessage("/gossip"), user=user2)
            grp_update.effective_chat.type = "supergroup"
            st = await G.gossip_start(grp_update, ctx4)
            check(st == ConversationHandler.END, "gossip: из группы -> END")

            # не-админ жмёт кнопку решения -> отказ
            q_intruder = FakeQuery("gossip:pub:1")
            await G.on_gossip_decision(FakeUpdate(query=q_intruder, user=FakeUser(999)), ctx)
            check(q_intruder.answered and "админ" in (q_intruder.last_answer_text or "").lower(),
                  "gossip: не-админ получает отказ")
            check(storage.gossip_get_draft(1)["status"] == "pending", "gossip: статус не изменился")

            # админ публикует
            q_pub = FakeQuery("gossip:pub:1")
            await G.on_gossip_decision(FakeUpdate(query=q_pub, user=FakeUser(42)), ctx)
            check(storage.gossip_get_draft(1)["status"] == "published", "gossip: опубликовано")
            published = [t for cid, t in ctx.bot.sent if cid == -999]
            check(len(published) == 1, "gossip: пост ушёл в NEWS_CHAT_ID")
            check(ctx.bot.last_send_kwargs.get("message_thread_id") == 77144,
                  "gossip: пост ушёл в тему gossip_topic_id, не в тему новостей")

            # повторный клик -> уже обработано
            q_again = FakeQuery("gossip:pub:1")
            await G.on_gossip_decision(FakeUpdate(query=q_again, user=FakeUser(42)), ctx)
            check("обработано" in (q_again.last_answer_text or "").lower(),
                  "gossip: повторный клик -> уже обработано")

            # второй черновик -> отклонение
            ctx5 = FakeContext(bd)
            storage.set_flag("gossip_enabled", True)
            long_text2 = "Ещё один инсайд про рынок беттинга, вполне безобидный, просто слух."
            st = await G.gossip_start(FakeUpdate(message=FakeMessage("/gossip"), user=user2), ctx5)
            # кулдауна у user2 ещё не было (он не отправлял), поэтому попадаем в WAIT_TEXT
            check(st == G.WAIT_TEXT, "gossip: второй юзер -> WAIT_TEXT")
            st = await G.gossip_text(FakeUpdate(message=FakeMessage(long_text2), user=user2), ctx5)
            check(st == ConversationHandler.END, "gossip: второй черновик отправлен")
            check(storage.gossip_pending_count() == 1, "gossip: второй черновик pending")
            q_rej = FakeQuery("gossip:rej:2")
            await G.on_gossip_decision(FakeUpdate(query=q_rej, user=FakeUser(42)), ctx5)
            check(storage.gossip_get_draft(2)["status"] == "rejected", "gossip: отклонено")

            storage.close()
    finally:
        G.format_with_gpt = orig_format


async def _run_news_sim():
    print("== news simulation (кросс-админ синхронизация решений) ==")
    import handlers.news as NEWS

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["settings"].admin_ids = (42, 43)
        bd["settings"].news_chat_id = -999
        storage = bd["storage"]
        did = storage.news_save_draft("guid1", "src", "http://x", "T", "Текст черновика", None)
        storage.news_add_admin_msg(did, 42, 5001)
        storage.news_add_admin_msg(did, 43, 5002)

        ctx = FakeContext(bd)
        # не-админ жмёт кнопку -> отказ, статус не меняется
        q_intruder = FakeQuery(f"news:pub:{did}")
        await NEWS.on_news_decision(FakeUpdate(query=q_intruder, user=FakeUser(999)), ctx)
        check("админ" in (q_intruder.last_answer_text or "").lower(), "news: не-админ получает отказ")
        check(storage.news_get_draft(did)["status"] == "pending", "news: статус не изменился")

        # один админ отклоняет -> копия удаляется у ОБОИХ, не только у нажавшего
        q_rej = FakeQuery(f"news:rej:{did}")
        await NEWS.on_news_decision(FakeUpdate(query=q_rej, user=FakeUser(42)), ctx)
        check(storage.news_get_draft(did)["status"] == "rejected", "news: отклонено")
        check((42, 5001) in ctx.bot.deleted_msgs and (43, 5002) in ctx.bot.deleted_msgs,
              "news: копия черновика удалена у ОБОИХ админов")
        check(storage.news_list_admin_msgs(did) == [], "news: записи сообщений очищены после решения")

        # повторный клик (второй админ пришёл позже) -> уже обработано
        q_again = FakeQuery(f"news:rej:{did}")
        await NEWS.on_news_decision(FakeUpdate(query=q_again, user=FakeUser(43)), ctx)
        check("обработано" in (q_again.last_answer_text or "").lower(),
              "news: повторный клик другим админом -> уже обработано")

        # публикация другого черновика -> тоже чистит у всех + постит в NEWS_CHAT_ID
        did2 = storage.news_save_draft("guid2", "src", "http://y", "T2", "Текст 2", None)
        storage.news_add_admin_msg(did2, 42, 6001)
        storage.news_add_admin_msg(did2, 43, 6002)
        q_pub = FakeQuery(f"news:pub:{did2}")
        await NEWS.on_news_decision(FakeUpdate(query=q_pub, user=FakeUser(43)), ctx)
        check(storage.news_get_draft(did2)["status"] == "published", "news: опубликовано")
        published = [t for cid, t in ctx.bot.sent if cid == -999]
        check(len(published) == 1, "news: пост ушёл в NEWS_CHAT_ID")
        check((42, 6001) in ctx.bot.deleted_msgs and (43, 6002) in ctx.bot.deleted_msgs,
              "news: копия удалена у ОБОИХ админов после публикации")
        storage.close()


async def _run_news_poster_sim():
    print("== news_poster (дневной лимит показов админам) ==")
    import news_poster as NP

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        bd["settings"].admin_ids = (42, 43)
        storage = bd["storage"]
        bot = FakeBot()

        ids = [
            storage.news_save_draft(f"g{i}", "src", f"http://x{i}", f"T{i}", f"Текст {i}", None)
            for i in range(8)
        ]
        sent = await NP._notify_up_to_quota(bot, bd["settings"], storage)
        check(sent == NP.DAILY_ADMIN_LIMIT, f"news_poster: за раз не больше {NP.DAILY_ADMIN_LIMIT}")
        check(storage.news_notified_today_count() == NP.DAILY_ADMIN_LIMIT, "news_poster: счётчик за день")
        check(len(storage.news_pending_unnotified(100)) == len(ids) - NP.DAILY_ADMIN_LIMIT,
              "news_poster: остаток ждёт своей очереди")
        notified_ids = {i for i in ids if storage.news_get_draft(i)["notified_at"]}
        check(notified_ids == set(ids[:NP.DAILY_ADMIN_LIMIT]),
              "news_poster: показаны САМЫЕ СТАРЫЕ первыми (честная очередь)")

        # квота на сегодня исчерпана -> следующий проход ничего не шлёт
        sent2 = await NP._notify_up_to_quota(bot, bd["settings"], storage)
        check(sent2 == 0, "news_poster: квота на сегодня исчерпана")

        admins_notified = [cid for cid, _text in bot.sent]
        check(admins_notified.count(42) == NP.DAILY_ADMIN_LIMIT
              and admins_notified.count(43) == NP.DAILY_ADMIN_LIMIT,
              "news_poster: каждый показанный черновик ушёл ОБОИМ админам")
        storage.close()


async def _run_referral_group_sim():
    print("== referral: постоянная reply-клавиатура в группе ==")
    import ui
    import handlers.referral as REF

    kb = ui.group_reply_kb()
    check(kb.resize_keyboard is True and kb.is_persistent is True and kb.one_time_keyboard is False,
          "referral: reply-клавиатура компактная и постоянная")
    check(kb.keyboard[0][0].text == C.GROUP_KB_INVITE_TEXT,
          "referral: текст кнопки клавиатуры совпадает с фильтром хендлера")

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        ctx = FakeContext(bd)
        chat = FakeChat(-777, "supergroup")

        msg = FakeMessage(C.GROUP_KB_INVITE_TEXT, chat_id=chat.id)
        upd = FakeUpdate(message=msg, user=FakeUser(600, "first"))
        upd.effective_chat = chat
        await REF.on_group_invite_button(upd, ctx)
        check(msg.deleted, "referral: нажатие reply-кнопки удаляет сообщение (Clean Chat)")
        dm_sent = [t for cid, t in ctx.bot.sent if cid == 600 and "персональная ссылка" in t]
        check(len(dm_sent) == 1, "referral: ссылка ушла в личку нажавшему")
        group_sent = [t for cid, t in ctx.bot.sent if cid == -777]
        check(len(group_sent) == 1 and "личные сообщения" in group_sent[0],
              "referral: подтверждение отправлено в группу")

        # второе нажатие (другим юзером) -> предыдущее подтверждение в группе заменяется
        msg2 = FakeMessage(C.GROUP_KB_INVITE_TEXT, chat_id=chat.id)
        upd2 = FakeUpdate(message=msg2, user=FakeUser(601, "second"))
        upd2.effective_chat = chat
        await REF.on_group_invite_button(upd2, ctx)
        check(msg2.deleted, "referral: второе нажатие тоже удаляется")
        check(len([t for cid, t in ctx.bot.sent if cid == -777]) == 2,
              "referral: второе подтверждение отправлено")
        check(any(cid == -777 for cid, _mid in ctx.bot.deleted_msgs),
              "referral: предыдущее подтверждение в группе удалено (singleton)")


async def _run_admin_panel_sim():
    print("== admin panel (dashboard/анкеты/рассылка/журнал) simulation ==")
    import handlers.admin_cms as A
    import handlers.admin_broadcast as BC
    import handlers.admin_log as LOGV
    import handlers.admin_profiles as PF
    import handlers.flow as F
    from telegram.ext import ConversationHandler

    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
        storage = bd["storage"]
        ctx = FakeContext(bd)

        # --- dashboard ---
        st = await A.admin_open(FakeUpdate(message=FakeMessage("/admin"), user=FakeUser(42)), ctx)
        check(st == A.BROWSE, "panel: admin_open -> BROWSE")
        check("Админ-панель" in ctx.bot.last_text, "panel: dashboard показан по /admin")
        check("Анкет всего: <b>0</b>" in ctx.bot.last_text, "panel: dashboard считает 0 анкет")
        await A.nav_menu(FakeUpdate(query=FakeQuery("acms_menu")), ctx)
        check("Управление контентом" in ctx.bot.last_text, "panel: раздел Контент открывается")
        await A.nav_home(FakeUpdate(query=FakeQuery("acms_home")), ctx)
        check("Админ-панель" in ctx.bot.last_text, "panel: возврат на dashboard")

        # тумблер режима теперь логируется в журнал
        st = await A.nav_modes(FakeUpdate(query=FakeQuery("acms_modes")), ctx)
        texts = kb_texts(ctx.bot.last_markup)
        check(all(t.startswith("🟢") for t in texts if "·" in t),
              "modes: все режимы по умолчанию включены -> зелёные кружки")
        await A.toggle_mode(FakeUpdate(query=FakeQuery("acms_tgl:greet"), user=FakeUser(42)), ctx)
        check(storage.audit_log_count() == 1, "panel: toggle_mode пишет действие в журнал")
        check(storage.audit_log_page(0, 10)[0]["action"] == "greeting_toggle",
              "panel: залогировано именно переключение приветствия")
        texts = kb_texts(ctx.bot.last_markup)
        greet_line = next(t for t in texts if "Приветствие" in t)
        check(greet_line.startswith("🔴") and "выкл" in greet_line,
              "modes: выключенное приветствие -> красный кружок")
        gate_line = next(t for t in texts if "Гейт" in t)
        check(gate_line.startswith("🟢") and "вкл" in gate_line,
              "modes: гейт остался включён -> зелёный кружок (другие тумблеры не задеты)")

        # анкеты для дальнейших тестов
        storage.save_profile({
            "user_id": 300, "username": "vasya", "vertical": "Gambling",
            "grade": "C-Level", "profession": "CEO", "request": "networking",
            "name": "Вася", "company": "Acme", "linkedin": "-",
        })
        storage.save_profile({
            "user_id": 301, "username": "petya", "vertical": "Betting",
            "grade": "Senior", "profession": "Manager", "request": "r",
            "name": "Петя", "company": "OtherCo", "linkedin": "-",
        })

        # --- раздел «Анкеты» ---
        st = await PF.nav_profiles(FakeUpdate(query=FakeQuery("acms_pf")), ctx)
        check(st == A.BROWSE and "Анкеты" in ctx.bot.last_text, "panel: список анкет открыт")
        check(f'?start=p_1"' in ctx.bot.last_text and "300" in ctx.bot.last_text,
              "panel: список анкет — кликабельный ID (deep-link p_<id>)")
        check(not any(b.callback_data and "acms_pf_open" in b.callback_data
                      for row in ctx.bot.last_markup.inline_keyboard for b in row),
              "panel: список анкет больше не использует кнопки-строки")
        st = await PF.pf_open(FakeUpdate(query=FakeQuery("acms_pf_open:1")), ctx)
        check("Анкета #1" in ctx.bot.last_text and "Вася" in ctx.bot.last_text,
              "panel: карточка анкеты открыта")
        await PF.pf_toggle_contact(
            FakeUpdate(query=FakeQuery("acms_pf_contact:1"), user=FakeUser(42)), ctx)
        check(storage.get_profile(1)["contacted"] == 1, "panel: отметка «связались» сохранена")
        check(storage.audit_log_count() == 2, "panel: отметка залогирована в журнал")

        st = await PF.pf_search_start(FakeUpdate(query=FakeQuery("acms_pf_search")), ctx)
        check(st == PF.WAIT_SEARCH, "panel: поиск анкет -> WAIT_SEARCH")
        st = await PF.pf_search_text(FakeUpdate(message=FakeMessage("Петя")), ctx)
        check(st == A.BROWSE and "Петя" in ctx.bot.last_text, "panel: поиск по имени нашёл анкету")

        # мут + принудительный размут
        storage.add_group_mute(-777, 300)
        check(storage.user_mute_chats(300) == [-777], "panel: мут записан для теста unmute")
        await PF.pf_open(FakeUpdate(query=FakeQuery("acms_pf_open:1")), ctx)
        check(any("Размутить" in t for t in kb_texts(ctx.bot.last_markup)),
              "panel: кнопка размута видна при активном муте")
        await PF.pf_unmute(FakeUpdate(query=FakeQuery("acms_pf_unmute:1"), user=FakeUser(42)), ctx)
        check(storage.user_mute_chats(300) == [], "panel: принудительный размут снял запись мута")
        check(any(cid == -777 and uid == 300 for cid, uid, _perm in getattr(ctx.bot, "restricts", [])),
              "panel: restrict_chat_member вызван для размута")
        # unmute_after_profile выше заодно шлёт приветствие -> планирует часовое
        # автоудаление через spawn_background (bot_data["_bg_tasks"], НЕ
        # application.create_task — см. фикс от 20.07.2026); гасим и убираем,
        # иначе более поздний asyncio.gather рассылки либо ждал бы реальный
        # час, либо упал бы на CancelledError отменённой задачи
        for _t in bd.get("_bg_tasks", set()):
            if not _t.done():
                _t.cancel()
        bd.get("_bg_tasks", set()).clear()

        # --- раздел «Рассылка» ---
        st = await BC.nav_broadcast(FakeUpdate(query=FakeQuery("acms_bc")), ctx)
        check(st == A.BROWSE and "Выберите аудиторию" in ctx.bot.last_text,
              "panel: рассылка — меню аудитории")
        await BC.bc_audience_vertical_menu(FakeUpdate(query=FakeQuery("acms_bc_aud:vertical")), ctx)
        check("вертикаль" in ctx.bot.last_text.lower(), "panel: выбор вертикали показан")
        await BC.bc_pick_vertical(FakeUpdate(query=FakeQuery("acms_bc_vert:0")), ctx)  # Gambling
        check(ctx.user_data["bc"]["audience"]["value"] == "Gambling", "panel: аудитория = вертикаль")
        check("Сообщений пока нет" in ctx.bot.last_text, "panel: конструктор без сообщений")

        st = await BC.bc_add_item_start(FakeUpdate(query=FakeQuery("acms_bc_additem")), ctx)
        check(st == BC.WAIT_TEXT, "panel: добавление сообщения -> WAIT_TEXT")
        st = await BC.bc_item_text(FakeUpdate(message=FakeMessage("Привет, у нас новости!")), ctx)
        check(st == A.BROWSE and "кнопку-ссылку" in ctx.bot.last_text,
              "panel: текст сохранён, спрашиваем про кнопку")
        st = await BC.bc_btn_choice(FakeUpdate(query=FakeQuery("acms_bc_btn:yes")), ctx)
        check(st == BC.WAIT_BTN_LABEL, "panel: да -> ждём текст кнопки")
        st = await BC.bc_btn_label(FakeUpdate(message=FakeMessage("Перейти")), ctx)
        check(st == BC.WAIT_BTN_URL, "panel: label сохранён -> ждём url")
        st = await BC.bc_btn_url(FakeUpdate(message=FakeMessage("не-ссылка")), ctx)
        check(st == BC.WAIT_BTN_URL, "panel: невалидный url -> остаёмся ждать")
        st = await BC.bc_btn_url(FakeUpdate(message=FakeMessage("https://example.com")), ctx)
        check(st == A.BROWSE and len(ctx.user_data["bc"]["items"]) == 1,
              "panel: сообщение с кнопкой добавлено в конструктор")

        q_count = FakeQuery("acms_bc_count")
        await BC.bc_audience_count(FakeUpdate(query=q_count, user=FakeUser(42)), ctx)
        check(q_count.last_answer_text and "1" in q_count.last_answer_text,
              "panel: подсчёт получателей (1 анкета Gambling)")

        # второе сообщение, без кнопки, потом удаляем последнее
        await BC.bc_add_item_start(FakeUpdate(query=FakeQuery("acms_bc_additem")), ctx)
        await BC.bc_item_text(FakeUpdate(message=FakeMessage("Второе сообщение")), ctx)
        await BC.bc_btn_choice(FakeUpdate(query=FakeQuery("acms_bc_btn:no")), ctx)
        check(len(ctx.user_data["bc"]["items"]) == 2, "panel: второе сообщение добавлено")
        await BC.bc_remove_last(FakeUpdate(query=FakeQuery("acms_bc_removelast")), ctx)
        check(len(ctx.user_data["bc"]["items"]) == 1, "panel: удаление последнего сообщения")

        q_send = FakeQuery("acms_bc_send", message=FakeMessage("stub"))
        await BC.bc_send(FakeUpdate(query=q_send, user=FakeUser(42)), ctx)
        check("bc" not in ctx.user_data, "panel: конструктор очищен после отправки")
        # run_broadcast теперь fire-and-forget через spawn_background (голый
        # asyncio.create_task, НЕ application.create_task — см. правку от
        # 20.07.2026 про зависающие рестарты), поэтому ждём через bot_data
        await asyncio.gather(*bd.get("_bg_tasks", []))
        report = [t for cid, t in ctx.bot.sent if cid == 42 and "Рассылка завершена" in t]
        check(len(report) == 1, "panel: отчёт о рассылке пришёл админу")
        check("успешно: 1" in report[0].lower(), "panel: отчёт содержит успешную доставку")
        check(storage.audit_log_count() == 4, "panel: рассылка залогирована в журнал "
              "(greeting_toggle+contacted+force_unmute+broadcast)")

        # отмена конструктора без отправки
        await BC.bc_audience_all(FakeUpdate(query=FakeQuery("acms_bc_aud:all")), ctx)
        check("bc" in ctx.user_data, "panel: новый конструктор создан")
        await BC.bc_cancel(FakeUpdate(query=FakeQuery("acms_bc_cancel"), user=FakeUser(42)), ctx)
        check("bc" not in ctx.user_data, "panel: отмена очищает конструктор")

        # --- раздел «Рассылка»: без стран в системе -> alert, конструктор не открывается ---
        q_empty = FakeQuery("acms_bc_aud:country")
        await BC.bc_audience_country_menu(FakeUpdate(query=q_empty), ctx)
        check(q_empty.answered and "страну" in (q_empty.last_answer_text or "").lower(),
              "panel: рассылка по странам без данных -> предупреждение")

        # --- раздел «Журнал» ---
        st = await LOGV.nav_log(FakeUpdate(query=FakeQuery("acms_log")), ctx)
        check(st == A.BROWSE and "Журнал действий" in ctx.bot.last_text, "panel: журнал открыт")
        check("рассылка" in ctx.bot.last_text.lower(), "panel: журнал видит запись о рассылке")

        # --- раздел «Пользователи» ---
        import handlers.admin_users as US
        from telegram.constants import ChatMemberStatus

        st = await US.nav_users(FakeUpdate(query=FakeQuery("acms_users")), ctx)
        check(st == US.WAIT_LOOKUP, "users: раздел -> WAIT_LOOKUP")
        check("Пользователи" in ctx.bot.last_text, "users: экран поиска показан")
        check(f'?start=u_300"' in ctx.bot.last_text and "vasya" in ctx.bot.last_text,
              "users: список показывает известных пользователей с кликабельным ID")

        # лукап по ID без анкеты и без статуса в группе (дефолт MEMBER)
        st = await US.lookup_text(FakeUpdate(message=FakeMessage("555555")), ctx)
        check(st == A.BROWSE and "555555" in ctx.bot.last_text, "users: карточка по ID открыта")
        check("Анкеты нет" in ctx.bot.last_text, "users: у 555555 анкеты нет")
        check(any("Забанить" in t for t in kb_texts(ctx.bot.last_markup)),
              "users: кнопка бана видна для обычного участника")

        # мут на 10 минут
        await US.usr_mute(FakeUpdate(query=FakeQuery("acms_usr_mute:555555:0"), user=FakeUser(42)), ctx)
        rec = [r for r in ctx.bot.restricts if r[1] == 555555][-1]
        check(rec[0] == bd["settings"].community_chat_id, "users: мут применён к community_chat_id")
        check(rec[2].can_send_messages is False, "users: мут запрещает сообщения")
        check(storage.audit_log_page(0, 1)[0]["action"] == "manual_mute",
              "users: мут залогирован в журнал")

        # бан требует подтверждения
        st = await US.usr_ban_confirm(FakeUpdate(query=FakeQuery("acms_usr_ban_confirm:555555")), ctx)
        check(st == A.BROWSE and "уверены" in ctx.bot.last_text.lower(), "users: запрошено подтверждение бана")
        await US.usr_ban(FakeUpdate(query=FakeQuery("acms_usr_ban:555555"), user=FakeUser(42)), ctx)
        check(storage.audit_log_page(0, 1)[0]["action"] == "manual_ban", "users: бан залогирован")
        check(storage.is_banned(555555), "users: usr_ban пишет в banned_users")
        st = await US.usr_open(FakeUpdate(query=FakeQuery("acms_usr_open:555555")), ctx)
        check("ЗАБАНЕН" in ctx.bot.last_text, "users: карточка явно показывает бан")

        # разбан -> restrict со стандартными правами чата (get_chat дал permissions=None -> фолбэк)
        await US.usr_unban(FakeUpdate(query=FakeQuery("acms_usr_unban:555555"), user=FakeUser(42)), ctx)
        check(storage.audit_log_page(0, 1)[0]["action"] == "manual_unban", "users: разбан залогирован")
        check(not storage.is_banned(555555), "users: usr_unban снимает флаг banned_users")
        last_unban = [r for r in ctx.bot.restricts if r[1] == 555555][-1]
        check(last_unban[2].can_send_messages is True, "users: разбан возвращает право писать")

        # у 300 уже есть анкета -> карточка с кнопкой «Открыть анкету»
        st = await US.lookup_text(FakeUpdate(message=FakeMessage("300")), ctx)
        check("Анкета #1" in ctx.bot.last_text, "users: карточка видит анкету участника")
        check(any("Открыть анкету" in t for t in kb_texts(ctx.bot.last_markup)),
              "users: кнопка перехода к анкете")

        # админ группы -> нет кнопок мута/бана
        ctx.bot.member_status_map[600] = ChatMemberStatus.ADMINISTRATOR
        st = await US.lookup_text(FakeUpdate(message=FakeMessage("600")), ctx)
        check(not any("Забанить" in t or "мин" in t for t in kb_texts(ctx.bot.last_markup)),
              "users: у админа группы нет кнопок мута/бана")

        # поиск по @username через анкету
        st = await US.lookup_text(FakeUpdate(message=FakeMessage("@vasya")), ctx)
        check("300" in ctx.bot.last_text, "users: поиск по @username нашёл через анкету")

        # не нашли -> просим повторить
        st = await US.lookup_text(FakeUpdate(message=FakeMessage("@no_such_user_xyz")), ctx)
        check(st == US.WAIT_LOOKUP and "Не нашёл" in ctx.bot.last_text,
              "users: несуществующий @username -> просим повторить")

        # --- быстрая карточка по форварду (без захода в /admin) ---
        from types import SimpleNamespace

        before = len(ctx.bot.sent)
        prev_mid = ctx.user_data.get("adm_mid")
        fwd_msg = FakeMessage("hello from the group", chat_id=42)
        fwd_msg.forward_origin = SimpleNamespace(sender_user=SimpleNamespace(id=777777))
        await US.quick_lookup_forward(FakeUpdate(message=fwd_msg, user=FakeUser(42)), ctx)
        check(len(ctx.bot.sent) == before + 1, "forward: админ переслал сообщение -> карточка отправлена")
        check("777777" in ctx.bot.sent[-1][1], "forward: карточка про правильного пользователя")
        check(ctx.user_data.get("adm_chat") == 42,
              "forward: экран карточки привязан к личке админа")
        check(any(mid == prev_mid for _cid, mid in ctx.bot.deleted_msgs),
              "forward: старое меню /admin удалено при открытии карточки по форварду")

        # не-админ пересылает -> тишина
        before2 = len(ctx.bot.sent)
        fwd_msg2 = FakeMessage("hi", chat_id=999)
        fwd_msg2.forward_origin = SimpleNamespace(sender_user=SimpleNamespace(id=888888))
        await US.quick_lookup_forward(FakeUpdate(message=fwd_msg2, user=FakeUser(999)), ctx)
        check(len(ctx.bot.sent) == before2, "forward: не-админ не получает карточку")

        # обычное (не пересланное) сообщение от админа -> тишина, не мешает остальным хендлерам
        before3 = len(ctx.bot.sent)
        await US.quick_lookup_forward(FakeUpdate(message=FakeMessage("просто текст", chat_id=42), user=FakeUser(42)), ctx)
        check(len(ctx.bot.sent) == before3, "forward: обычное сообщение (не форвард) -> не реагируем")

        storage.close()

    # --- пагинация списков (Анкеты/Пользователи), 21 анкета -> 2 страницы по 20 ---
    with tempfile.TemporaryDirectory() as d:
        bd3 = _bot_data(d)
        storage3 = bd3["storage"]
        ctx3 = FakeContext(bd3)
        await A.admin_open(FakeUpdate(message=FakeMessage("/admin"), user=FakeUser(42)), ctx3)
        for i in range(21):
            storage3.save_profile({
                "user_id": 1000 + i, "username": f"u{i}", "vertical": "Gambling",
                "grade": "C-Level", "profession": "CEO", "request": "r",
                "name": f"User{i}", "company": "Acme", "linkedin": "-",
            })

        st = await PF.nav_profiles(FakeUpdate(query=FakeQuery("acms_pf")), ctx3)
        check(ctx3.bot.last_text.count("<a href=") == 20, "pagination: анкеты стр.0 — ровно 20 строк")
        check(any("Вперёд" in t for t in kb_texts(ctx3.bot.last_markup))
              and not any("Назад" in t for t in kb_texts(ctx3.bot.last_markup)),
              "pagination: анкеты стр.0 — только «Вперёд →»")
        await PF.pf_page(FakeUpdate(query=FakeQuery("acms_pf_list:1")), ctx3)
        check(ctx3.bot.last_text.count("<a href=") == 1, "pagination: анкеты стр.1 — остаток (1 анкета)")
        check(any("Назад" in t for t in kb_texts(ctx3.bot.last_markup))
              and not any("Вперёд" in t for t in kb_texts(ctx3.bot.last_markup)),
              "pagination: анкеты стр.1 — только «← Назад»")

        st = await US.nav_users(FakeUpdate(query=FakeQuery("acms_users")), ctx3)
        check(ctx3.bot.last_text.count("<a href=") == 20, "pagination: пользователи стр.0 — ровно 20 строк")
        await US.usr_list_page(FakeUpdate(query=FakeQuery("acms_users_p:1")), ctx3)
        check(ctx3.bot.last_text.count("<a href=") == 1, "pagination: пользователи стр.1 — остаток (1)")
        storage3.close()

    # --- deep-link для админа: клик по ID в списке (?start=u_<id> / ?start=p_<id>) ---
    with tempfile.TemporaryDirectory() as d:
        bd4 = _bot_data(d)
        storage4 = bd4["storage"]
        storage4.save_profile({
            "user_id": 400, "username": "deeplinked", "vertical": "Gambling",
            "grade": "C-Level", "profession": "CEO", "request": "r",
            "name": "Deep Link", "company": "Acme", "linkedin": "-",
        })
        ctx4 = FakeContext(bd4)
        # старое меню уже открыто (как будто админ только что смотрел список) —
        # клик по ID должен его удалить, а не оставить висеть рядом с карточкой
        ctx4.user_data["adm_chat"] = 42
        ctx4.user_data["adm_mid"] = 9001
        ctx4.args = ["u_400"]
        st = await F.start(FakeUpdate(message=FakeMessage("/start u_400", chat_id=42), user=FakeUser(42)), ctx4)
        check(st == ConversationHandler.END, "deep-link: /start u_400 (админ) -> END")
        check(any(cid == 42 and "400" in t and "Участник" in t for cid, t in ctx4.bot.sent),
              "deep-link: карточка участника открыта по u_<id>")
        check((42, 9001) in ctx4.bot.deleted_msgs,
              "deep-link: старое меню (список Пользователи) удалено при открытии карточки")

        ctx4b = FakeContext(bd4)
        ctx4b.user_data["adm_chat"] = 42
        ctx4b.user_data["adm_mid"] = 9002
        ctx4b.args = ["p_1"]
        st = await F.start(FakeUpdate(message=FakeMessage("/start p_1", chat_id=42), user=FakeUser(42)), ctx4b)
        check(st == ConversationHandler.END, "deep-link: /start p_1 (админ) -> END")
        check(any(cid == 42 and "Анкета #1" in t and "Deep Link" in t for cid, t in ctx4b.bot.sent),
              "deep-link: карточка анкеты открыта по p_<id>")
        check((42, 9002) in ctx4b.bot.deleted_msgs,
              "deep-link: старое меню (список Анкеты) удалено при открытии карточки")
        storage4.close()

    # --- QR-код профиля GURO ID: /start guro_<id> -> web_app-кнопка, БЕЗ
    #     повторного прохождения анкеты (в отличие от голого /start) ---
    with tempfile.TemporaryDirectory() as d:
        bd6 = _bot_data(d)
        storage6 = bd6["storage"]
        storage6.save_profile({
            "user_id": 500, "username": "scanner", "name": "Scanner", "vertical": "Gambling",
            "grade": "C-Level", "profession": "CEO", "request": "r", "company": "Acme", "linkedin": "-",
        })
        ctx6 = FakeContext(bd6)
        ctx6.args = ["guro_777"]
        st = await F.start(
            FakeUpdate(message=FakeMessage("/start guro_777", chat_id=500), user=FakeUser(500)), ctx6,
        )
        check(st == ConversationHandler.END,
              "QR deep-link: /start guro_777 (уже зарегистрирован) -> END, БЕЗ повторной анкеты")
        sent = [t for cid, t in ctx6.bot.sent if cid == 500]
        check(len(sent) == 1 and "профиль" in sent[0].lower(),
              "QR deep-link: пришло сообщение с предложением открыть профиль")
        markup = ctx6.bot.last_send_kwargs.get("reply_markup")
        btn = markup.inline_keyboard[0][0]
        check(btn.web_app is not None, "QR deep-link: кнопка — именно web_app (не обычная url-ссылка)")
        check(btn.web_app.url == f"{bd6['settings'].guro_id_webapp_url.rstrip('/')}/?target=777",
              f"QR deep-link: web_app URL содержит ?target=777, получено {btn.web_app.url}")

        # НЕзарегистрированный сканирующий -> обычный флоу регистрации (lang_select),
        # QR-цель просто теряется, а не ломает анкету
        ctx7 = FakeContext(bd6)
        ctx7.args = ["guro_777"]
        st = await F.start(
            FakeUpdate(message=FakeMessage("/start guro_777", chat_id=999), user=FakeUser(999)), ctx7,
        )
        check(st != ConversationHandler.END,
              "QR deep-link: НЕзарегистрированный сканирующий -> обычный флоу анкеты продолжается")
        storage6.close()

    # --- раздел «Рассылка»: сегментация по странам (кнопки, флаги, overflow) ---
    with tempfile.TemporaryDirectory() as d:
        bd5 = _bot_data(d)
        storage5 = bd5["storage"]
        ctx5 = FakeContext(bd5)
        await A.admin_open(FakeUpdate(message=FakeMessage("/admin"), user=FakeUser(42)), ctx5)

        uid = 2000
        for country, iso2, n in (("Азербайджан", "AZ", 3), ("Германия", "DE", 1), ("США", "US", 2)):
            for _ in range(n):
                uid += 1
                storage5.save_profile({
                    "user_id": uid, "username": f"u{uid}", "vertical": "Gambling",
                    "grade": "C-Level", "profession": "CEO", "request": "r",
                    "name": f"N{uid}", "company": "Acme", "linkedin": "-",
                    "country": country, "country_iso2": iso2,
                })

        await BC.bc_audience_country_menu(FakeUpdate(query=FakeQuery("acms_bc_aud:country")), ctx5)
        texts = kb_texts(ctx5.bot.last_markup)
        check("🇦🇿 Азербайджан — 3" in texts, "country-bc: кнопка с флагом, именем и счётчиком")
        check("🇺🇸 США — 2" in texts, "country-bc: вторая страна тоже с флагом")
        check(texts.index("🇦🇿 Азербайджан — 3") < texts.index("🇺🇸 США — 2") < texts.index("🇩🇪 Германия — 1"),
              "country-bc: сортировка по убыванию количества")

        await BC.bc_pick_country(FakeUpdate(query=FakeQuery("acms_bc_country:0")), ctx5)  # топ по счётчику = Азербайджан
        check(ctx5.user_data["bc"]["audience"]["mode"] == "country", "country-bc: режим аудитории country")
        check(ctx5.user_data["bc"]["audience"]["value"] == "Азербайджан", "country-bc: выбрана верная страна")
        check(len(BC._targets(ctx5, ctx5.user_data["bc"])) == 3, "country-bc: таргеты — все 3 профиля страны")

        # overflow: добавим много стран сверх лимита COUNTRY_BUTTON_LIMIT=20
        for i in range(25):
            uid += 1
            storage5.save_profile({
                "user_id": uid, "username": f"ov{uid}", "vertical": "Gambling",
                "grade": "C-Level", "profession": "CEO", "request": "r",
                "name": f"N{uid}", "company": "Acme", "linkedin": "-",
                "country": f"Страна{i}", "country_iso2": "",
            })
        segments = storage5.country_broadcast_segments()
        overflow_expected = sum(s["n"] for s in segments[BC.COUNTRY_BUTTON_LIMIT:])
        check(overflow_expected > 0, "country-bc: тестовые данные дают overflow (>20 стран)")

        await BC.bc_audience_country_menu(FakeUpdate(query=FakeQuery("acms_bc_aud:country")), ctx5)
        overflow_label = next((t for t in kb_texts(ctx5.bot.last_markup) if "Остальные страны" in t), None)
        check(overflow_label == f"🌐 Остальные страны — {overflow_expected}",
              "country-bc: overflow-кнопка с верным суммарным счётчиком")

        await BC.bc_pick_country_other(FakeUpdate(query=FakeQuery("acms_bc_country_other")), ctx5)
        check(ctx5.user_data["bc"]["audience"]["mode"] == "country_other", "country-bc: режим overflow")
        check(len(BC._targets(ctx5, ctx5.user_data["bc"])) == overflow_expected,
              "country-bc: overflow-таргеты соответствуют заявленному счётчику")
        storage5.close()


def test_admin_start_entry_point():
    """РЕГРЕССИЯ 20.07.2026: /start у админа зависал — admin_open() раньше
    вызывался НАПРЯМУЮ из flow.start(), в обход диспетчера ConversationHandler,
    поэтому conversation state gambling_admin_cms по-настоящему не
    проставлялся (если у админа не было уже АКТИВНОЙ сессии — например, только
    что вышел через «✖ Выход» — все кнопки дашборда молча переставали
    отвечать). Фикс: /start — ВТОРОЙ entry_point самого gambling_admin_cms
    (admin_start, с filters.User по admin_ids), заходит через настоящий
    диспетчер PTB. Тест проверяет ИМЕННО механизм диспетчеризации (check_update
    реального CommandHandler), а не вызов функции напрямую — баг был именно в
    обходе диспетчера, обычные unit-тесты (вызов хендлеров как функций) его
    не ловят."""
    print("== admin /start entry point (regression) ==")
    import datetime
    from telegram import Chat, Message, MessageEntity, Update, User
    import handlers.admin_cms as A

    class _FakeBotForCommand:
        username = "GamblingCommunitybot"

    def _real_update(text, uid):
        chat = Chat(id=uid, type="private")
        user = User(id=uid, is_bot=False, first_name="T")
        entities = [MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(text.split()[0]))]
        msg = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user,
                      text=text, entities=entities)
        msg.set_bot(_FakeBotForCommand())
        return Update(update_id=1, message=msg)

    ch_none = A.build_admin_cms()
    check(len(ch_none.entry_points) == 1,
          "без admin_ids -> только /admin entry_point (нет второго /start)")

    ch = A.build_admin_cms(admin_ids=(42, 43))
    check(len(ch.entry_points) == 2, "с admin_ids -> оба entry_point (/admin и /start)")
    start_entry = ch.entry_points[1]

    u_admin = _real_update("/start", 42)
    u_admin2 = _real_update("/start u_400", 43)
    u_other = _real_update("/start", 999)
    check(bool(start_entry.check_update(u_admin)),
          "admin_start entry_point матчит /start от админа (42)")
    check(bool(start_entry.check_update(u_admin2)),
          "admin_start entry_point матчит /start с deep-link payload от админа (43)")
    check(not start_entry.check_update(u_other),
          "admin_start entry_point НЕ матчит /start от НЕ-админа (999) -> уходит в gambling_form как раньше")


def test_persistence():
    print("== persistence wiring ==")
    import tempfile as _tf
    from telegram.ext import Application, PersistenceInput, PicklePersistence
    from handlers.flow import build_conversation
    from handlers.admin_cms import build_admin_cms
    from handlers.gossip import build_gossip_handlers

    persistence = PicklePersistence(
        filepath=_tf.mktemp(suffix=".pkl"),
        store_data=PersistenceInput(bot_data=False, user_data=True, chat_data=True, callback_data=False),
    )
    check(persistence.store_data.bot_data is False, "persistence исключает bot_data")
    app = Application.builder().token("123:ABCDEF").persistence(persistence).build()
    # persistent=True конв-хендлеры подключаются только при наличии persistence —
    # отсутствие исключения подтверждает корректную обвязку.
    app.add_handler(build_conversation())
    app.add_handler(build_admin_cms(admin_ids=(42,)))
    for h in build_gossip_handlers():
        app.add_handler(h)
    check(True, "persistent ConversationHandler-ы подключены с persistence")


# --- GURO ID (партнёрства/репутация) --------------------------------------

def test_guro_id_init_data():
    print("== guro_id: initData ==")
    import time as _time
    import guro_logic as GLm

    token = "123456:ABCDEF"
    params = {"auth_date": str(int(_time.time())), "user": '{"id":42,"username":"ann"}'}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    import hashlib as _hl
    import hmac as _hmac
    secret = _hmac.new(b"WebAppData", token.encode(), _hl.sha256).digest()
    good_hash = _hmac.new(secret, data_check_string.encode(), _hl.sha256).hexdigest()
    from urllib.parse import urlencode
    init_data_ok = urlencode({**params, "hash": good_hash})
    init_data_bad = urlencode({**params, "hash": "deadbeef"})

    user = GLm.verify_init_data(init_data_ok, token)
    check(user is not None and user["id"] == 42, "verify_init_data принимает корректную подпись")
    check(GLm.verify_init_data(init_data_bad, token) is None, "verify_init_data режет неверную подпись")
    check(GLm.verify_init_data("", token) is None, "verify_init_data режет пустую строку")

    old_params = {**params, "auth_date": "1"}
    old_check_string = "\n".join(f"{k}={v}" for k, v in sorted(old_params.items()))
    old_hash = _hmac.new(secret, old_check_string.encode(), _hl.sha256).hexdigest()
    init_data_old = urlencode({**old_params, "hash": old_hash})
    check(GLm.verify_init_data(init_data_old, token) is None, "verify_init_data режет протухший auth_date")


def test_guro_id_reputation_formula():
    print("== guro_id: формула рейтинга v2 (25.08.2026, ТЗ 'формула рейтинга') ==")
    import guro_logic as GLm
    import guro_constants as GCm
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    # 5.6 — бонус за стаж, теперь часть W (не стартовая репутация).
    check(GLm.tenure_bonus(None, now) == 0.0, "нет даты регистрации -> бонус за стаж = 0")
    check(GLm.tenure_bonus(now, now) == 0.0, "0 дней в комьюнити -> бонус за стаж = 0")
    check(abs(GLm.tenure_bonus(now - timedelta(days=40), now) - 2.0) < 1e-9, "40 дней × 0.05 = +2.0")
    very_old = now - timedelta(days=3650)
    check(GLm.tenure_bonus(very_old, now) == GCm.TENURE_BONUS_MAX, "бонус за стаж капается в TENURE_BONUS_MAX")

    # 5.3 — сжатие W в шкалу 0-100, монотонно, без выхода за границы.
    check(GLm.reputation_from_w(0.0) == 0.0, "W=0 -> R=0")
    check(GLm.reputation_from_w(-100) < 0, "отрицательный W даёт отрицательный R (штрафы могут увести в минус)")
    r_small = GLm.reputation_from_w(10)
    r_big = GLm.reputation_from_w(1000)
    check(0 < r_small < r_big < 100, "формула монотонна и не превышает 100")
    check(GLm.reputation_tier(0) == "Bronze", "R=0 -> Bronze")
    check(GLm.reputation_tier(95) == "Platinum", "R=95 -> Platinum")

    # 5.1+5.2 — базовые очки по типу сделки + диминишинг повторов.
    check(GLm.partnership_base_weight("deal", 0) == 10.0, "5.1: первая 'сделка' = 10 очков")
    check(GLm.partnership_base_weight("hire", 0) == 15.0, "5.1: первый 'найм' = 15 очков")
    check(GLm.partnership_base_weight("deal", 1) == 2.0, "5.2: 1-й повтор с тем же контрагентом = 20% от базы")
    check(GLm.partnership_base_weight("deal", 3) == 2.0, "5.2: 3-й повтор всё ещё 20%")
    check(GLm.partnership_base_weight("deal", 4) == 0.0, "5.2: 4-й повтор и далее -> 0 (анти-фарм)")

    # 5.4/5.5 — крипто-бонус.
    check(GLm.crypto_bonus_multiplier(False, False) == 1.0, "без верификации хеша -> множитель 1.0")
    check(GLm.crypto_bonus_multiplier(True, False) == GCm.CRYPTO_VERIFIED_MULTIPLIER, "верифицирован -> обычный множитель")
    check(GLm.crypto_bonus_multiplier(True, True) == GCm.CRYPTO_COMPANY_MULTIPLIER, "адрес компании совпал -> повышенный множитель")
    check(GLm.log_amount_bonus(100, tx_verified=False) == 0.0, "сумма без верификации хеша НЕ даёт бонуса (анти-фарм, см. допущение в guro_constants.py)")
    check(GLm.log_amount_bonus(None, tx_verified=True) == 0.0, "нет суммы -> бонус 0 даже при верификации")
    check(GLm.log_amount_bonus(100, tx_verified=True) > 0, "верифицированная сумма > 0 -> положительный бонус")

    # 6.1 — влияние оценки Шага 2 на W ОДНОЙ стороны (см. rating_delta).
    base = 10.0
    check(GLm.rating_delta(None, base, tx_verified=False, tx_company_match=False, amount=None) == 0.0,
          "контрагент не оценил (или не раскрыто) -> нейтрально, как 'были нюансы'")
    check(GLm.rating_delta(GCm.RATING_NUANCE, base, tx_verified=False, tx_company_match=False, amount=None) == 0.0,
          "'были нюансы' -> без бонусов, нейтрально")
    check(GLm.rating_delta(GCm.RATING_PROBLEMATIC, base, tx_verified=False, tx_company_match=False, amount=None) == -GCm.PARTNERSHIP_PENALTY_POINTS,
          "'проблемная сделка' -> штраф PARTNERSHIP_PENALTY_POINTS")
    success_delta = GLm.rating_delta(GCm.RATING_SUCCESS, base, tx_verified=True, tx_company_match=False, amount=None)
    check(abs(success_delta - base * (GCm.CRYPTO_VERIFIED_MULTIPLIER - 1.0)) < 1e-9,
          "'успешно' + верифицированный хеш -> бонус = base×(множитель-1)")
    check(GLm.rating_delta(GCm.RATING_SUCCESS, base, tx_verified=False, tx_company_match=False, amount=None) == 0.0,
          "'успешно' БЕЗ верификации хеша -> бонуса нет (уже начислено при подтверждении)")

    old_join = now - timedelta(days=95)
    check(GLm.counts_toward_rating(old_join, old_join, now), "оба старше 14 дней -> учитывается")
    fresh = now - timedelta(days=2)
    check(not GLm.counts_toward_rating(old_join, fresh, now), "один младше 14 дней -> НЕ учитывается")
    check(not GLm.counts_toward_rating(None, old_join, now), "нет даты -> НЕ учитывается")

    # 08.09.2026: правило стало потолком за сутки (три заявки на пару),
    # а не паузой между заявками, поэтому функция принимает КОЛИЧЕСТВО.
    check(not GLm.rate_limited(0), "заявок за сутки не было -> не залимичено")
    check(not GLm.rate_limited(2), "две заявки за сутки -> ещё можно")
    check(GLm.rate_limited(3), "три заявки за сутки -> потолок достигнут")
    check(GLm.rate_limited(4), "сверх потолка -> тоже залимичено")


def test_guro_id_storage():
    print("== guro_id: storage ==")
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from storage import Storage
    from guro_storage import GuroStorage
    import guro_constants as GC
    import guro_logic as GL

    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "t.sqlite3"
        st = Storage(db_path)  # создаёт таблицу profiles
        st.save_profile({"user_id": 1, "username": "alice", "name": "Alice"})
        st.save_profile({"user_id": 2, "username": "bob", "name": "Bob"})

        gst = GuroStorage(db_path)  # тот же файл, отдельное соединение — как в проде (2 процесса)
        check(gst.find_profile_by_username("@Alice") is not None, "поиск по юзернейму регистронезависим и терпит @")
        check(gst.find_profile_by_username("nobody") is None, "поиск несуществующего юзернейма -> None")

        u1 = gst.get_or_create_guro_user(1)
        check(u1["reputation_score"] == 0.0, f"первичная репутация = 0 (0 сделок, 0 дней стажа), а не {u1['reputation_score']}")

        # 28.08.2026 (макет "09 · Приватность"): смешанная политика — 4
        # opt-out поля (show_name/show_company/show_vertical/show_profession,
        # default=1) видны по умолчанию, остальные — opt-in (default=0),
        # см. guro_storage.py::_OPT_OUT_PRIVACY_FIELDS.
        privacy = gst.get_privacy(1)
        opt_out_fields = {"show_name", "show_company", "show_vertical", "show_profession"}
        check(
            all(privacy[k] is True for k in opt_out_fields) and all(v is False for k, v in privacy.items() if k not in opt_out_fields),
            "приватность по умолчанию: opt-out поля видны, остальное скрыто (opt-in)",
        )
        updated = gst.set_privacy_field(1, "show_cv", True)
        check(updated["show_cv"] is True, "set_privacy_field включает конкретный тумблер")
        check(updated["show_contacts"] is False, "остальные opt-in тумблеры не трогает")
        check(updated["show_name"] is True, "opt-out тумблеры тоже не трогает (остаются как были)")
        check(gst.get_privacy(1)["show_cv"] is True, "значение сохраняется между вызовами")
        try:
            gst.set_privacy_field(1, "show_everything", True)
            check(False, "неизвестное поле должно кидать UNKNOWN_FIELD")
        except ValueError as e:
            check(str(e) == "UNKNOWN_FIELD", "неизвестное поле -> ValueError(UNKNOWN_FIELD)")

        # Продление АКТИВНОЙ подписки прибавляет к остатку, не сбрасывает
        # (28.08.2026, найдено по макету "10 · Подписка" — реальный
        # биллинг-баг: раньше ранняя оплата тихо съедала уже оплаченные
        # дни). Чистая функция — без похода в БД, чтобы не влиять на
        # dashboard_stats дальше по тесту.
        now = datetime.now(timezone.utc)
        active_expiry = now + timedelta(days=300)
        extended = GL.subscription_expires_at(now, 30, current_expires_at=active_expiry)
        check(abs((extended - active_expiry).total_seconds() - 30 * 86400) < 1,
              "продление активной подписки прибавляет duration_days к ОСТАВШЕМУСЯ сроку, не сбрасывает на now+duration")
        expired_expiry = now - timedelta(days=5)
        renewed = GL.subscription_expires_at(now, 30, current_expires_at=expired_expiry)
        check(abs((renewed - now).total_seconds() - 30 * 86400) < 1,
              "продление ПРОСРОЧЕННОЙ подписки считается от now, а не от старой (уже прошедшей) даты")

        # Интеграционная проверка через storage (user 1 — уже часть набора
        # "активных" ниже по тесту, повторная активация не меняет счёт
        # dashboard_stats, только освежает срок).
        gst.activate_subscription(1, 30)
        first_expiry = GL.parse_db_datetime(gst.get_or_create_guro_user(1)["subscription_expires_at"])
        gst.activate_subscription(1, 30)
        second_expiry = GL.parse_db_datetime(gst.get_or_create_guro_user(1)["subscription_expires_at"])
        check(
            abs((second_expiry - first_expiry).total_seconds() - 30 * 86400) < 5,
            "activate_subscription: та же логика продления, но через реальный storage-слой",
        )
        check(gst.get_or_create_guro_user(1)["subscription_cycle_days"] == 30,
              "subscription_cycle_days запоминает длину последнего цикла (для progress bar)")

        try:
            gst.create_partnership(1, 1, None, None)
            check(False, "партнёрство с самим собой должно кидать SELF_PARTNERSHIP")
        except ValueError as e:
            check(str(e) == "SELF_PARTNERSHIP", "self-partnership -> ValueError(SELF_PARTNERSHIP)")

        try:
            gst.create_partnership(1, 999, None, None)
            check(False, "партнёрство с юзером без анкеты должно кидать NO_CONFIRMER_PROFILE")
        except ValueError as e:
            check(str(e) == "NO_CONFIRMER_PROFILE", "нет анкеты у confirmer -> ValueError(NO_CONFIRMER_PROFILE)")

        try:
            gst.create_partnership(1, 2, "casino", "Odessa", ptype="whatever")
            check(False, "неизвестный тип партнёрства должен кидать INVALID_TYPE")
        except ValueError as e:
            check(str(e) == "INVALID_TYPE", "мусорный ptype -> ValueError(INVALID_TYPE)")

        p = gst.create_partnership(1, 2, "casino", "Odessa")
        check(p["status"] == "pending", "новое партнёрство в статусе pending")
        check(p["ptype"] == "deal", "ptype по умолчанию = 'deal'")

        # Проверка потолка «три заявки на пару за сутки» вынесена в КОНЕЦ
        # этой функции: она создаёт лишние строки, а ниже по тесту
        # dashboard_stats считает все партнёрства разом.

        try:
            gst.respond_partnership(p["id"], responder_id=1, accept=True)
            check(False, "ответ не от confirmer должен кидать NOT_YOUR_REQUEST")
        except ValueError as e:
            check(str(e) == "NOT_YOUR_REQUEST", "ответ не от confirmer -> ValueError(NOT_YOUR_REQUEST)")

        rep1_before = gst.get_or_create_guro_user(1)["reputation_score"]
        rep2_before = gst.get_or_create_guro_user(2)["reputation_score"]
        confirmed = gst.respond_partnership(p["id"], responder_id=2, accept=True)
        check(confirmed["status"] == "confirmed", "respond_partnership(accept=True) -> confirmed")
        # 25.08.2026, формула v2: tenure/подписка теперь проверяются НА МОМЕНТ
        # ПОДТВЕРЖДЕНИЯ (не заявки) — оба свежих (<14д) И без подписки ->
        # counts_toward_rating=0, base_weight=0, репутация не меняется.
        check(confirmed["counts_toward_rating"] == 0, "свежие аккаунты без подписки -> НЕ учитывается в рейтинге")
        check(confirmed["base_weight"] == 0.0, "не учитывается -> base_weight=0")
        rep1_after = gst.get_or_create_guro_user(1)["reputation_score"]
        rep2_after = gst.get_or_create_guro_user(2)["reputation_score"]
        check(rep1_after == rep1_before and rep2_after == rep2_before,
              "counts_toward_rating=0 -> подтверждение НЕ меняет репутацию (свежие аккаунты)")
        check(gst.count_confirmed_partnerships(1) == 1, "у user 1 одно подтверждённое партнёрство")

        try:
            gst.respond_partnership(p["id"], responder_id=2, accept=True)
            check(False, "повторный ответ на решённую заявку должен кидать ALREADY_RESOLVED")
        except ValueError as e:
            check(str(e) == "ALREADY_RESOLVED", "повторный ответ -> ValueError(ALREADY_RESOLVED)")

        # старые аккаунты + активная подписка ОБОИХ -> партнёрство должно
        # учитываться и менять репутацию (25.08.2026: оба условия новые —
        # раньше требовался только стаж).
        import sqlite3
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE profiles SET created_at=? WHERE user_id IN (1,2)", (old_ts,))
        conn.commit()
        conn.close()
        st.save_profile({"user_id": 3, "username": "carl", "name": "Carl"})
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE profiles SET created_at=? WHERE user_id=3", (old_ts,))
        conn.commit()
        conn.close()
        gst3 = GuroStorage(db_path)
        p2 = gst3.create_partnership(1, 3, None, None, ptype="hire")
        gst3.activate_subscription(1, 30)
        gst3.activate_subscription(3, 30)
        # "Найм" (6, п.3) — очки откладываются, пока кандидат не переключит
        # work_status на "работаю"; ставим ЗАРАНЕЕ, чтобы очки применились сразу.
        gst3.set_work_status(3, GC.WORK_STATUS_WORKING)
        rep3_before = gst3.get_or_create_guro_user(3)["reputation_score"]
        rep1_before2 = gst3.get_or_create_guro_user(1)["reputation_score"]
        confirmed2 = gst3.respond_partnership(p2["id"], responder_id=3, accept=True)
        check(confirmed2["counts_toward_rating"] == 1, "оба старше 14 дней И оба подписаны -> partnership учитывается")
        check(confirmed2["base_weight"] == 15.0, "тип 'hire', 1-е партнёрство с этим контрагентом -> 15 очков")
        check(confirmed2["repeat_index"] == 0, "первое партнёрство с этим контрагентом -> repeat_index=0")
        check(confirmed2["hire_status_pending"] == 0, "кандидат уже 'работаю' на момент подтверждения -> очки не отложены")
        rep3_after = gst3.get_or_create_guro_user(3)["reputation_score"]
        rep1_after2 = gst3.get_or_create_guro_user(1)["reputation_score"]
        check(rep3_after > rep3_before, "подтверждённое учитываемое партнёрство поднимает репутацию confirmer")
        check(rep1_after2 > rep1_before2, "и репутацию initiator тоже (симметрично)")

        check(gst3.is_subscribed(1), "activate_subscription -> is_subscribed True")
        check(not gst3.is_subscribed(2), "user 2 без подписки -> is_subscribed False")

        # оценка партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) — anti-retaliation:
        # раскрытие только когда ОБЕ стороны оценили. 25.08.2026 (фидбек
        # владельца, "Правки.pdf"): повторная отправка теперь РЕДАКТИРУЕТ
        # (upsert), а не кидает ALREADY_RATED; своя оценка удаляется через
        # delete_rating.
        gst3.submit_rating(p2["id"], rater_id=1, verdict="success", comment=None)
        not_yet = gst3.get_partnership(p2["id"])
        check(not_yet["rating_revealed_at"] is None, "одна оценка из двух -> ещё не раскрыто")

        # 28.08.2026 (макет "07 · Сделки — шаг 2"): комментарий теперь
        # ОБЯЗАТЕЛЕН для "nuance" (раньше молча отбрасывался, как у
        # "success") — без него submit_rating кидает COMMENT_REQUIRED.
        try:
            gst3.submit_rating(p2["id"], rater_id=1, verdict="nuance", comment=None)
            check(False, "'nuance' без комментария должен кидать COMMENT_REQUIRED")
        except ValueError as e:
            check(str(e) == "COMMENT_REQUIRED", "'nuance' без комментария -> ValueError(COMMENT_REQUIRED)")

        gst3.submit_rating(p2["id"], rater_id=1, verdict="nuance", comment="частично задержал ответ")
        edited = gst3.get_my_rating(p2["id"], 1)
        check(edited["verdict"] == "nuance", "повторная отправка РЕДАКТИРУЕТ оценку (upsert), не кидает ошибку")
        check(edited["comment"] == "частично задержал ответ", "комментарий 'nuance' теперь СОХРАНЯЕТСЯ (раньше отбрасывался)")

        try:
            gst3.submit_rating(p2["id"], rater_id=999, verdict="success", comment=None)
            check(False, "оценка от постороннего должна кидать NOT_YOUR_PARTNERSHIP")
        except ValueError as e:
            check(str(e) == "NOT_YOUR_PARTNERSHIP", "не участник партнёрства -> ValueError(NOT_YOUR_PARTNERSHIP)")

        try:
            gst3.delete_rating(p2["id"], 999)
            check(False, "удаление чужой (несуществующей у 999) оценки должно кидать RATING_NOT_FOUND")
        except ValueError as e:
            check(str(e) == "NOT_YOUR_PARTNERSHIP", "999 вообще не участник партнёрства -> NOT_YOUR_PARTNERSHIP раньше RATING_NOT_FOUND")

        rep3_before_rating = gst3.get_or_create_guro_user(3)["reputation_score"]
        gst3.submit_rating(p2["id"], rater_id=3, verdict="problematic", comment="задержал оплату")
        revealed = gst3.get_partnership(p2["id"])
        check(revealed["rating_revealed_at"] is not None, "обе стороны оценили -> раскрыто сразу")
        rep1_after_rating = gst3.get_or_create_guro_user(1)["reputation_score"]
        check(rep1_after_rating < rep1_after2, "3 оценил 1 как 'проблемная' -> репутация 1 упала (штраф)")
        rep3_after_rating = gst3.get_or_create_guro_user(3)["reputation_score"]
        check(rep3_after_rating == rep3_before_rating, "1 оценил 3 как 'нюансы' -> нейтрально, без изменений")

        # Удаление оценки ПОСЛЕ раскрытия (25.08.2026, фидбек владельца:
        # "удалить может тот, кто отзыв оставил") — сразу пересчитывает W контрагента.
        gst3.delete_rating(p2["id"], rater_id=3)
        rep1_after_delete = gst3.get_or_create_guro_user(1)["reputation_score"]
        check(rep1_after_delete == rep1_after2,
              "оценка 3-го про 1-го удалена -> штраф снят, репутация 1 вернулась к значению до оценки")
        check(gst3.get_rating_of(p2["id"], 1) is None, "оценки 3-го про 1-го больше нет в БД")
        try:
            gst3.delete_rating(p2["id"], rater_id=3)
            check(False, "повторное удаление уже удалённой оценки должно кидать RATING_NOT_FOUND")
        except ValueError as e:
            check(str(e) == "RATING_NOT_FOUND", "повторное удаление -> ValueError(RATING_NOT_FOUND)")

        # "Найм" (6, п.3), путь ОТЛОЖЕННЫХ очков — кандидат ещё НЕ "работаю"
        # на момент подтверждения -> очки не применяются до синка (guro_partnership_sync.py).
        st.save_profile({"user_id": 4, "username": "dave", "name": "Dave"})
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE profiles SET created_at=? WHERE user_id=4", (old_ts,))
        conn.commit()
        conn.close()
        gst3.activate_subscription(4, 30)
        p3 = gst3.create_partnership(1, 4, None, None, ptype="hire")
        rep4_before = gst3.get_or_create_guro_user(4)["reputation_score"]
        confirmed3 = gst3.respond_partnership(p3["id"], responder_id=4, accept=True)
        check(confirmed3["hire_status_pending"] == 1, "кандидат ещё не 'работаю' -> очки отложены")
        rep4_after = gst3.get_or_create_guro_user(4)["reputation_score"]
        check(rep4_after == rep4_before, "отложенный найм -> репутация НЕ меняется")
        check(not gst3.sync_hire_status(p3["id"]), "sync_hire_status до смены статуса -> False, ничего не применилось")
        gst3.set_work_status(4, GC.WORK_STATUS_WORKING)
        check(gst3.sync_hire_status(p3["id"]), "sync_hire_status после смены статуса -> True, очки применены")
        rep4_synced = gst3.get_or_create_guro_user(4)["reputation_score"]
        check(rep4_synced > rep4_after, "после синка репутация кандидата выросла")
        check(gst3.get_partnership(p3["id"])["hire_status_pending"] == 0, "флаг снят после синка")

        stats = gst3.dashboard_stats()
        check(stats["total"] == 3, f"dashboard_stats: total=3 (1-2, 1-3, 1-4), а не {stats['total']}")
        check(stats["confirmed"] == 3, f"dashboard_stats: confirmed=3, а не {stats['confirmed']}")
        check(stats["pending"] == 0, "dashboard_stats: pending=0")
        check(stats["declined"] == 0, "dashboard_stats: declined=0")
        check(stats["active_subscriptions_guro_id"] == 3, "dashboard_stats: active_subscriptions_guro_id=3 (users 1,3,4)")

        # --- разбивка по продуктам + отсев ручных выдач (11.09.2026) --------
        gst3.activate_recruiter_subscription(1, 30)
        gst3.activate_company_subscription(1, 30)
        stats_split = gst3.dashboard_stats()
        check(stats_split["active_subscriptions_recruiter"] == 1, "рекрутерская подписка считается отдельно от GURO ID")
        check(stats_split["active_subscriptions_company"] == 1, "подписка компании считается отдельно от GURO ID")

        # личная доля владельца (каждый 5-й крипто-платёж) — не в статистику,
        # ни у одного из трёх продуктов
        gst3.activate_recruiter_subscription(1, 30, personal_cut=True)
        gst3.activate_company_subscription(1, 30, personal_cut=True)
        stats_cut = gst3.dashboard_stats()
        check(stats_cut["active_subscriptions_recruiter"] == 0, "личная доля владельца (рекрутер) не попадает в статистику")
        check(stats_cut["active_subscriptions_company"] == 0, "личная доля владельца (компания) не попадает в статистику")

        # ручная выдача (владелец правит expires_at в БД на годы вперёд) —
        # тоже не в статистику, даже без personal_cut
        far = GL.format_db_datetime(gst3._now() + timedelta(days=365 * 5))
        gst3._conn.execute(
            "UPDATE guro_users SET subscription_status=?, subscription_expires_at=?, subscription_personal_cut=0 "
            "WHERE user_id=?", (GC.SUBSCRIPTION_ACTIVE, far, 1),
        )
        gst3._conn.commit()
        stats_granted = gst3.dashboard_stats()
        check(stats_granted["active_subscriptions_guro_id"] == 2,
              f"ручная выдача на 5 лет вперёд исключена из счётчика (было 3, юзер 1 выпал): {stats_granted['active_subscriptions_guro_id']}")
        check(stats["tracked_users"] >= 4, "dashboard_stats: tracked_users учитывает всех с guro_users row")

        # расширение "Моё CV" (12.08.2026) — потолок записей опыта работы
        for i in range(GC.CV_EXPERIENCE_MAX):
            gst3.add_cv_experience(1, company=f"Co{i}", position="Dev")
        check(len(gst3.list_cv_experience(1)) == GC.CV_EXPERIENCE_MAX,
              f"добавлено ровно CV_EXPERIENCE_MAX={GC.CV_EXPERIENCE_MAX} записей")
        try:
            gst3.add_cv_experience(1, company="Overflow", position="Dev")
            check(False, "запись сверх CV_EXPERIENCE_MAX должна кидать LIMIT_REACHED")
        except ValueError as e:
            check(str(e) == "LIMIT_REACHED", "потолок записей опыта -> ValueError(LIMIT_REACHED)")

        # 08.09.2026: на пару разрешено ТРИ заявки за скользящие сутки (было
        # одна). Стоит в самом конце — проверка создаёт строки, а
        # dashboard_stats выше считает все партнёрства разом. Проверяем оба
        # края: иначе тест перестанет ловить снятие ограничителя вовсе.
        # Первая заявка между 1 и 2 уже была заведена в начале функции.
        gst3.create_partnership(1, 2, "casino", "Odessa")
        check(True, "вторая заявка на ту же пару за сутки проходит")
        gst3.create_partnership(1, 2, "casino", "Odessa")
        check(True, "третья заявка на ту же пару за сутки проходит")
        try:
            gst3.create_partnership(1, 2, "casino", "Odessa")
            check(False, "четвёртая заявка за сутки должна кидать RATE_LIMITED")
        except ValueError as e:
            check(str(e) == "RATE_LIMITED",
                  "анти-фрод: четвёртая заявка на ту же пару за сутки -> RATE_LIMITED")


def test_guro_id_recruiter_dashboard():
    print("== guro_id: кабинет 'Рекрутер', главный экран (26.08.2026) ==")
    import tempfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    import guro_constants as GC
    import guro_logic as GLm
    from storage import Storage
    from guro_storage import GuroStorage

    # 5.2 (перцентиль) — чистые функции.
    check(GLm.percentile_of(9, 10) == 90.0, "9 из 10 меньше -> перцентиль 90")
    check(GLm.percentile_of(0, 10) == 0.0, "0 меньше -> перцентиль 0")
    check(GLm.percentile_of(5, 0) == 0.0, "total=0 -> 0.0, не деление на ноль")
    check(GLm.percentile_tier(96) == "5", "96-й перцентиль -> топ-5%")
    check(GLm.percentile_tier(91) == "10", "91-й -> топ-10%")
    check(GLm.percentile_tier(80) == "25", "80-й -> топ-25%")
    check(GLm.percentile_tier(55) == "50", "55-й -> топ-50%")
    check(GLm.percentile_tier(49) is None, "ниже топ-50% -> None (не показываем цифру)")

    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "t.sqlite3"
        st = Storage(db_path)
        st.save_profile({"user_id": 10, "username": "recruiter1", "name": "Rec1"})
        st.save_profile({"user_id": 20, "username": "candidate1", "name": "Cand1"})
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE profiles SET created_at=?", (old_ts,))
        conn.commit()
        conn.close()

        gst = GuroStorage(db_path)

        # Статус активности (2.4) — тот же приём, что work_status.
        check(gst.get_recruiter_activity_status(10) is None, "по умолчанию статус активности не задан")
        result = gst.set_recruiter_activity_status(10, GC.RECRUITER_ACTIVITY_HIRING)
        check(result == "hiring", "статус активности сохраняется")
        try:
            gst.set_recruiter_activity_status(10, "garbage")
            check(False, "мусорное значение статуса должно кидать INVALID_STATUS")
        except ValueError as e:
            check(str(e) == "INVALID_STATUS", "невалидный статус -> ValueError(INVALID_STATUS)")

        # "Стаж в роли рекрутера" — first_activated_at ставится ОДИН раз.
        check(gst.get_or_create_recruiter_profile(10)["first_activated_at"] is None,
              "до оплаты first_activated_at не проставлен")
        gst.activate_recruiter_subscription(10, 30)
        first_at = gst.get_or_create_recruiter_profile(10)["first_activated_at"]
        check(first_at is not None, "activate_recruiter_subscription проставляет first_activated_at")
        gst.activate_recruiter_subscription(10, 365)  # продление -> дата НЕ должна поменяться
        check(gst.get_or_create_recruiter_profile(10)["first_activated_at"] == first_at,
              "продление подписки НЕ трогает first_activated_at (стаж считается от первой оплаты)")

        # Метрики "Характеристика" (2.3).
        check(gst.count_active_vacancies(10) == 0, "новых вакансий пока нет")
        gst.create_vacancy(10, author_workspace="recruiter", title="QA Engineer")
        gst.create_vacancy(10, author_workspace="recruiter", title="Affiliate Manager")
        check(gst.count_active_vacancies(10) == 2, "2 активные вакансии")
        v = gst.create_vacancy(10, author_workspace="recruiter", title="Closed one")
        gst.close_vacancy(v["id"], 10)
        check(gst.count_active_vacancies(10) == 2, "закрытая вакансия не считается активной")

        check(gst.count_confirmed_partnerships_by_type(10, GC.PARTNERSHIP_TYPE_HIRE) == 0, "наймов пока 0")
        gst.activate_subscription(10, 30)
        gst.activate_subscription(20, 30)
        gst.set_work_status(20, GC.WORK_STATUS_WORKING)  # кандидат уже "работаю" -> очки не откладываются
        p = gst.create_partnership(10, 20, None, None, ptype="hire")
        gst.respond_partnership(p["id"], responder_id=20, accept=True)
        check(gst.count_confirmed_partnerships_by_type(10, GC.PARTNERSHIP_TYPE_HIRE) == 1,
              "1 подтверждённый найм засчитан в метрику")

        # W_найм (2.5) — БЕЗ бонуса за стаж, только сумма base_weight подтверждённых hire.
        w = gst.hire_w(10)
        check(w == 15.0, f"W_найм = 15 (1-й найм, без диминишинга, без стажа), а не {w}")
        w_candidate = gst.hire_w(20)
        check(w_candidate == 15.0, "W_найм симметричен для confirmer'а тоже")

        # Кэш процентиля — читает/пишет storage, НЕ считает сам (это дело
        # guro_recruiter_percentile_sync.py).
        cached = gst.get_recruiter_percentile(10)
        check(cached["tier"] is None and cached["computed_at"] is None, "до первого прогона джоба кэш пуст")
        gst.set_recruiter_percentile(10, "10")
        cached2 = gst.get_recruiter_percentile(10)
        check(cached2["tier"] == "10" and cached2["computed_at"] is not None, "кэш обновился и проставил дату")

        # Вход для фонового джоба — рекрутер с вертикалью и хотя бы 1 наймом.
        gst.set_recruiter_extra_field(10, "vertical", "Gambling")
        pairs = gst.list_recruiter_verticals_with_hires()
        check((10, "Gambling") in pairs, "рекрутер с вертикалью и наймом попадает в выборку для перцентиля")

        # Единый инбокс: метка кабинета-источника у сообщения (2.7).
        msg = gst.send_message(10, 20, "Здравствуйте, есть вакансия", via_workspace="recruiter")
        check(msg["via_workspace"] == "recruiter", "сообщение помечено кабинетом-источником")
        msg2 = gst.send_message(20, 10, "Спасибо, расскажите подробнее")
        check(msg2["via_workspace"] == "personal", "via_workspace по умолчанию 'personal'")


def _guro_make_init_data(token: str, user: dict) -> str:
    import hashlib as _hl
    import hmac as _hmac
    import json as _json
    import time as _time
    from urllib.parse import urlencode

    params = {"auth_date": str(int(_time.time())), "user": _json.dumps(user)}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = _hmac.new(b"WebAppData", token.encode(), _hl.sha256).digest()
    good_hash = _hmac.new(secret, data_check_string.encode(), _hl.sha256).hexdigest()
    return urlencode({**params, "hash": good_hash})


async def _run_guro_id_api_sim():
    print("== guro_id: API (aiohttp routes) ==")
    import tempfile
    from pathlib import Path
    from unittest import mock

    from aiohttp.test_utils import TestClient, TestServer

    import guro_constants as GC
    import guro_id_api
    import guro_tags
    from config import Settings
    from storage import Storage

    class _FakeTGBot:
        # Класс-уровневые (не self.), т.к. sync_member_tag_standalone создаёт
        # НОВЫЙ Bot(token=...) на каждый вызов — состояние должно быть общим.
        member_status_map: dict = {}
        member_tag_map: dict = {}
        set_tag_calls: list = []

        def __init__(self, token=None):
            self.token = token

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send_message(self, *a, **kw):
            return None

        invoice_calls: list = []

        async def create_invoice_link(self, **kw):
            _FakeTGBot.invoice_calls.append(kw)
            return "https://t.me/fake_invoice_link"

        async def get_chat_member(self, chat_id, user_id):
            from telegram.constants import ChatMemberStatus

            class _Member:
                def __init__(self, status, tag):
                    self.status = status
                    self.tag = tag

            status = _FakeTGBot.member_status_map.get(user_id, ChatMemberStatus.MEMBER)
            return _Member(status, _FakeTGBot.member_tag_map.get(user_id))

        async def set_chat_member_tag(self, chat_id, user_id, tag=None, **kw):
            _FakeTGBot.set_tag_calls.append((chat_id, user_id, tag))
            _FakeTGBot.member_tag_map[user_id] = tag
            return True

    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "t.sqlite3"
        st = Storage(db_path)
        st.save_profile({
            "user_id": 100, "username": "initiator", "name": "Init", "company": "GURO Co",
            "vertical": "iGaming", "profession": "Manager", "linkedin": "linkedin.com/in/init",
            "request": "ищу партнёров",
        })
        st.save_profile({"user_id": 200, "username": "confirmer", "name": "Conf"})

        token = "111111:FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAK"
        settings = Settings(
            bot_token=token, base_dir=Path(d), database_path=db_path, admin_ids=(),
            community_invite_url="https://t.me/+TEST", google_sheets_enabled=False,
            google_sheets_spreadsheet_id="", google_sheets_worksheet_name="Анкеты",
            google_sheets_credentials_path=None, community_chat_id=555,
        )

        with mock.patch.object(guro_id_api, "Bot", _FakeTGBot), \
                mock.patch.object(guro_tags, "Bot", _FakeTGBot):
            app = guro_id_api.create_app(settings)
            server = TestServer(app)
            client = TestClient(server)
            await client.start_server()
            try:
                resp = await client.get("/api/me")
                check(resp.status == 401, "GET /api/me без Authorization -> 401")

                auth_100 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 100, "username": "initiator"})}
                resp = await client.get("/api/me", headers=auth_100)
                check(resp.status == 200, "GET /api/me с валидной initData -> 200")
                body = await resp.json()
                check(body["username"] == "initiator", "тело /api/me содержит username")
                # «Рейтинг сгорает без подписки» — пока у initiator (100) нет
                # активной подписки, реputation_score скрыт ДАЖЕ в его же /api/me.
                check(body["reputation_score"] is None,
                      "свежий профиль БЕЗ подписки -> reputation_score скрыт даже себе")
                check(app["storage"].get_or_create_guro_user(100)["reputation_score"] == 0.0,
                      "гейт РЕВЕРСИВНЫЙ: в БД значение реально есть (база 0), просто скрыто в выдаче API")
                check(not any(c[1] == 100 for c in _FakeTGBot.set_tag_calls),
                      "GET /api/me без подписки -> тег НЕ выставляется (одного захода в Mini App недостаточно)")

                # активируем подписку initiator'у — дальше тестируем privacy-тумблеры
                # и пейволл ИЗОЛИРОВАННО от гейта подписки (у него отдельный тест ниже)
                app["storage"].activate_subscription(100, 30)

                auth_ghost = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 999, "username": "ghost"})}
                resp = await client.get("/api/me", headers=auth_ghost)
                check(resp.status == 404, "GET /api/me для юзера без анкеты -> 404 NO_PROFILE")

                auth_200 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 200, "username": "confirmer"})}
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                check(resp.status == 200, "GET /api/search -> 200")
                body = await resp.json()
                check(body["locked"] is True, "поиск без подписки -> locked=True (пейволл)")
                check("company" not in body, "поиск без подписки -> урезанные поля")

                app["storage"].activate_subscription(200, 30)
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["locked"] is False, "поиск с активной подпиской -> locked=False")
                check(body["username"] == "initiator", "поиск с подпиской -> полная карточка")

                # Смешанная политика тумблеров (28.08.2026, макет "09 ·
                # Приватность", Untitled-12): show_name/show_company/
                # show_vertical/show_profession — opt-out (default=1,
                # видно по умолчанию, можно СКРЫТЬ), остальные
                # (show_cv/show_contacts/show_offers) — opt-in (default=0,
                # скрыто, нужно явно включить). До этого момента (в тот же
                # день, но раньше) эти 4 поля были ВООБЩЕ без гейта —
                # затем нашёлся макет отдельного экрана "Приватность
                # профиля" с этими же тумблерами, гейт вернули, но с
                # opt-out дефолтом (иначе каждый новый пользователь
                # оставался бы без имени в поиске, пока сам не зайдёт в
                # новый экран и не включит вручную).
                check(body["name"] == "Init", "имя личного профиля видно по умолчанию (opt-out)")
                check(body["company"] == "GURO Co" and body["vertical"] == "iGaming",
                      "company/vertical тоже видны по умолчанию (opt-out)")
                check(body["reputation_score"] is not None,
                      "рейтинг виден без тумблера -> подписки цели достаточно (приватность рейтинга убрана)")
                check(body["joined_community_at"] is not None and body["days_in_community"] is not None,
                      "стаж виден без тумблера по той же причине")
                check(body["confirmed_partnerships"] == 0, "число партнёрств видно ВСЕГДА, даже без единого включённого тумблера")
                check(body["profession"] == "Manager", "профессия личного профиля видна по умолчанию (opt-out)")
                check(body["linkedin"] is None and body["website"] is None,
                      "по умолчанию show_contacts выключен -> linkedin/website скрыты")
                check(body["looking_for"] is None and body["offering"] is None,
                      "по умолчанию show_offers выключен -> looking_for/offering скрыты")
                check(body["cv_text"] is None, "по умолчанию show_cv выключен -> cv_text скрыт")

                # opt-out работает и в обратную сторону — явно выключенный
                # тумблер реально прячет поле (не просто мёртвая настройка).
                await client.post("/api/privacy", headers=auth_100, json={"field": "show_profession", "value": False})
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["profession"] is None, "явно выключенный show_profession реально прячет поле (opt-out можно выключить)")
                check(body["name"] == "Init", "остальные opt-out поля не задеты выключением одного")
                await client.post("/api/privacy", headers=auth_100, json={"field": "show_profession", "value": True})

                # редизайн профиля: /api/me отдаёт поля анкеты (профессия/linkedin/
                # "ищу"), даже те, что не были в _profile_summary раньше
                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["profession"] == "Manager", "/api/me: профессия из анкеты видна себе")
                check(body["linkedin"] == "linkedin.com/in/init", "/api/me: linkedin из анкеты видна себе")
                check(body["looking_for"] == "ищу партнёров",
                      "/api/me: looking_for = profiles.request (\"что актуально\") из анкеты")
                check(body["cv_text"] is None and body["website"] is None and body["offering"] is None,
                      "/api/me: новые поля (cv/сайт/офферы) пока не заполнены -> None")

                # POST /api/profile — редактирование НОВЫХ полей (в отличие от
                # полей анкеты, для них это единственный способ заполнения)
                resp = await client.post("/api/profile", headers=auth_100,
                                          json={"field": "unknown_field", "value": "x"})
                check(resp.status == 400, "POST /api/profile с неизвестным полем -> 400")

                resp = await client.post("/api/profile", headers=auth_100,
                                          json={"field": "cv_text", "value": "5 лет в iGaming"})
                check(resp.status == 200, "POST /api/profile cv_text -> 200")
                body = await resp.json()
                check(body["cv_text"] == "5 лет в iGaming", "/api/profile возвращает обновлённое значение")

                # Регрессия 12.09.2026 ("удалить фото" шлёт value:null):
                # str(body.get("value","")) превращал JSON null в строку
                # "None" вместо реальной очистки.
                resp = await client.post("/api/profile", headers=auth_100,
                                          json={"field": "cv_text", "value": None})
                check(resp.status == 200, "POST /api/profile field=None -> 200")
                body = await resp.json()
                check(body["cv_text"] is None,
                      f"value:null реально очищает поле, а не пишет строку 'None': {body['cv_text']!r}")
                # Восстанавливаем — более поздняя проверка "show_cv включён"
                # ожидает это же значение, тест иначе загрязняет своё же
                # состояние.
                await client.post("/api/profile", headers=auth_100,
                                   json={"field": "cv_text", "value": "5 лет в iGaming"})

                await client.post("/api/profile", headers=auth_100, json={"field": "website", "value": "init.dev"})
                await client.post("/api/profile", headers=auth_100,
                                   json={"field": "offering", "value": "консультации по трафику"})

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["cv_text"] is None, "заполненный cv_text всё равно скрыт, пока show_cv выключен")

                await client.post("/api/privacy", headers=auth_100, json={"field": "show_cv", "value": True})
                await client.post("/api/privacy", headers=auth_100, json={"field": "show_contacts", "value": True})
                await client.post("/api/privacy", headers=auth_100, json={"field": "show_offers", "value": True})
                await client.post("/api/privacy", headers=auth_100, json={"field": "show_profession", "value": True})

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["cv_text"] == "5 лет в iGaming", "show_cv включён -> cv_text виден в чужом поиске")
                check(body["website"] == "init.dev" and body["linkedin"] == "linkedin.com/in/init",
                      "show_contacts включён -> website И linkedin видны разом (одна пара)")
                check(body["looking_for"] == "ищу партнёров" and body["offering"] == "консультации по трафику",
                      "show_offers включён -> looking_for И offering видны разом (одна пара)")
                check(body["profession"] == "Manager", "show_profession включён -> профессия видна")

                # --- расширение "Моё CV" (12.08.2026) ---------------------------

                resp = await client.post("/api/cv/field", headers=auth_100,
                                          json={"field": "unknown_field", "value": "x"})
                check(resp.status == 400, "POST /api/cv/field с неизвестным полем -> 400")

                resp = await client.post("/api/cv/field", headers=auth_100,
                                          json={"field": "cv_skills", "value": "Python, SQL"})
                check(resp.status == 200, "POST /api/cv/field cv_skills -> 200")
                body = await resp.json()
                check(body["cv_skills"] == "Python, SQL", "/api/cv/field возвращает обновлённое значение")

                resp = await client.post("/api/cv/profession", headers=auth_100, json={"value": "Менеджер"})
                check(resp.status == 200, "POST /api/cv/profession первое заполнение -> 200")
                body = await resp.json()
                check(body["cv_profession"] == "Менеджер", "cv_profession сохранился")

                resp = await client.post("/api/cv/profession", headers=auth_100, json={"value": ""})
                check(resp.status == 400, "POST /api/cv/profession с пустым значением -> 400")

                resp = await client.post("/api/cv/profession", headers=auth_100, json={"value": "Директор"})
                check(resp.status == 200, "1-я реальная смена должности (из 2 разрешённых) -> 200")
                resp = await client.post("/api/cv/profession", headers=auth_100, json={"value": "C-Level"})
                check(resp.status == 200, "2-я реальная смена должности -> 200")
                resp = await client.post("/api/cv/profession", headers=auth_100, json={"value": "Ещё раз"})
                check(resp.status == 400, "3-я смена должности за год -> 400 CHANGE_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "CHANGE_LIMIT_REACHED", "тело ответа содержит CHANGE_LIMIT_REACHED")

                resp = await client.post("/api/cv/grade", headers=auth_100, json={"value": "Not A Grade"})
                check(resp.status == 400, "POST /api/cv/grade с невалидным значением -> 400 INVALID_GRADE")
                resp = await client.post("/api/cv/grade", headers=auth_100,
                                          json={"value": GC.CV_GRADE_LEVELS[2]})
                check(resp.status == 200, "POST /api/cv/grade из списка -> 200")
                body = await resp.json()
                check(body["cv_grade"] == GC.CV_GRADE_LEVELS[2], "cv_grade сохранился")

                resp = await client.post("/api/cv/flag", headers=auth_100,
                                          json={"field": "cv_relocation_ready", "value": True})
                check(resp.status == 200, "POST /api/cv/flag relocation=True -> 200")
                body = await resp.json()
                check(body["cv_relocation_ready"] is True, "cv_relocation_ready=True сохранился")
                resp = await client.post("/api/cv/flag", headers=auth_100,
                                          json={"field": "cv_relocation_ready", "value": None})
                body = await resp.json()
                check(body["cv_relocation_ready"] is None, "cv_relocation_ready можно вернуть в 'не указано' (None)")
                resp = await client.post("/api/cv/flag", headers=auth_100,
                                          json={"field": "cv_polygraph_consent", "value": False})
                body = await resp.json()
                check(body["cv_polygraph_consent"] is False, "cv_polygraph_consent=False сохранился")
                resp = await client.post("/api/cv/flag", headers=auth_100,
                                          json={"field": "not_a_flag", "value": True})
                check(resp.status == 400, "POST /api/cv/flag с неизвестным полем -> 400")

                resp = await client.post("/api/cv/salary", headers=auth_100,
                                          json={"salary_from": "2000", "salary_to": "3000", "negotiable": False})
                check(resp.status == 200, "POST /api/cv/salary -> 200")
                body = await resp.json()
                check(body["cv_salary_from"] == 2000.0 and body["cv_salary_to"] == 3000.0,
                      "вилка зарплаты сохранилась")
                check(body["cv_salary_negotiable"] is False, "negotiable=False сохранился")
                resp = await client.post("/api/cv/salary", headers=auth_100,
                                          json={"salary_from": None, "salary_to": None, "negotiable": True})
                body = await resp.json()
                check(body["cv_salary_from"] is None and body["cv_salary_negotiable"] is True,
                      "'по договорённости' можно выставить без чисел")

                resp = await client.post("/api/cv/experience", headers=auth_100,
                                          json={"company": "", "position": "PM"})
                check(resp.status == 400, "POST /api/cv/experience без company -> 400")

                resp = await client.post("/api/cv/experience", headers=auth_100, json={
                    "company": "GURO Co", "position": "Manager",
                    "date_from": "2020", "date_to": "2023", "location": "Odessa",
                    "description": "Управлял командой",
                })
                check(resp.status == 200, "POST /api/cv/experience валидная запись -> 200")
                body = await resp.json()
                exp_id = body["id"]
                check(body["company"] == "GURO Co" and body["position"] == "Manager",
                      "запись опыта содержит company/position")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(len(body["cv_experience"]) == 1, "/api/me: cv_experience содержит добавленную запись")
                check(body["cv_skills"] == "Python, SQL", "/api/me: cv_skills виден себе")
                check(body["cv_grade"] == GC.CV_GRADE_LEVELS[2], "/api/me: cv_grade виден себе")

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["cv_skills"] == "Python, SQL", "show_cv включён -> cv_skills виден в чужом поиске")
                check(len(body["cv_experience"]) == 1, "show_cv включён -> cv_experience виден в чужом поиске")

                await client.post("/api/privacy", headers=auth_100, json={"field": "show_cv", "value": False})
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["cv_skills"] is None, "show_cv выключен -> cv_skills скрыт в чужом поиске")
                check(body["cv_experience"] == [], "show_cv выключен -> cv_experience = [] (не null) в чужом поиске")

                # Привилегированные наблюдатели (12.08.2026) — GC.PRIVILEGED_VIEWER_IDS
                # видят карточку целиком, ДАЖЕ ПОКА show_cv/show_name у initiator
                # выключены (show_name тут ещё ни разу не включался). Бонус
                # обходит только тумблеры ЦЕЛИ — своя подписка запрашивающего
                # по-прежнему нужна для полной (не teaser) карточки, поэтому
                # активируем её тестовому привилегированному аккаунту, как это
                # будет и в проде ("подписка навсегда" тем же двум ID).
                app["storage"].activate_subscription(GC.PRIVILEGED_VIEWER_IDS[0], 30)
                auth_admin = {
                    "Authorization": "tma " + _guro_make_init_data(
                        token, {"id": GC.PRIVILEGED_VIEWER_IDS[0], "username": "priv_admin"},
                    )
                }
                resp = await client.get("/api/search?username=initiator", headers=auth_admin)
                check(resp.status == 200, "GET /api/search привилегированным -> 200")
                body = await resp.json()
                check(body["locked"] is False, "привилегированный + своя подписка -> полная карточка, не teaser")
                check(body["cv_skills"] == "Python, SQL",
                      "привилегированный видит cv_skills, ХОТЯ show_cv у initiator сейчас выключен")
                check(body["name"] == "Init",
                      "привилегированный видит имя, ХОТЯ show_name у initiator ещё ни разу не включался")
                check(body["company"] == "GURO Co",
                      "привилегированный видит company ('GURO Co'), ХОТЯ show_company у initiator тоже выключен")

                # непривилегированный (auth_200) в ЭТОТ ЖЕ момент по-прежнему не видит cv_skills —
                # бонус НЕ снимает приватность глобально, только для этих двух ID
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["cv_skills"] is None, "обычный запрашивающий по-прежнему не видит выключенный show_cv")

                await client.post("/api/privacy", headers=auth_100, json={"field": "show_cv", "value": True})

                resp = await client.post(f"/api/cv/experience/{exp_id}/delete", headers=auth_200)
                check(resp.status == 404, "DELETE чужой записи опыта -> 404 (не автор)")
                resp = await client.post(f"/api/cv/experience/{exp_id}/delete", headers=auth_100)
                check(resp.status == 200, "DELETE своей записи опыта -> 200")
                resp = await client.post(f"/api/cv/experience/{exp_id}/delete", headers=auth_100)
                check(resp.status == 404, "повторное удаление уже удалённой записи -> 404")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["cv_experience"] == [], "после удаления cv_experience снова пуст")

                # приватность: show_name opt-out (28.08.2026) — явно
                # включаем то, что и так уже включено по умолчанию, просто
                # проверяем, что тумблер реально работает в обе стороны.
                resp = await client.post("/api/privacy", headers=auth_100,
                                          json={"field": "show_name", "value": True})
                check(resp.status == 200, "POST /api/privacy -> 200")
                body = await resp.json()
                check(body["show_name"] is True, "/api/privacy возвращает обновлённое состояние")

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["name"] == "Init", "имя видно в ЧУЖОМ поиске (show_name=True, как и по умолчанию)")
                check(body["company"] == "GURO Co", "company тоже видна (opt-out по умолчанию, не трогали)")
                check(body["username"] == "initiator", "username всё равно виден (нужен для идентификации)")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["name"] == "Init", "в СВОЁМ профиле имя видно всегда, несмотря на тумблеры")
                check(body["privacy"]["show_name"] is True, "/api/me отдаёт текущее состояние тумблеров")

                resp = await client.post("/api/privacy", headers=auth_100,
                                          json={"field": "show_everything", "value": True})
                check(resp.status == 400, "POST /api/privacy с неизвестным полем -> 400")

                # включает ВСЕ тумблеры (динамически по GC.PRIVACY_FIELDS, чтобы
                # тест не протухал при добавлении новых разделов) -> видно всё
                for f in GC.PRIVACY_FIELDS:
                    await client.post("/api/privacy", headers=auth_100, json={"field": f, "value": True})
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["reputation_score"] is not None, "репутация видна в чужом поиске (тумблер на неё больше не влияет)")
                check(body["company"] == "GURO Co" and body["vertical"] == "iGaming", "company/vertical включены -> видны")
                check(body["joined_community_at"] is not None and body["days_in_community"] is not None,
                      "оба поля стажа видны (тумблер на них больше не влияет)")
                check(body["confirmed_partnerships"] == 0, "число партнёрств ВСЕГДА видно (не зависит от тумблеров)")
                check(isinstance(body.get("partners"), list), "список партнёров виден всегда")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["reputation_score"] is not None,
                      "приватность НЕ трогает свой /api/me — репутация видна себе независимо от тумблеров")
                check(all(body["privacy"].values()), "/api/me: все включённые тумблеры отражены в privacy")

                # «Рейтинг сгорает без подписки» — гейт РЕВЕРСИВНЫЙ: симулируем
                # истечение подписки initiator'а (без готового storage-метода
                # деактивации — правим строку напрямую, как и в других тестах
                # этого файла), проверяем скрытие ото ВСЕХ, потом реактивацию.
                import sqlite3 as _sq
                score_before_lapse = app["storage"].get_or_create_guro_user(100)["reputation_score"]
                _conn = _sq.connect(db_path)
                _conn.execute(
                    "UPDATE guro_users SET subscription_status='inactive', subscription_expires_at=NULL "
                    "WHERE user_id=100",
                )
                _conn.commit()
                _conn.close()

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["reputation_score"] is None,
                      "подписка истекла -> reputation_score скрыт ДАЖЕ себе")
                check(body["confirmed_partnerships"] is None,
                      "подписка истекла -> confirmed_partnerships тоже скрыт (не просто 0)")
                check(body["partners"] == [], "подписка истекла -> список партнёров пуст в выдаче")
                check(body.get("name") == "Init",
                      "подписка НЕ трогает остальные поля себя (имя и т.п. видны как обычно)")

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["reputation_score"] is None,
                      "подписка target'а истекла -> репутация скрыта и в ЧУЖОМ поиске (несмотря на show_reputation=True)")
                check(body["confirmed_partnerships"] is None,
                      "подписка target'а истекла -> confirmed_partnerships скрыт в чужом поиске")
                check(body["company"] == "GURO Co",
                      "гейт подписки НЕ трогает privacy-поля (company всё ещё видна через show_company)")

                # Привилегированные наблюдатели (12.08.2026, расширено по явной
                # просьбе "обойди и это тоже") — обходят и «рейтинг сгорает без
                # подписки» цели, не только тумблеры приватности. Собственная
                # подписка привилегированного аккаунта была активирована выше
                # (в блоке CV-расширения), поэтому locked=False.
                auth_admin_gate = {
                    "Authorization": "tma " + _guro_make_init_data(
                        token, {"id": GC.PRIVILEGED_VIEWER_IDS[0], "username": "priv_admin"},
                    )
                }
                resp = await client.get("/api/search?username=initiator", headers=auth_admin_gate)
                body = await resp.json()
                check(body["reputation_score"] == score_before_lapse,
                      "привилегированный видит рейтинг ЦЕЛИ, ХОТЯ у initiator подписка сейчас истекла")
                check(body["confirmed_partnerships"] is not None,
                      "привилегированный видит confirmed_partnerships ЦЕЛИ, ХОТЯ у initiator подписка сейчас истекла")
                check(isinstance(body["partners"], list),
                      "привилегированный видит список partners ЦЕЛИ, ХОТЯ у initiator подписка сейчас истекла")

                app["storage"].activate_subscription(100, 30)
                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["reputation_score"] == score_before_lapse,
                      "реактивация подписки -> СТАРОЕ значение репутации мгновенно вернулось, не с нуля заново "
                      "(гейт ничего не удалял из БД)")

                resp = await client.get("/api/me", headers=auth_200)
                check(resp.status == 200, "GET /api/me подписчика -> 200")
                check((555, 200, GC.GURO_TAG) in _FakeTGBot.set_tag_calls,
                      "GET /api/me с активной подпиской -> появляется тег GURO ID")

                resp = await client.get("/api/search?username=nobody", headers=auth_200)
                check(resp.status == 404, "поиск несуществующего юзернейма -> 404")

                # work_status: публичный статус трудоустройства — виден ВСЕМ
                # бесплатно (даже без подписки смотрящего), НЕ тумблер приватности
                resp = await client.post("/api/work_status", headers=auth_100, json={"status": "bogus"})
                check(resp.status == 400, "POST /api/work_status с неизвестным значением -> 400")

                resp = await client.post("/api/work_status", headers=auth_100, json={"status": "looking"})
                check(resp.status == 200, "POST /api/work_status валидное значение -> 200")
                body = await resp.json()
                check(body["work_status"] == "looking", "/api/work_status возвращает обновлённое значение")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["work_status"] == "looking", "/api/me отдаёт work_status себе")

                auth_300 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 300, "username": "outsider"})}
                resp = await client.get("/api/search?username=initiator", headers=auth_300)
                check(resp.status == 200, "поиск НЕподписанным -> 200 (locked-карточка)")
                body = await resp.json()
                check(body["locked"] is True, "user 300 без подписки -> locked=True")
                check(body["work_status"] == "looking",
                      "work_status виден ДАЖЕ в пейволленной locked-карточке — не платный контент")

                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["work_status"] == "looking", "work_status виден и в полной карточке подписчика")

                await client.post("/api/work_status", headers=auth_100, json={"status": None})
                resp = await client.get("/api/search?username=initiator", headers=auth_300)
                body = await resp.json()
                check(body["work_status"] is None, "status=null (\"выкл\") -> work_status пропадает даже у locked")

                # /api/qr — дипссылка на /start бота с payload guro_<user_id>
                resp = await client.get("/api/qr", headers=auth_100)
                check(resp.status == 200, "GET /api/qr -> 200")
                body = await resp.json()
                check(body["deeplink"] == f"https://t.me/{settings.bot_username}?start=guro_100",
                      f"/api/qr отдаёт корректную deep-link, получено: {body['deeplink']}")
                resp = await client.get("/api/qr")
                check(resp.status == 401, "GET /api/qr без Authorization -> 401")

                # 25.08.2026 (фидбек владельца, "Правки.pdf", раздел "Поиск"):
                # поиск по описанию убран из ЛИЧНОГО профиля — только точный
                # юзернейм. cryptomgr (user 400) заведён тут же — ещё нужен
                # ниже для теста browse по вертикали (см. "Фаза 2").
                st.save_profile({
                    "user_id": 400, "username": "cryptomgr", "name": "Crypto Manager",
                    "vertical": "Крипто", "profession": "Manager", "company": "Secret Co",
                    "request": "ищу инвесторов",
                })
                app["storage"].activate_subscription(400, 30)
                await client.post(
                    "/api/privacy",
                    headers={"Authorization": "tma " + _guro_make_init_data(token, {"id": 400, "username": "cryptomgr"})},
                    json={"field": "show_vertical", "value": True},
                )

                # УНИВЕРСАЛЬНЫЙ поиск (10.08.2026, сужен 25.08.2026): один
                # инпут ?q=, бэкенд ищет ТОЛЬКО точный юзернейм — не нашёл ->
                # NOT_FOUND, а не платный directory-поиск (тот убран из
                # личного профиля, `_directory_search` оставлена в коде для
                # будущих кабинетов Рекрутер/Компания, см. handle_search).
                resp = await client.get("/api/search?q=initiator", headers=auth_ghost)
                check(resp.status == 200,
                      "q= точно совпал с юзернеймом -> 200 БЕЗ подписки (это режим profile, не list)")
                body = await resp.json()
                check(body["mode"] == "profile", "q= с точным юзернеймом -> mode=profile")
                check(body["locked"] is True, "но карточка всё равно тизер, т.к. auth_ghost не подписан")

                resp = await client.get("/api/search?q=крипто", headers=auth_ghost)
                check(resp.status == 404,
                      "q= НЕ совпал ни с одним юзернеймом -> 404 (поиск по описанию убран из личного профиля)")

                # auth_200 (confirmer) уже подписан с самого начала теста (см. paywall-тест выше)
                resp = await client.get("/api/search?q=", headers=auth_200)
                check(resp.status == 200, "GET /api/search?q= (пусто) -> 200, просто пустой список")
                body = await resp.json()
                check(body["mode"] == "list" and body["results"] == [],
                      "пустой query -> mode=list с пустым results, не вся база")

                resp = await client.get("/api/search?q=крипто", headers=auth_200)
                check(resp.status == 404,
                      "q= без точного юзернейма -> 404 ДАЖЕ с подпиской смотрящего (не directory-режим больше)")

                resp = await client.get("/api/search?q=cryptomgr", headers=auth_200)
                body = await resp.json()
                check(body["mode"] == "profile" and body["user_id"] == 400,
                      "q= точно совпал с юзернеймом user 400 -> находит его (mode=profile)")

                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "nobody", "ptype": "deal"})
                check(resp.status == 404, "POST /api/partnerships неизвестному юзернейму -> 404")

                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "confirmer"})
                check(resp.status == 400, "POST /api/partnerships без ptype -> 400 INVALID_TYPE (6, п.1, обязательное поле)")

                # tx_hash/tx_network передаём ЯВНЫМ null — так их шлёт форма при
                # галочке «Без прямой оплаты» (06.09.2026, «компания.pdf», стр. 6).
                # Раньше тест ключи просто не передавал и потому не различал
                # «ключа нет» и «ключ со значением null» — а баг жил именно там:
                # str(None) давал строку "None", сервер считал её хешем и требовал
                # сеть, из-за чего безоплатная сделка не отправлялась вообще.
                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "confirmer", "vertical": "casino",
                                                "ptype": "deal", "tx_hash": None, "tx_network": None,
                                                "amount_received": None, "amount_paid": None})
                check(resp.status == 200, "POST /api/partnerships с явными null -> 200 (безоплатная сделка)")
                body = await resp.json()
                check(body["status"] == "pending", "созданное партнёрство в статусе pending")
                _row_np = _sq.connect(db_path).execute(
                    "SELECT tx_hash FROM partnerships WHERE id=?", (body["id"],)).fetchone()
                check(_row_np[0] is None,
                      'в базе NULL, а не строка "None" (так мусор попадал в боевые данные)')

                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "nobody", "ptype": "deal",
                                                "tx_hash": "None"})
                check(resp.status == 404,
                      'строка "None" в поле хеша не считается хешем (иначе -> 400 про сеть)')

                # 08.09.2026: на пару разрешено ТРИ заявки за скользящие сутки.
                # Первая была заведена выше по тесту, поэтому вторая и третья
                # обязаны пройти, а отказ приходит на четвёртой. Проверяем оба
                # края: одна лишь проверка отказа не поймала бы случайное
                # ужесточение ограничителя обратно до одной заявки.
                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "confirmer", "ptype": "deal"})
                check(resp.status == 200, "вторая заявка на ту же пару за сутки -> 200")
                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "confirmer", "ptype": "deal"})
                check(resp.status == 200, "третья заявка на ту же пару за сутки -> 200")
                resp = await client.post("/api/partnerships", headers=auth_100,
                                          json={"confirmer_username": "confirmer", "ptype": "deal"})
                check(resp.status == 409, "четвёртая заявка на ту же пару за сутки -> 409 (анти-фрод)")

                # --- Фаза 2 (11.08.2026): офер/суммы/отзыв в партнёрстве -------
                st.save_profile({"user_id": 450, "username": "dealmaker", "name": "Deal Maker"})
                st.save_profile({"user_id": 460, "username": "dealpartner", "name": "Deal Partner"})
                app["storage"].activate_subscription(450, 30)
                auth_450 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 450, "username": "dealmaker"})}

                resp = await client.post("/api/partnerships", headers=auth_450, json={
                    "confirmer_username": "dealpartner", "vertical": "iGaming", "geo": "Malta",
                    "offer": "Привёл байера на казино-трафик",
                    "amount_received": "1500", "amount_paid": "200.5",
                    # "review" (25.08.2026, фидбек владельца): свободный
                    # отзыв убран с этого шага (см. handle_create_partnership) —
                    # даже если фронт (или старый клиент) его пришлёт,
                    # бэкенд молча игнорирует, партнёрство хранит review=None.
                    "review": "Отличная сделка, всё чётко и в срок",
                    "amount_visible": True,
                    "tx_hash": "0xabc123def456", "ptype": "deal", "tx_network": "ethereum",
                })
                check(resp.status == 200, "POST /api/partnerships с офером/суммами/отзывом -> 200")
                body = await resp.json()
                app["storage"].respond_partnership(body["id"], responder_id=460, accept=True)

                resp = await client.get("/api/search?username=dealmaker", headers=auth_200)
                body = await resp.json()
                partner = next(p for p in body["partners"] if p["user_id"] == 460)
                check(partner["offer"] == "Привёл байера на казино-трафик",
                      "офер виден в чужом поиске (публичен всегда)")
                check(partner["review"] is None,
                      "отзыв больше НЕ собирается на этом шаге (25.08.2026) -> всегда None, даже если фронт его прислал")
                check(partner["amount_received"] == 1500.0, "сумма видна, т.к. amount_visible=True при создании")
                check(partner["amount_paid"] == 200.5, "вторая сумма тоже видна")
                check(partner["tx_hash"] == "0xabc123def456", "хэш транзакции виден вместе с суммой (16.08.2026)")
                check(partner["vertical"] == "iGaming" and partner["geo"] == "Malta",
                      "вертикаль/гео конкретного партнёрства видны")
                check(partner["initiator_id"] == 450, "видно, кто был инициатором (со слов кого офер/суммы)")

                st.save_profile({"user_id": 470, "username": "dealmaker2", "name": "Deal Maker 2"})
                app["storage"].activate_subscription(470, 30)
                auth_470 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 470, "username": "dealmaker2"})}
                resp = await client.post("/api/partnerships", headers=auth_470, json={
                    "confirmer_username": "dealpartner",
                    "offer": "Консультация по комплаенсу",
                    "amount_received": "500",
                    "review": "Норм",
                    "tx_hash": "should_stay_hidden", "ptype": "deal", "tx_network": "ethereum",
                })
                body = await resp.json()
                app["storage"].respond_partnership(body["id"], responder_id=460, accept=True)

                resp = await client.get("/api/search?username=dealmaker2", headers=auth_200)
                body = await resp.json()
                partner2 = next(p for p in body["partners"] if p["user_id"] == 460)
                check(partner2["offer"] == "Консультация по комплаенсу", "офер публичен и БЕЗ amount_visible")
                check(partner2["amount_received"] is None,
                      "amount_visible по умолчанию False -> сумма скрыта, несмотря на то что была указана")
                check(partner2["tx_hash"] is None,
                      "хэш транзакции тоже скрыт без amount_visible, несмотря на то что был указан")

                # --- «Анонимная сделка/найм» (11.09.2026) ----------------------
                st.save_profile({"user_id": 550, "username": "anonmaker", "name": "Anon Maker"})
                st.save_profile({"user_id": 560, "username": "anonpartner", "name": "Anon Partner"})
                app["storage"].activate_subscription(550, 30)
                app["storage"].activate_subscription(560, 30)
                auth_550 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 550, "username": "anonmaker"})}

                resp = await client.post("/api/partnerships", headers=auth_550, json={
                    "confirmer_username": "anonpartner", "offer": "Заметка для себя",
                    "amount_received": "300", "tx_hash": "0xanon111", "ptype": "deal",
                    "tx_network": "ethereum", "anonymous": True,
                })
                check(resp.status == 200, "анонимная сделка создаётся так же, как обычная -> 200")
                anon_id = (await resp.json())["id"]
                app["storage"].respond_partnership(anon_id, responder_id=560, accept=True)

                # третье лицо (auth_200, обычный подписанный смотрящий) —
                # видит СТРОКУ (счётчик не расходится со списком), но не
                # личность контрагента ни с одной из двух сторон.
                resp = await client.get("/api/search?username=anonmaker", headers=auth_200)
                body = await resp.json()
                anon_seen_from_maker = next(p for p in body["partners"] if p["id"] == anon_id)
                check(anon_seen_from_maker["name"] is None and anon_seen_from_maker["username"] is None,
                      "третьему лицу имя/юзернейм анонимного партнёра не видны")
                check(anon_seen_from_maker["user_id"] is None,
                      "user_id тоже обнулён — иначе обход через /api/search?user_id=<leaked>")
                check(anon_seen_from_maker["offer"] == "Заметка для себя",
                      "остальные детали (офер/сумма) анонимность не трогает — это отдельная ось (amount_visible)")

                resp = await client.get("/api/search?username=anonpartner", headers=auth_200)
                body = await resp.json()
                anon_seen_from_partner = next(p for p in body["partners"] if p["id"] == anon_id)
                check(anon_seen_from_partner["user_id"] is None,
                      "анонимность симметрична — со стороны confirmer'а личность initiator'а тоже скрыта")

                # сами участники видят друг друга полностью на СВОЁМ /api/me
                resp = await client.get("/api/me", headers=auth_550)
                body = await resp.json()
                own_view = next(p for p in body["partners"] if p["id"] == anon_id)
                check(own_view["username"] == "anonpartner" and own_view["user_id"] == 560,
                      "участник видит СВОЮ анонимную сделку полностью на собственном /api/me")

                # привилегированный смотрящий (админ) — тоже видит личность,
                # тот же обход, что у _apply_privacy/_apply_subscription_gate
                auth_admin = {"Authorization": "tma " + _guro_make_init_data(
                    token, {"id": GC.PRIVILEGED_VIEWER_IDS[0], "username": "owneracct"},
                )}
                resp = await client.get("/api/search?username=anonmaker", headers=auth_admin)
                body = await resp.json()
                admin_view = next(p for p in body["partners"] if p["id"] == anon_id)
                check(admin_view["user_id"] == 560 and admin_view["username"] == "anonpartner",
                      "привилегированный смотрящий видит настоящих участников даже анонимной сделки")

                # --- Фаза 2: browse по вертикали (альтернатива тексту поиска) ---
                st.save_profile({"user_id": 480, "username": "gambler1", "name": "Gambler One", "vertical": "Gambling"})
                st.save_profile({"user_id": 481, "username": "other1", "name": "Other One", "vertical": "Other: Web3 gaming"})
                st.save_profile({"user_id": 482, "username": "gambler2", "name": "Gambler Two", "vertical": "Gambling"})
                for uid, uname in ((480, "gambler1"), (481, "other1"), (482, "gambler2")):
                    app["storage"].activate_subscription(uid, 30)
                    auth_u = {"Authorization": "tma " + _guro_make_init_data(token, {"id": uid, "username": uname})}
                    await client.post("/api/privacy", headers=auth_u, json={"field": "show_vertical", "value": True})
                    await client.post("/api/privacy", headers=auth_u, json={"field": "show_reputation", "value": True})

                st.save_profile({"user_id": 490, "username": "nosub2", "name": "No Sub 2"})
                auth_490 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 490, "username": "nosub2"})}
                resp = await client.get("/api/search?vertical=Gambling", headers=auth_490)
                check(resp.status == 402, "browse по вертикали без подписки СМОТРЯЩЕГО -> 402")

                resp = await client.get("/api/search?vertical=Gambling", headers=auth_200)
                check(resp.status == 200, "browse по вертикали с подпиской -> 200")
                body = await resp.json()
                check(body["mode"] == "list", "browse по вертикали -> mode=list")
                ids = [r["user_id"] for r in body["results"]]
                check(480 in ids and 482 in ids, "browse находит обоих gambler1/gambler2 по вертикали Gambling")
                check(400 not in ids,
                      "browse НЕ путает с cryptomgr (у него вертикаль 'Крипто', это другое значение)")

                resp = await client.get("/api/search?vertical=Other", headers=auth_200)
                body = await resp.json()
                ids2 = [r["user_id"] for r in body["results"]]
                check(481 in ids2, "browse по 'Other' находит произвольные 'Other: <текст>' через startswith")

                # ТОП рейтинга (top=1) — искусственно поднимаем репутацию gambler2
                _conn3 = _sq.connect(db_path)
                _conn3.execute("UPDATE guro_users SET reputation_score=90 WHERE user_id=482")
                _conn3.commit()
                _conn3.close()

                resp = await client.get("/api/search?vertical=Gambling&top=1", headers=auth_200)
                body = await resp.json()
                top_ids = [r["user_id"] for r in body["results"]]
                check(top_ids.index(482) < top_ids.index(480),
                      "top=1 -> сортировка по репутации (gambler2=90 выше gambler1=0), а не по порядку совпадения")

                # --- Фаза 2: «Пригласить коллегу» — персональная реф-ссылка -----
                resp = await client.get("/api/invite_link", headers=auth_100)
                check(resp.status == 200, "GET /api/invite_link -> 200")
                body = await resp.json()
                check(body["link"].startswith(f"https://t.me/{settings.bot_username}?start=ref_100_"),
                      f"инвайт-ссылка в формате реф-системы, получено: {body['link']}")
                resp = await client.get("/api/invite_link")
                check(resp.status == 401, "GET /api/invite_link без Authorization -> 401")

                resp = await client.get("/api/plans")
                check(resp.status == 200, "GET /api/plans -> 200 (публичный эндпойнт, без авторизации)")
                body = await resp.json()
                check(set(body["plans"].keys()) == {"monthly", "yearly"}, "/api/plans содержит оба тарифа")
                check(body["plans"]["monthly"]["stars_price"] == 400, "месячный тариф = 400 звёзд (~$6, ТЗ 'Тарифы и лимиты')")
                check(body["plans"]["yearly"]["stars_price"] == 3350, "годовой тариф = 3350 звёзд (~$50)")
                check(body["plans"]["yearly"]["stars_price_full"] == 4800,
                      "у годового тарифа есть 'полная' цена для скидочной плашки (400*12)")
                check(body["plans"]["yearly"]["crypto_price_usd"] == round(3350 * GC.STARS_TO_USD_RATE, 2),
                      "крипто-цена годового тарифа считается по STARS_TO_USD_RATE")
                check(body["crypto_enabled"] is False, "crypto_enabled=False, пока не задан CRYPTOBOT_API_TOKEN")

                resp = await client.post("/api/subscribe", headers=auth_100, json={})
                check(resp.status == 400, "POST /api/subscribe без плана -> 400 UNKNOWN_PLAN")

                resp = await client.post("/api/subscribe", headers=auth_100, json={"plan": "nonsense"})
                check(resp.status == 400, "POST /api/subscribe с несуществующим планом -> 400")

                resp = await client.post("/api/subscribe", headers=auth_100, json={"plan": "yearly"})
                check(resp.status == 200, "POST /api/subscribe с валидным планом -> 200")
                body = await resp.json()
                check(body["invoice_link"] == "https://t.me/fake_invoice_link", "/api/subscribe отдаёт invoice_link")

                # крипто-оплата выключена (в этой Settings нет токена) -> 503
                resp = await client.post("/api/subscribe/crypto", headers=auth_100, json={"plan": "monthly"})
                check(resp.status == 503, "POST /api/subscribe/crypto без CRYPTOBOT_API_TOKEN -> 503")

                # включаем крипту и мокаем сам вызов CryptoBot (реальный API не дёргаем)
                app["settings"].cryptobot_api_token = "fake-crypto-token"

                async def _fake_create_invoice(api_token, **kw):
                    return {"invoice_id": 42, "pay_url": "https://t.me/CryptoBot?start=fakeinv"}

                with mock.patch.object(guro_id_api.GCR, "create_invoice", _fake_create_invoice):
                    resp = await client.post("/api/subscribe/crypto", headers=auth_100, json={"plan": "yearly"})
                    check(resp.status == 200, "POST /api/subscribe/crypto с токеном -> 200")
                    body = await resp.json()
                    check(body["pay_url"] == "https://t.me/CryptoBot?start=fakeinv", "/api/subscribe/crypto отдаёт pay_url")

                resp = await client.get("/api/plans")
                body = await resp.json()
                check(body["crypto_enabled"] is True, "crypto_enabled=True после появления токена")

                # вебхук CryptoBot: неверная подпись -> 403, подписку не активирует
                import hashlib
                import hmac
                import json as _json
                from datetime import datetime as _dt, timezone as _tz

                webhook_body = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_subscription:yearly:300"},
                }).encode()
                resp = await client.post("/api/crypto/webhook", data=webhook_body,
                                          headers={"crypto-pay-api-signature": "wrong"})
                check(resp.status == 403, "crypto webhook с неверной подписью -> 403")
                check(not app["storage"].is_subscribed(300), "неверная подпись -> подписка НЕ активирована")

                secret = hashlib.sha256(b"fake-crypto-token").digest()
                good_sig = hmac.new(secret, webhook_body, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body,
                                          headers={"crypto-pay-api-signature": good_sig})
                check(resp.status == 200, "crypto webhook с верной подписью -> 200")
                check(app["storage"].is_subscribed(300), "верная подпись -> подписка активирована")
                _status, _expires = app["storage"].get_subscription(300)
                _days_left = (_expires - _dt.now(_tz.utc)).days
                check(_days_left > 300, "crypto webhook с планом yearly -> подписка на ~365 дней")

                resp = await client.post("/api/crypto/webhook", data=b'{"update_type": "other"}',
                                          headers={"crypto-pay-api-signature":
                                                    hmac.new(secret, b'{"update_type": "other"}', hashlib.sha256).hexdigest()})
                check(resp.status == 200, "crypto webhook с чужим update_type -> 200, но без побочных эффектов")

                # --- 29.08.2026: два токена CryptoBot, кольцо 5:1 -----------------
                # (владелец: "прикрутить новый ключ, 5 платежей на него и 1 на
                # старый, по кругу") — старый токен уже "fake-crypto-token" (см.
                # выше), добавляем второй и проверяем сам паттерн распределения,
                # персистентность позиции кольца через "рестарт" (новый объект
                # GuroStorage на тот же файл) и проверку подписи вебхука ОБОИМИ
                # токенами.
                from guro_storage import GuroStorage as _GuroStorage

                app["settings"].cryptobot_api_token_new = "fake-crypto-token-new"
                app["storage"].set_config(GC.CRYPTO_TOKEN_CYCLE_KEY, 0)  # детерминированный старт кольца

                used_tokens = []

                async def _fake_create_invoice_multi(api_token, **kw):
                    used_tokens.append(api_token)
                    return {"invoice_id": 43, "pay_url": "https://t.me/CryptoBot?start=fakeinv2"}

                with mock.patch.object(guro_id_api.GCR, "create_invoice", _fake_create_invoice_multi):
                    for _ in range(7):
                        resp = await client.post("/api/subscribe/crypto", headers=auth_100, json={"plan": "monthly"})
                        check(resp.status == 200, "POST /api/subscribe/crypto (кольцо 5:1) -> 200")

                check(used_tokens == ["fake-crypto-token-new"] * 5 + ["fake-crypto-token"] + ["fake-crypto-token-new"],
                      "кольцо 5:1 — 5 инвойсов новому токену, 1 старому, затем снова новому (7 звонков подряд)")

                # "рестарт процесса" — новый объект GuroStorage на тот же файл,
                # позиция кольца должна пережить его (не сброситься в 0).
                _restarted_storage = _GuroStorage(app["settings"].database_path)
                check(_restarted_storage.get_config(GC.CRYPTO_TOKEN_CYCLE_KEY, -1) == 1,
                      "позиция кольца переживает рестарт процесса (после 7 вызовов ожидаем позицию 1 из 6)")

                # вебхук: подпись СТАРЫМ токеном по-прежнему проходит, даже когда
                # настроен ещё и новый (заранее не известно, каким токеном создан
                # именно этот инвойс — см. handle_crypto_webhook).
                webhook_body_old = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_subscription:monthly:301"},
                }).encode()
                sig_old = hmac.new(secret, webhook_body_old, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body_old,
                                          headers={"crypto-pay-api-signature": sig_old})
                check(resp.status == 200, "webhook подписанный СТАРЫМ токеном проходит и при настроенном новом")
                check(app["storage"].is_subscribed(301), "подписка активирована по вебхуку со старым токеном")

                # и подпись НОВЫМ токеном тоже проходит.
                secret_new = hashlib.sha256(b"fake-crypto-token-new").digest()
                webhook_body_new = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_subscription:monthly:302"},
                }).encode()
                sig_new = hmac.new(secret_new, webhook_body_new, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body_new,
                                          headers={"crypto-pay-api-signature": sig_new})
                check(resp.status == 200, "webhook подписанный НОВЫМ токеном тоже проходит")
                check(app["storage"].is_subscribed(302), "подписка активирована по вебхуку с новым токеном")

                # 29.08.2026 (владелец: "платёж на старый кошелёк — моя личная
                # доля, в статистике участвовать не должна") — 301 (старый
                # токен) подписан ПОЛНОЦЕННО (см. is_subscribed выше), но не
                # должен попадать в dashboard_stats().active_subscriptions;
                # 302 (новый токен) — обычная запись, считается как всегда.
                _row301 = _sq.connect(db_path).execute(
                    "SELECT subscription_personal_cut FROM guro_users WHERE user_id=301").fetchone()
                check(_row301[0] == 1, "user_id=301 (старый токен) помечен subscription_personal_cut=1")
                _row302 = _sq.connect(db_path).execute(
                    "SELECT subscription_personal_cut FROM guro_users WHERE user_id=302").fetchone()
                check(_row302[0] == 0, "user_id=302 (новый токен) НЕ помечен personal_cut")

                _stats_before = app["storage"].dashboard_stats()
                # переактивируем 301 через Stars (personal_cut=False по
                # умолчанию) — обычная оплата ДОЛЖНА снять флаг и снова
                # попасть в статистику (флаг отражает ТЕКУЩИЙ цикл, не
                # унаследованное значение).
                app["storage"].activate_subscription(301, 30)
                _stats_after = app["storage"].dashboard_stats()
                check(_stats_after["active_subscriptions_guro_id"] == _stats_before["active_subscriptions_guro_id"] + 1,
                      "обычная реактивация (Stars, без personal_cut) СНИМАЕТ флаг — 301 снова в статистике")
                _row301b = _sq.connect(db_path).execute(
                    "SELECT subscription_personal_cut FROM guro_users WHERE user_id=301").fetchone()
                check(_row301b[0] == 0, "флаг personal_cut сброшен после обычной реактивации")

                # --- Фаза 3 (12.08.2026): кабинет рекрутера ---------------------
                resp = await client.get("/api/me?workspace=recruiter", headers=auth_100)
                check(resp.status == 200, "GET /api/me?workspace=recruiter -> 200 (не требует своей анкеты)")
                body = await resp.json()
                check(body["is_recruiter_subscribed"] is False, "свежий кабинет рекрутера -> подписки ещё нет")
                check(body["name"] is None, "поля витрины рекрутера пока не заполнены")
                check(body["privacy"] == {f: True for f in GC.PRIVACY_FIELDS},
                      "приватность рекрутера теперь opt-out (06.09.2026): витрина видна сразу, "
                      "иначе оплаченный кабинет не находится в поиске")

                # Главный экран кабинета "Рекрутер" (26.08.2026, ТЗ "Гуро
                # рекрутер каб") — панель "Характеристика"/статус/процентиль.
                check(body["successful_hires"] == 0, "успешных наймов пока 0")
                check(body["active_vacancies"] == 0, "активных вакансий пока 0")
                check(body["responses_7d"] == 0, "откликов за 7 дней -> 0 (заглушка, механики ещё нет)")
                check(body["tenure_days"] is None, "стаж в роли -> None, подписка ещё не оформлена")
                check(body["activity_status"] is None, "статус активности по умолчанию не задан")
                check(body["percentile_tier"] is None, "кэш процентиля пуст до первого прогона джоба")

                resp = await client.post("/api/recruiter/activity_status", headers=auth_100,
                                          json={"status": "garbage"})
                check(resp.status == 400, "POST /api/recruiter/activity_status с мусором -> 400")
                resp = await client.post("/api/recruiter/activity_status", headers=auth_100,
                                          json={"status": "hiring"})
                check(resp.status == 200, "POST /api/recruiter/activity_status hiring -> 200")
                body = await resp.json()
                check(body["activity_status"] == "hiring", "статус активности сохранён")

                resp = await client.post("/api/recruiter/profile", headers=auth_100,
                                          json={"field": "unknown_field", "value": "x"})
                check(resp.status == 400, "POST /api/recruiter/profile с неизвестным полем -> 400")

                resp = await client.post("/api/recruiter/profile", headers=auth_100,
                                          json={"field": "name", "value": "Init HR"})
                check(resp.status == 200, "POST /api/recruiter/profile name -> 200")
                body = await resp.json()
                check(body["name"] == "Init HR", "/api/recruiter/profile возвращает обновлённое значение")

                # Регрессия 12.09.2026 ("удалить фото" шлёт value:null) —
                # см. комментарий у аналогичной проверки /api/profile выше.
                resp = await client.post("/api/recruiter/profile", headers=auth_100,
                                          json={"field": "logo_url", "value": None})
                check(resp.status == 200, "POST /api/recruiter/profile logo_url=None -> 200")
                body = await resp.json()
                check(body["logo_url"] is None,
                      f"value:null реально очищает логотип, а не пишет строку 'None': {body['logo_url']!r}")

                await client.post("/api/recruiter/profile", headers=auth_100,
                                   json={"field": "company", "value": "GURO Recruiting"})

                resp = await client.post("/api/recruiter/privacy", headers=auth_100,
                                          json={"field": "unknown_field", "value": True})
                check(resp.status == 400, "POST /api/recruiter/privacy с неизвестным полем -> 400")

                resp = await client.post("/api/recruiter/privacy", headers=auth_100,
                                          json={"field": "show_name", "value": True})
                check(resp.status == 200, "POST /api/recruiter/privacy show_name -> 200")

                resp = await client.get("/api/search?workspace=recruiter&username=nobody", headers=auth_200)
                check(resp.status == 404, "recruiter-просмотр несуществующего юзернейма -> 404 NOT_FOUND")

                # чужой просмотр кабинета БЕЗ активной подписки РЕКРУТЕРА у цели ->
                # витрина формально не существует, даже если поля уже заполнены
                resp = await client.get("/api/search?workspace=recruiter&username=initiator", headers=auth_200)
                check(resp.status == 404, "чужой просмотр recruiter-кабинета без подписки рекрутера у цели -> 404")
                body = await resp.json()
                check(body["error"] == "NO_RECRUITER_PROFILE", "тело содержит понятный код ошибки")

                app["storage"].activate_recruiter_subscription(100, 30)

                resp = await client.get("/api/search?workspace=recruiter&username=initiator", headers=auth_200)
                check(resp.status == 200, "чужой просмотр recruiter-кабинета С активной подпиской рекрутера -> 200")
                body = await resp.json()
                check(body["locked"] is False, "auth_200 подписан на базовый GURO ID -> карточка разблокирована")
                check(body["name"] == "Init HR", "show_name включён -> имя рекрутера видно")
                check(body["company"] == "GURO Recruiting",
                      "show_company включён по умолчанию -> company виден (opt-out, 06.09.2026)")
                # Механизм приватности должен работать и в обратную сторону:
                # выключенный вручную тумблер обязан скрывать поле.
                app["storage"].set_recruiter_privacy_field(100, "show_company", False)
                resp = await client.get("/api/search?workspace=recruiter&username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["company"] is None,
                      "выключенный вручную show_company -> company снова скрыт")
                app["storage"].set_recruiter_privacy_field(100, "show_company", True)

                st.save_profile({"user_id": 495, "username": "nosub3", "name": "No Sub 3"})
                auth_495 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 495, "username": "nosub3"})}
                resp = await client.get("/api/search?workspace=recruiter&username=initiator", headers=auth_495)
                check(resp.status == 200, "recruiter-кабинет виден даже без подписки СМОТРЯЩЕГО, но как тизер")
                body = await resp.json()
                check(body["locked"] is True, "495 без базовой подписки -> locked=True и для recruiter-карточки")

                # тарифы/подписка/крипто-вебхук кабинета рекрутера — та же цепочка,
                # что у базового тарифа, через product=recruiter
                resp = await client.get("/api/plans?product=recruiter")
                check(resp.status == 200, "GET /api/plans?product=recruiter -> 200")
                body = await resp.json()
                check(body["plans"]["monthly"]["stars_price"] == 1250, "кабинет рекрутера: месяц = 1250⭐ (~$19, ТЗ 'Тарифы и лимиты')")
                check(body["plans"]["yearly"]["stars_price"] == 11350, "кабинет рекрутера: год = 11350⭐ (~$170)")
                check(body["plans"]["yearly"]["stars_price_full"] == 15000,
                      "кабинет рекрутера: 'полная' цена года = 1250*12, для скидочной плашки")

                resp = await client.post("/api/subscribe", headers=auth_100,
                                          json={"product": "recruiter", "plan": "monthly"})
                check(resp.status == 200, "POST /api/subscribe product=recruiter -> 200")
                body = await resp.json()
                check(body["invoice_link"] == "https://t.me/fake_invoice_link",
                      "recruiter subscribe тоже отдаёт invoice_link (общая платёжная цепочка)")

                resp = await client.post("/api/subscribe", headers=auth_100,
                                          json={"product": "unknown", "plan": "monthly"})
                check(resp.status == 400, "POST /api/subscribe с неизвестным product -> 400")

                webhook_body_r = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_recruiter_subscription:yearly:355"},
                }).encode()
                good_sig_r = hmac.new(secret, webhook_body_r, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body_r,
                                          headers={"crypto-pay-api-signature": good_sig_r})
                check(resp.status == 200, "crypto webhook recruiter с верной подписью -> 200")
                check(app["storage"].is_recruiter_subscribed(355),
                      "crypto webhook recruiter -> подписка рекрутера активирована")
                check(not app["storage"].is_subscribed(355),
                      "crypto webhook recruiter НЕ активирует базовую GURO ID подписку (разные продукты)")

                # --- Фаза 5 (17.08.2026): кабинет "Компания" ---------------------
                # Зеркало кабинета рекрутера выше — третий воркспейс поверх
                # личного профиля, бренд-страница работодателя отдельно от
                # конкретного рекрутера внутри неё (см. AskUserQuestion от
                # 16.08.2026: "Компания — бренд-страница, Рекрутер — человек
                # внутри неё"). Своя подписка; с 27.08.2026 (ТЗ "Тарифы и
                # лимиты") — два тира Basic/Pro вместо единой цены рекрутера.
                resp = await client.get("/api/me?workspace=company", headers=auth_100)
                check(resp.status == 200, "GET /api/me?workspace=company -> 200 (не требует своей анкеты)")
                body = await resp.json()
                check(body["no_company"] is True,
                      "свежий юзер (27.08.2026, ТЗ 'Роли и команда') — не Владелец и не Админ ни в одной компании")
                check(body["is_company_subscribed"] is False, "no_company -> подписки нет")

                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "name", "value": "x"})
                check(resp.status == 403, "правка витрины компании без членства -> 403 NOT_A_COMPANY_MEMBER")

                resp = await client.post("/api/company/create", headers=auth_100, json={"name": ""})
                check(resp.status == 400, "POST /api/company/create без названия -> 400 NAME_REQUIRED")

                resp = await client.post("/api/company/create", headers=auth_100, json={"name": "GURO Casino Ltd"})
                check(resp.status == 200, "POST /api/company/create -> 200")
                body = await resp.json()
                check(body["name"] == "GURO Casino Ltd", "имя сохранено при создании")
                check(body["my_role"] == "owner", "основатель сразу становится Владельцем")
                check(body["company_id"] == 100, "company_id — user_id основателя, стабильный идентификатор компании")
                check(body["member_count"] == 1 and body["member_limit"] == 5,
                      "1 участник (сам Владелец), лимит Basic по умолчанию = 5 (раздел 3.4 ТЗ)")

                resp = await client.post("/api/company/create", headers=auth_100, json={"name": "Ещё одна"})
                check(resp.status == 409, "повторное создание компании тем же юзером -> 409 ALREADY_IN_COMPANY")

                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "unknown_field", "value": "x"})
                check(resp.status == 400, "POST /api/company/profile с неизвестным полем -> 400")

                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "vertical", "value": "iGaming"})
                check(resp.status == 200, "POST /api/company/profile vertical (теперь есть членство) -> 200")

                # Регрессия 12.09.2026 ("удалить обложку/логотип" шлёт
                # value:null) — см. комментарий у /api/profile выше.
                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "cover_url", "value": None})
                check(resp.status == 200, "POST /api/company/profile cover_url=None -> 200")
                body = await resp.json()
                check(body["cover_url"] is None,
                      f"value:null реально очищает обложку, а не пишет строку 'None': {body['cover_url']!r}")

                resp = await client.post("/api/company/privacy", headers=auth_100,
                                          json={"field": "unknown_field", "value": True})
                check(resp.status == 400, "POST /api/company/privacy с неизвестным полем -> 400")

                resp = await client.post("/api/company/privacy", headers=auth_100,
                                          json={"field": "show_name", "value": True})
                check(resp.status == 200, "POST /api/company/privacy show_name -> 200")

                resp = await client.get("/api/search?workspace=company&username=nobody", headers=auth_200)
                check(resp.status == 404, "company-просмотр несуществующего юзернейма -> 404 NOT_FOUND")

                resp = await client.get("/api/search?workspace=company&username=initiator", headers=auth_200)
                check(resp.status == 404, "чужой просмотр company-кабинета без подписки компании у цели -> 404")
                body = await resp.json()
                check(body["error"] == "NO_COMPANY_PROFILE", "тело содержит понятный код ошибки")

                app["storage"].activate_company_subscription(100, 30)

                resp = await client.get("/api/search?workspace=company&username=initiator", headers=auth_200)
                check(resp.status == 200, "чужой просмотр company-кабинета С активной подпиской компании -> 200")
                body = await resp.json()
                check(body["locked"] is False, "auth_200 подписан на базовый GURO ID -> карточка разблокирована")
                check(body["name"] == "GURO Casino Ltd", "show_name включён -> имя компании видно")
                check(body["vertical"] == "iGaming",
                      "show_vertical включён по умолчанию -> vertical виден (opt-out, 06.09.2026)")
                # Обратная сторона: выключенный вручную тумблер обязан
                # скрывать поле, иначе приватность сломана незаметно.
                app["storage"].set_company_privacy_field(100, "show_vertical", False)
                resp = await client.get("/api/search?workspace=company&username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["vertical"] is None,
                      "выключенный вручную show_vertical -> vertical снова скрыт")
                app["storage"].set_company_privacy_field(100, "show_vertical", True)
                check(body["can_join"] is True, "auth_200 не состоит ни в одной компании -> может подать заявку")
                check(body["is_member"] is False, "auth_200 не участник ЭТОЙ компании")

                resp = await client.get("/api/search?workspace=company&username=initiator", headers=auth_495)
                check(resp.status == 200, "company-кабинет виден даже без подписки СМОТРЯЩЕГО, но как тизер")
                body = await resp.json()
                check(body["locked"] is True, "495 без базовой подписки -> locked=True и для company-карточки")

                # тарифы/подписка/крипто-вебхук кабинета компании — 27.08.2026
                # (ТЗ "Тарифы и лимиты"): ТЕПЕРЬ два отдельных product/тира
                # вместо одного (были 800⭐/7000⭐ на оба).
                resp = await client.get("/api/plans?product=company_basic")
                check(resp.status == 200, "GET /api/plans?product=company_basic -> 200")
                body = await resp.json()
                check(body["plans"]["monthly"]["stars_price"] == 3250, "компания Basic: месяц = 3250⭐ (~$49)")
                check(body["plans"]["yearly"]["stars_price"] == 28000, "компания Basic: год = 28000⭐ (~$420)")
                check(body["plans"]["yearly"]["stars_price_full"] == 39000,
                      "компания Basic: 'полная' цена года = 3250*12, для скидочной плашки")

                resp = await client.get("/api/plans?product=company_pro")
                check(resp.status == 200, "GET /api/plans?product=company_pro -> 200")
                body = await resp.json()
                check(body["plans"]["monthly"]["stars_price"] == 6600, "компания Pro: месяц = 6600⭐ (~$99)")
                check(body["plans"]["yearly"]["stars_price"] == 56650, "компания Pro: год = 56650⭐ (~$850)")
                check(body["plans"]["yearly"]["stars_price_full"] == 79200,
                      "компания Pro: 'полная' цена года = 6600*12, для скидочной плашки")

                resp = await client.post("/api/subscribe", headers=auth_100,
                                          json={"product": "company_basic", "plan": "monthly"})
                check(resp.status == 200, "POST /api/subscribe product=company_basic -> 200")
                body = await resp.json()
                check(body["invoice_link"] == "https://t.me/fake_invoice_link",
                      "company_basic subscribe тоже отдаёт invoice_link (общая платёжная цепочка)")

                resp = await client.post("/api/subscribe", headers=auth_100,
                                          json={"product": "company_pro", "plan": "monthly"})
                check(resp.status == 200, "POST /api/subscribe product=company_pro -> 200")

                webhook_body_c = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_company_basic_subscription:yearly:356"},
                }).encode()
                good_sig_c = hmac.new(secret, webhook_body_c, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body_c,
                                          headers={"crypto-pay-api-signature": good_sig_c})
                check(resp.status == 200, "crypto webhook company_basic с верной подписью -> 200")
                check(app["storage"].is_company_subscribed(356),
                      "crypto webhook company_basic -> подписка компании активирована")
                check(not app["storage"].is_subscribed(356),
                      "crypto webhook company НЕ активирует базовую GURO ID подписку (разные продукты)")
                check(app["storage"].get_company_tier(356) == "basic",
                      "crypto webhook company_basic проставляет company_tier='basic'")

                webhook_body_c2 = _json.dumps({
                    "update_type": "invoice_paid",
                    "payload": {"payload": "guro_id_company_pro_subscription:yearly:357"},
                }).encode()
                good_sig_c2 = hmac.new(secret, webhook_body_c2, hashlib.sha256).hexdigest()
                resp = await client.post("/api/crypto/webhook", data=webhook_body_c2,
                                          headers={"crypto-pay-api-signature": good_sig_c2})
                check(resp.status == 200, "crypto webhook company_pro с верной подписью -> 200")
                check(app["storage"].get_company_tier(357) == "pro",
                      "crypto webhook company_pro проставляет company_tier='pro'")

                # has_recruiter_profile/has_company_profile на личном профиле
                # (флаги для кнопок "Посмотреть как рекрутера/компанию" в
                # поиске — has_recruiter_profile был найден НЕ РЕАЛИЗОВАННЫМ
                # при работе над этой фичей, починен заодно)
                resp = await client.get("/api/search?username=initiator", headers=auth_200)
                check(resp.status == 200, "личный просмотр initiator после активации обоих доп.кабинетов -> 200")
                body = await resp.json()
                check(body["has_recruiter_profile"] is True,
                      "has_recruiter_profile=True после activate_recruiter_subscription (был не реализован, починен)")
                check(body["has_company_profile"] is True,
                      "has_company_profile=True после activate_company_subscription")

                # --- Фаза 4 (12.08.2026, переписано 26.08.2026 под новую схему
                # вакансий из ТЗ "Recruitment — ВАКАНСИИ") -----------------------
                # auth_100 публикует НЕСКОЛЬКО вакансий подряд в этом тестовом
                # блоке (проверяются разные аспекты доски/CRUD) — оверрайд
                # дневного лимита новых публикаций (раздел 2.3 ТЗ "Тарифы и
                # лимиты", по умолчанию 3/день), чтобы не смешивать это с
                # целевыми тестами лимитов ниже (см. "Фаза 5"). Заодно первая
                # проверка самого механизма оверрайда на живом аккаунте.
                app["storage"].set_user_limit_override(100, GC.LIMIT_KEY_NEW_VACANCIES, 100)

                resp = await client.get("/api/positions", headers=auth_200)
                check(resp.status == 200, "GET /api/positions -> 200")
                body = await resp.json()
                check(body["grades"] == list(GC.VACANCY_GRADES), "справочник грейдов совпадает с константой")
                check("Gambling" in body["professions"] and "Senior" in body["professions"]["Gambling"],
                      "справочник должностей отдаёт structure вертикаль -> грейд -> должности (из professions_data.py)")

                resp = await client.post("/api/vacancies", headers=auth_200, json={"title": "PM"})
                check(resp.status == 402,
                      "POST /api/vacancies без подписки Рекрутер/Компания (даже с базовой) -> 402")
                body = await resp.json()
                check(body["error"] == "RECRUITER_SUBSCRIPTION_REQUIRED", "тело содержит понятный код ошибки")

                resp = await client.post("/api/vacancies", headers=auth_100, json={"title": "   "})
                check(resp.status == 400, "POST /api/vacancies с пустым (после strip) заголовком -> 400")

                # auth_100 (initiator) уже подписан на кабинет рекрутера и заполнил
                # company="GURO Recruiting" в предыдущем блоке тестов (Фаза 3)
                resp = await client.post("/api/vacancies", headers=auth_100, json={
                    "title": "Senior Product Manager", "vertical": "Gambling", "grade": "Senior",
                    "position": "Senior Media Buyer (Facebook/Meta)",
                    "location": "Malta", "work_format": "remote", "employment_type": "full",
                    "salary_from": "3000", "salary_to": "5000", "salary_negotiable": False,
                    "salary_visible": True, "contact_method": "guro_id",
                    "description": "Ищем продакта в казино-направление", "lang": "ru",
                })
                check(resp.status == 200, "POST /api/vacancies валидный запрос (recruiter подписан) -> 200")
                body = await resp.json()
                vacancy_ru_id = body["id"]
                check(body["company"] == "GURO Recruiting",
                      "company подтягивается из кабинета рекрутера автора, не хранится в самой вакансии")
                check(body["status"] == "active", "новая вакансия сразу активна")
                check(body["grade"] == "Senior" and body["work_format"] == "remote"
                      and body["employment_type"] == "full", "структурные поля грейд/формат/занятость сохранены")
                check(body["salary_from"] == 3000 and body["salary_to"] == 5000,
                      "зарплата видна автору (salary_visible=True)")
                check(body["duration_days"] == GC.VACANCY_DURATION_DEFAULT and body["expires_at"],
                      "duration_days по умолчанию (не передан) и expires_at посчитан")
                check(body["is_owner"] is True and body["views_count"] == 0,
                      "владельческие поля видны автору сразу после создания")

                resp = await client.post("/api/vacancies", headers=auth_100, json={
                    "title": "Head of Marketing", "vertical": "Crypto", "lang": "en",
                    "duration_days": 15, "salary_from": "1000", "salary_to": "2000",
                })
                check(resp.status == 200, "вторая вакансия (en) -> 200")
                body = await resp.json()
                vacancy_en_id = body["id"]
                check(body["duration_days"] == 15, "явно переданный duration_days применяется")
                check(body["salary_from"] == 1000, "владельцу зарплата видна всегда, вне зависимости от salary_visible")

                # Компания (тот же юзер 100, кабинет company уже активирован в Фазе 3)
                # тоже может публиковать вакансии — capability-based доступ (раздел 1 ТЗ)
                resp = await client.post("/api/vacancies", headers=auth_100, json={
                    "title": "Компания-вакансия", "vertical": "Crypto",
                    "author_workspace": "company", "lang": "ru",
                })
                check(resp.status == 200, "кабинет Компания тоже может публиковать вакансии (не только Рекрутер)")
                body = await resp.json()
                vacancy_company_id = body["id"]
                check(body["author_workspace"] == "company",
                      "вакансия от компании помечена author_workspace=company")
                check(body["verified_company"] is False,
                      "верификация НЕ автоматическая (ТЗ 'Компания. каб', раздел 2) — по умолчанию False, пока "
                      "администратор не включил бейдж вручную")

                # Верификация компании (26.08.2026, ТЗ "Компания. каб", раздел 2) —
                # ручной MVP: заявка только фиксирует момент, статус переключает
                # админ; видимость/функциональность компании не зависят от статуса.
                check(app["storage"].is_company_verified(100) is False, "изначально не верифицирована")
                resp = await client.post("/api/company/verification/request", headers=auth_100)
                check(resp.status == 200, "POST /api/company/verification/request -> 200")
                row = app["storage"].get_or_create_company_profile(100)
                check(row["verification_requested_at"] is not None, "момент заявки зафиксирован")

                pending = app["storage"].list_companies_for_verification()
                check(any(r["user_id"] == 100 for r in pending),
                      "компания появилась в админ-списке 'на верификацию' после заявки")

                ok = app["storage"].set_company_verified(100, True)
                check(ok is True, "админ вручную включает бейдж -> True")
                check(app["storage"].is_company_verified(100) is True, "бейдж теперь включён")

                resp = await client.get(f"/api/vacancies/{vacancy_company_id}", headers=auth_200)
                body = await resp.json()
                check(body["verified_company"] is True,
                      "после ручной верификации вакансия от той же компании показывает verified_company=True")

                resp = await client.get("/api/search?workspace=company&username=initiator", headers=auth_200)
                body = await resp.json()
                check(body["verified"] is True, "бейдж верификации виден и в карточке самого company-кабинета")

                not_ok = app["storage"].set_company_verified(999999, True)
                check(not_ok is False, "верификация несуществующего company-кабинета -> False")

                # Приоритет верифицированной компании в сортировке доски (раздел 4
                # ТЗ) — публикуем ЕЩЁ одну, заведомо более свежую вакансию от
                # рекрутера в той же вертикали и проверяем, что верифицированная
                # компания всё равно идёт первой, несмотря на то что она СТАРШЕ.
                resp = await client.post("/api/vacancies", headers=auth_100, json={
                    "title": "Freshest Recruiter Vacancy", "vertical": "Crypto", "lang": "ru",
                })
                check(resp.status == 200, "ещё одна (самая свежая) вакансия рекрутера в Crypto -> 200")

                resp = await client.get("/api/vacancies?vertical=Crypto", headers=auth_200)
                body = await resp.json()
                crypto_titles = [v["title"] for v in body["vacancies"]]
                check(crypto_titles[0] == "Компания-вакансия",
                      "вакансия верифицированной компании идёт ПЕРВОЙ в вертикали, обгоняя ДАЖЕ более свежую "
                      "вакансию рекрутера (is_verified_company DESC приоритетнее created_at DESC)")
                check(crypto_titles[1] == "Freshest Recruiter Vacancy",
                      "внутри группы 'неверифицированных' сортировка по дате как раньше (сначала новые)")

                # "Тип компании" (раздел 5 ТЗ) — множественный выбор + фильтр доски
                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "company_types", "value": "hr_agency,cpa_network"})
                check(resp.status == 200, "сохранение company_types -> 200")
                body = await resp.json()
                check(body["company_types"] == "hr_agency,cpa_network", "оба тега сохранены")

                resp = await client.post("/api/company/profile", headers=auth_100,
                                          json={"field": "company_type_other", "value": "Web3-студия"})
                check(resp.status == 200, "сохранение 'Другое' -> 200")
                other_logged = app["storage"]._conn.execute(
                    "SELECT text FROM guro_company_other_types WHERE company_user_id=100"
                ).fetchall()
                check(any(r["text"] == "Web3-студия" for r in other_logged),
                      "нестандартный 'Тип компании' залогирован для последующего review (не сразу в справочник)")

                resp = await client.get("/api/vacancies?company_type=hr_agency", headers=auth_200)
                body = await resp.json()
                check([v["title"] for v in body["vacancies"]] == ["Компания-вакансия"],
                      "?company_type= фильтрует доску по тегу компании-автора")

                resp = await client.get("/api/vacancies?company_type=bookmaker", headers=auth_200)
                body = await resp.json()
                check(body["vacancies"] == [], "фильтр по НЕ выбранному типу компании -> пусто")

                st.save_profile({"user_id": 496, "username": "nosub4", "name": "No Sub 4"})
                auth_496 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 496, "username": "nosub4"})}
                resp = await client.get("/api/vacancies", headers=auth_496)
                check(resp.status == 402, "GET /api/vacancies без БАЗОВОЙ подписки смотрящего -> 402")

                resp = await client.get("/api/vacancies", headers=auth_200)
                check(resp.status == 200, "GET /api/vacancies с базовой подпиской -> 200 (подписка рекрутера НЕ нужна)")
                body = await resp.json()
                check("truncated" in body, "ответ доски содержит флаг truncated")
                titles = [v["title"] for v in body["vacancies"]]
                check("Senior Product Manager" in titles and "Head of Marketing" in titles,
                      "обе активные вакансии видны в общей выдаче")
                board_ru = next(v for v in body["vacancies"] if v["title"] == "Senior Product Manager")
                check(board_ru["salary_from"] == 3000,
                      "не-владельцу salary_from виден, т.к. у этой вакансии salary_visible=True")
                check("views_count" not in board_ru, "владельческие поля (views_count) не утекают не-владельцу")

                board_en = next(v for v in body["vacancies"] if v["title"] == "Head of Marketing")
                check(board_en["salary_from"] is None,
                      "не-владельцу salary_from скрыт, т.к. у этой вакансии salary_visible не задан (False)")

                resp = await client.get("/api/vacancies?lang=en", headers=auth_200)
                body = await resp.json()
                en_titles = [v["title"] for v in body["vacancies"]]
                check("Head of Marketing" in en_titles and "Senior Product Manager" not in en_titles,
                      "?lang=en фильтрует по языку публикации")

                resp = await client.get("/api/vacancies?vertical=Crypto", headers=auth_200)
                body = await resp.json()
                check(all(v["vertical"] == "Crypto" for v in body["vacancies"]), "?vertical= фильтрует по вертикали")

                resp = await client.get("/api/vacancies?grade=Senior", headers=auth_200)
                body = await resp.json()
                check([v["title"] for v in body["vacancies"]] == ["Senior Product Manager"],
                      "?grade= фильтрует по грейду")

                resp = await client.get("/api/vacancies", params={"q": "продакта"}, headers=auth_200)
                body = await resp.json()
                check("Senior Product Manager" in [v["title"] for v in body["vacancies"]],
                      "?q= находит по свободному тексту в описании")

                resp = await client.get(
                    "/api/vacancies",
                    params={"vertical": "Crypto", "q": "совершенно левый текст, которого нигде нет"},
                    headers=auth_200,
                )
                body = await resp.json()
                check("Head of Marketing" in [v["title"] for v in body["vacancies"]],
                      "?q= с несовпадающим текстом всё равно находит по структурным фильтрам — "
                      "OR-логика, не строгое AND (раздел 6 ТЗ, устойчивость к неточному тегированию)")

                resp = await client.get("/api/vacancies/mine", headers=auth_100)
                check(resp.status == 200, "GET /api/vacancies/mine -> 200")
                body = await resp.json()
                check(len(body["vacancies"]) == 4,
                      "у автора все 4 его вакансии видны в /mine (recruiter x3 + company x1)")

                # Просмотр чужой карточки увеличивает views_count у владельца
                resp = await client.get(f"/api/vacancies/{vacancy_ru_id}", headers=auth_200)
                check(resp.status == 200, "GET /api/vacancies/{id} чужой активной вакансии -> 200")
                resp = await client.get(f"/api/vacancies/{vacancy_ru_id}", headers=auth_100)
                body = await resp.json()
                check(body["views_count"] == 1,
                      "просмотр НЕ-автором увеличил views_count (просмотр автором — нет)")

                # Редактирование
                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/edit", headers=auth_200,
                                          json={"title": "Hacked"})
                check(resp.status == 404, "редактировать чужую вакансию -> 404 (не автор)")
                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/edit", headers=auth_100,
                                          json={"salary_to": "6000"})
                check(resp.status == 200, "автор редактирует свою вакансию -> 200")
                body = await resp.json()
                check(body["salary_to"] == 6000, "изменённое поле применилось")

                # Пауза / возобновление
                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/pause", headers=auth_100)
                check(resp.status == 200, "пауза своей вакансии -> 200")
                body = await resp.json()
                check(body["status"] == "paused", "статус сменился на paused")
                resp = await client.get("/api/vacancies", headers=auth_200)
                body = await resp.json()
                check("Senior Product Manager" not in [v["title"] for v in body["vacancies"]],
                      "вакансия на паузе пропадает из общей выдачи")
                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/resume", headers=auth_100)
                check(resp.status == 200, "возобновление -> 200")
                body = await resp.json()
                check(body["status"] == "active", "статус снова active")

                # Продление
                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/extend", headers=auth_100,
                                          json={"duration_days": 60})
                check(resp.status == 200, "продление своей вакансии -> 200")
                body = await resp.json()
                check(body["duration_days"] == 60, "duration_days обновлён продлением")

                # Отклики (мини-ATS, раздел 5 ТЗ) — кандидат откликается на
                # vacancy_ru_id (contact_method=guro_id)
                st.save_profile({"user_id": 499, "username": "candidate1", "name": "Cand One", "vertical": "Gambling"})
                auth_499 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 499, "username": "candidate1"})}
                app["storage"].activate_subscription(499, 30)

                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/respond", headers=auth_100, json={})
                check(resp.status == 400, "автор не может откликнуться на свою же вакансию -> 400 SELF_RESPONSE")

                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/respond", headers=auth_499,
                                          json={"message": "Готов начать сразу"})
                check(resp.status == 200, "кандидат откликается -> 200")
                body = await resp.json()
                response_id = body["id"]
                check(body["status"] == "new", "новый отклик сразу в статусе new")

                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/respond", headers=auth_499, json={})
                check(resp.status == 409, "повторный отклик той же вакансии -> 409 ALREADY_RESPONDED")

                resp = await client.get(f"/api/vacancies/{vacancy_ru_id}/responses", headers=auth_200)
                check(resp.status == 404, "чужой список откликов -> 404 (не владелец)")

                resp = await client.get(f"/api/vacancies/{vacancy_ru_id}/responses", headers=auth_100)
                check(resp.status == 200, "владелец видит отклики своей вакансии -> 200")
                body = await resp.json()
                check(len(body["responses"]) == 1 and body["responses"][0]["candidate_username"] == "candidate1",
                      "отклик кандидата виден владельцу с его username")

                resp = await client.post(f"/api/responses/{response_id}/status", headers=auth_200,
                                          json={"status": "interview"})
                check(resp.status == 404, "менять статус чужого отклика -> 404 (не владелец вакансии)")

                resp = await client.post(f"/api/responses/{response_id}/status", headers=auth_100,
                                          json={"status": "not_a_status"})
                check(resp.status == 400, "невалидный статус отклика -> 400 INVALID_STATUS")

                resp = await client.post(f"/api/responses/{response_id}/status", headers=auth_100,
                                          json={"status": "interview"})
                check(resp.status == 200, "владелец двигает воронку отклика -> 200")
                body = await resp.json()
                check(body["status"] == "interview", "статус отклика обновлён (воронка Найм-раздела 5.3)")

                resp = await client.get("/api/responses", headers=auth_100)
                check(resp.status == 200, "GET /api/responses (агрегация по всем своим вакансиям) -> 200")
                body = await resp.json()
                check(len(body["responses"]) == 1 and body["responses"][0]["vacancy_title"] == "Senior Product Manager",
                      "агрегированный отклик подписан названием вакансии (раздел 5.5)")

                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/close", headers=auth_200)
                check(resp.status == 404, "закрыть чужую вакансию -> 404 (не автор)")

                resp = await client.post(f"/api/vacancies/{vacancy_ru_id}/close", headers=auth_100,
                                          json={"reason": "Нашли кандидата"})
                check(resp.status == 200, "автор закрывает свою вакансию (с причиной) -> 200")
                body = await resp.json()
                check(body["status"] == "closed", "статус вакансии сменился на closed")

                resp = await client.get("/api/vacancies", headers=auth_200)
                body = await resp.json()
                check("Senior Product Manager" not in [v["title"] for v in body["vacancies"]],
                      "закрытая вакансия пропадает из общей выдачи")

                resp = await client.get("/api/vacancies/mine", headers=auth_100)
                body = await resp.json()
                check(len(body["vacancies"]) == 4,
                      "но в /mine у автора закрытая вакансия всё ещё видна (для истории/архива)")
                closed_row = next(v for v in body["vacancies"] if v["id"] == vacancy_ru_id)
                check(closed_row["closed_reason"] == "Нашли кандидата",
                      "closed_reason сохранён и виден владельцу в /mine")

                # «Резюме» — не отдельный экран, а фильтр work_status=looking
                # поверх того же поиска; НЕ требует ни подписки, ни единого
                # открытого privacy-тумблера у самого кандидата (work_status
                # публичен всегда, тот же принцип, что и везде в приложении).
                st.save_profile({"user_id": 497, "username": "resumeuser1", "name": "Resume One", "vertical": "Gambling"})
                app["storage"].set_work_status(497, "looking")
                st.save_profile({"user_id": 498, "username": "resumeuser2", "name": "Resume Two", "vertical": "Gambling"})
                app["storage"].set_work_status(498, "working")

                resp = await client.get("/api/search?resumes=1", headers=auth_496)
                check(resp.status == 402, "GET /api/search?resumes=1 без подписки смотрящего -> 402")

                resp = await client.get("/api/search?resumes=1", headers=auth_200)
                check(resp.status == 200, "GET /api/search?resumes=1 с подпиской -> 200")
                body = await resp.json()
                check(body["mode"] == "list", "резюме-режим -> mode=list")
                resume_ids = [r["user_id"] for r in body["results"]]
                check(497 in resume_ids,
                      "resumeuser1 (work_status=looking) найден, ХОТЯ не открыл ни одного privacy-тумблера")
                check(498 not in resume_ids, "resumeuser2 (work_status=working) НЕ попадает в резюме-выдачу")
                found_resume = next(r for r in body["results"] if r["user_id"] == 497)
                check(found_resume["name"] == "Resume One",
                      "имя видно по умолчанию (28.08.2026: show_name — opt-out, resumeuser1 его не трогал)")
                check(found_resume["work_status"] == "looking", "work_status виден в результате резюме-поиска")

                resp = await client.get("/api/search?resumes=1&vertical=Crypto", headers=auth_200)
                body = await resp.json()
                check(497 not in [r["user_id"] for r in body["results"]],
                      "resumes=1 + vertical= сужает выдачу (resumeuser1 в Gambling, не Crypto)")

                # Живой счётчик "Показать N кандидатов" (28.08.2026, макет
                # "12 · Рекрутер — Поиск кандидатов") — тот же гейт/фильтры,
                # что у /api/search, но только count, без сборки карточек.
                resp = await client.get("/api/candidates/count?resumes=1", headers=auth_496)
                check(resp.status == 402, "GET /api/candidates/count без подписки -> 402 (тот же гейт, что у /api/search)")

                resp = await client.get("/api/candidates/count?resumes=1", headers=auth_200)
                check(resp.status == 200, "GET /api/candidates/count с подпиской -> 200")
                count_body = await resp.json()
                resp = await client.get("/api/search?resumes=1", headers=auth_200)
                list_body = await resp.json()
                check(count_body["count"] == len(list_body["results"]),
                      "count совпадает с фактическим числом результатов того же фильтра")

                resp = await client.get("/api/candidates/count?resumes=1&vertical=Crypto", headers=auth_200)
                count_body = await resp.json()
                check(count_body["count"] == 0,
                      "count с тем же фильтром vertical=Crypto, что сузил выдачу выше, -> 0")

                # --- Тарифы и лимиты (27.08.2026, ТЗ "Тарифы и лимиты") -------
                # Конфиг/оверрайд (раздел 3 ТЗ) — глобальный слой + точечный
                # оверрайд на аккаунт, оба уровня поверх дефолт-констант.
                check(app["storage"].get_config("test.some.key", 42) == 42, "get_config без записи -> дефолт")
                app["storage"].set_config("test.some.key", 99)
                check(app["storage"].get_config("test.some.key", 42) == 99, "set_config переопределяет дефолт")
                check(app["storage"].get_effective_limit(999999, "test.some.key", 42) == 99,
                      "get_effective_limit без оверрайда на аккаунт -> глобальный конфиг")
                app["storage"].set_user_limit_override(999999, "test.some.key", 5)
                check(app["storage"].get_effective_limit(999999, "test.some.key", 42) == 5,
                      "оверрайд на аккаунт побеждает глобальный конфиг")
                check(app["storage"].list_user_limit_overrides(999999)[0]["value"] == "5",
                      "list_user_limit_overrides видит запись")
                check(app["storage"].clear_user_limit_override(999999, "test.some.key") is True,
                      "clear_user_limit_override -> True (запись была)")
                check(app["storage"].clear_user_limit_override(999999, "test.some.key") is False,
                      "повторный clear -> False (уже нечего снимать)")
                check(app["storage"].get_effective_limit(999999, "test.some.key", 42) == 99,
                      "после clear снова действует глобальный конфиг")
                check(app["storage"].count_new_partnerships_today(999999) == 0, "0 партнёрств у свежего аккаунта")
                check(app["storage"].count_new_vacancies_today(999999) == 0, "0 вакансий у свежего аккаунта")

                # Приоритет тира при выборе лимита (раздел 2.1/2.2 ТЗ) — если
                # оплачены и Рекрутер, и Компания, действует более щедрый
                # лимит Компании; активные вакансии считаются отдельно на
                # каждый воркспейс, тир Компании тут ни при чём для Рекрутера.
                st.save_profile({"user_id": 930, "username": "both_subs", "name": "Both"})
                app["storage"].activate_recruiter_subscription(930, 30)
                app["storage"].activate_company_subscription(930, 30, tier="pro")
                check(guro_id_api._views_per_day_limit(app["storage"], 930) == GC.LIMIT_VIEWS_PER_DAY_COMPANY_PRO,
                      "Рекрутер+Компания(Pro) разом -> действует лимит просмотров Компании Pro (более щедрый)")
                check(guro_id_api._new_requests_per_day_limit(app["storage"], 930) == GC.LIMIT_NEW_REQUESTS_PER_DAY_COMPANY,
                      "то же самое для лимита новых заявок")
                check(guro_id_api._active_vacancies_limit(app["storage"], 930, "company") == GC.LIMIT_ACTIVE_VACANCIES_COMPANY_PRO,
                      "потолок активных вакансий company-воркспейса — по тиру Pro")
                check(guro_id_api._active_vacancies_limit(app["storage"], 930, "recruiter") == GC.LIMIT_ACTIVE_VACANCIES_RECRUITER,
                      "потолок активных вакансий recruiter-воркспейса свой, не зависит от тира Компании")

                # Лимит просмотров/день (раздел 2.1 ТЗ) — тестируем через
                # оверрайд, чтобы не создавать десятки профилей.
                st.save_profile({"user_id": 910, "username": "viewer_recruiter", "name": "Viewer R"})
                app["storage"].activate_recruiter_subscription(910, 30)
                app["storage"].set_user_limit_override(910, GC.LIMIT_KEY_VIEWS_RECRUITER, 2)
                auth_910 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 910, "username": "viewer_recruiter"})}
                st.save_profile({"user_id": 911, "username": "target_a", "name": "A"})
                st.save_profile({"user_id": 912, "username": "target_b", "name": "B"})
                st.save_profile({"user_id": 913, "username": "target_c", "name": "C"})

                resp = await client.get("/api/search?username=target_a", headers=auth_910)
                check(resp.status == 200, "1-й просмотр в пределах оверрайда (2) -> 200")
                resp = await client.get("/api/search?username=target_b", headers=auth_910)
                check(resp.status == 200, "2-й просмотр -> 200 (лимит на сегодня теперь исчерпан)")
                resp = await client.get("/api/search?username=target_c", headers=auth_910)
                check(resp.status == 429, "3-й просмотр в тот же день -> 429 VIEW_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "VIEW_LIMIT_REACHED", "код ошибки понятен")
                check(body.get("resets_at"), "тело содержит resets_at (раздел 3 ТЗ, 'когда обновится')")

                resp = await client.get("/api/search?username=viewer_recruiter", headers=auth_910)
                check(resp.status == 200, "self-view никогда не считается и не лимитируется")

                # Лимит новых заявок/день (раздел 2.2 ТЗ).
                st.save_profile({"user_id": 920, "username": "req_tester", "name": "Req"})
                auth_920 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 920, "username": "req_tester"})}
                app["storage"].set_user_limit_override(920, GC.LIMIT_KEY_REQUESTS_PERSONAL, 1)
                st.save_profile({"user_id": 921, "username": "req_target1", "name": "T1"})
                st.save_profile({"user_id": 922, "username": "req_target2", "name": "T2"})

                resp = await client.post("/api/partnerships", headers=auth_920,
                                          json={"confirmer_username": "req_target1", "ptype": "deal"})
                check(resp.status == 200, "1-я новая заявка в пределах оверрайда (1) -> 200")
                resp = await client.post("/api/partnerships", headers=auth_920,
                                          json={"confirmer_username": "req_target2", "ptype": "deal"})
                check(resp.status == 429, "2-я заявка в тот же день (лимит=1) -> 429 DAILY_REQUEST_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "DAILY_REQUEST_LIMIT_REACHED" and body.get("resets_at"),
                      "код + resets_at понятны")

                # Лимиты вакансий (раздел 2.3 ТЗ): дневной лимит новых
                # публикаций + потолок одновременно активных, независимо.
                st.save_profile({"user_id": 940, "username": "vac_tester", "name": "VacT"})
                auth_940 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 940, "username": "vac_tester"})}
                app["storage"].activate_recruiter_subscription(940, 30)
                app["storage"].set_user_limit_override(940, GC.LIMIT_KEY_NEW_VACANCIES, 2)

                resp = await client.post("/api/vacancies", headers=auth_940, json={"title": "V1"})
                check(resp.status == 200, "1-я вакансия в пределах оверрайда дневного лимита (2) -> 200")
                resp = await client.post("/api/vacancies", headers=auth_940, json={"title": "V2"})
                check(resp.status == 200, "2-я вакансия -> 200 (дневной лимит теперь исчерпан)")
                resp = await client.post("/api/vacancies", headers=auth_940, json={"title": "V3"})
                check(resp.status == 429, "3-я вакансия в тот же день -> 429 DAILY_VACANCY_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "DAILY_VACANCY_LIMIT_REACHED" and body.get("resets_at"),
                      "код + resets_at понятны")

                # Потолок ОДНОВРЕМЕННО активных — отдельный аккаунт, чтобы не
                # смешивать с дневным лимитом публикаций выше.
                st.save_profile({"user_id": 950, "username": "vac_active_tester", "name": "VacActive"})
                auth_950 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 950, "username": "vac_active_tester"})}
                app["storage"].activate_recruiter_subscription(950, 30)
                app["storage"].set_user_limit_override(950, GC.LIMIT_KEY_NEW_VACANCIES, 10)
                app["storage"].set_user_limit_override(950, GC.LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER, 2)

                resp = await client.post("/api/vacancies", headers=auth_950, json={"title": "A1"})
                check(resp.status == 200, "1-я активная вакансия в пределах потолка (2) -> 200")
                vac_a1_id = (await resp.json())["id"]
                resp = await client.post("/api/vacancies", headers=auth_950, json={"title": "A2"})
                check(resp.status == 200, "2-я активная вакансия -> 200 (потолок теперь исчерпан)")
                vac_a2_id = (await resp.json())["id"]
                resp = await client.post("/api/vacancies", headers=auth_950, json={"title": "A3"})
                check(resp.status == 429, "3-я вакансия при потолке активных=2 -> 429 ACTIVE_VACANCY_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "ACTIVE_VACANCY_LIMIT_REACHED" and body.get("limit") == 2,
                      "код + limit в теле понятны")

                resp = await client.post(f"/api/vacancies/{vac_a2_id}/pause", headers=auth_950)
                check(resp.status == 200, "пауза одной из активных -> 200 (освобождает место)")
                app["storage"].set_user_limit_override(950, GC.LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER, 1)
                resp = await client.post(f"/api/vacancies/{vac_a2_id}/resume", headers=auth_950)
                check(resp.status == 429,
                      "возобновление ТОЖЕ сверяется с потолком активных — A1 один уже заполняет ужатый потолок (1)")
                resp = await client.post(f"/api/vacancies/{vac_a1_id}/close", headers=auth_950)
                check(resp.status == 200, "закрыть A1 -> 200 (освобождает место при потолке=1)")
                resp = await client.post(f"/api/vacancies/{vac_a2_id}/resume", headers=auth_950)
                check(resp.status == 200, "теперь возобновление проходит (0 активных < потолка 1)")

                # --- Роли и команда компании (27.08.2026, ТЗ "Роли и управление
                # командой в кабинете 'Компания'") -----------------------------
                st.save_profile({"user_id": 960, "username": "masha_owner", "name": "Masha"})
                auth_960 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 960, "username": "masha_owner"})}
                st.save_profile({"user_id": 965, "username": "dima_am", "name": "Dima"})
                auth_965 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 965, "username": "dima_am"})}

                resp = await client.post("/api/company/join_request", headers=auth_965,
                                          json={"company_id": 999999, "position_text": "Affiliate Manager"})
                check(resp.status == 404, "заявка на несуществующую компанию -> 404 COMPANY_NOT_FOUND")

                resp = await client.post("/api/company/create", headers=auth_960, json={"name": "1xBet"})
                check(resp.status == 200, "Маша создаёт компанию '1xBet' -> 200")
                app["storage"].activate_company_subscription(960, 30)

                resp = await client.get("/api/company/team", headers=auth_960)
                check(resp.status == 200, "GET /api/company/team владельцем -> 200")
                body = await resp.json()
                check(body["member_count"] == 1 and len(body["members"]) == 1, "пока только сама Маша")
                check(body["members"][0]["role"] == "owner", "Маша — Владелец")
                check(body["requests"] == [], "заявок пока нет")

                resp = await client.get("/api/company/team", headers=auth_965)
                check(resp.status == 403, "просмотр 'Команды' НЕ-участником -> 403 NOT_A_COMPANY_MEMBER")

                resp = await client.post("/api/company/profile", headers=auth_965,
                                          json={"field": "description", "value": "hack"})
                check(resp.status == 403, "правка витрины НЕ-участником -> 403")

                resp = await client.post("/api/company/join_request", headers=auth_965,
                                          json={"company_id": 960, "position_text": "Affiliate Manager"})
                check(resp.status == 200, "Дима подаёт заявку на присоединение к 1xBet -> 200")
                body = await resp.json()
                dima_request_id = body["id"]
                check(body["status"] == "pending", "заявка сразу в статусе pending")

                resp = await client.post("/api/company/join_request", headers=auth_965,
                                          json={"company_id": 960, "position_text": "Affiliate Manager"})
                check(resp.status == 409, "повторная заявка -> 409 ALREADY_REQUESTED")

                resp = await client.post(f"/api/company/team/requests/{dima_request_id}/approve", headers=auth_965)
                check(resp.status == 403, "одобрить заявку может только Владелец -> 403 NOT_OWNER (Дима не Владелец)")

                resp = await client.get("/api/company/team", headers=auth_960)
                body = await resp.json()
                check(len(body["requests"]) == 1 and body["requests"][0]["username"] == "dima_am",
                      "заявка Димы видна Владельцу с должностью")
                check(body["approvals_left_today"] == GC.LIMIT_COMPANY_APPROVALS_PER_DAY,
                      "одобрений сегодня ещё не тратили — полный лимит (5, раздел 3.5 ТЗ)")

                resp = await client.post(f"/api/company/team/requests/{dima_request_id}/approve", headers=auth_960)
                check(resp.status == 200, "Владелец одобряет заявку Димы -> 200")

                resp = await client.get("/api/company/team", headers=auth_965)
                check(resp.status == 200, "Дима теперь участник -> видит 'Команду'")
                body = await resp.json()
                check(body["my_role"] == "admin", "Дима получил роль Админ/Рекрутер")
                check("requests" not in body, "Админ НЕ видит заявки (раздел 2 ТЗ — не управляет составом команды)")
                check(body["member_count"] == 2, "счётчик обновился: 2 из 5")

                resp = await client.post("/api/company/profile", headers=auth_965,
                                          json={"field": "description", "value": "1xBet — казино-оператор"})
                check(resp.status == 200,
                      "Админ/Рекрутер редактирует бренд-страницу НАРАВНЕ с Владельцем (раздел 2 ТЗ)")

                # Раздел 6 ТЗ — вакансия от лица компании атрибутирована на
                # company_id, а НЕ на личный id того, кто реально нажал "Опубликовать".
                resp = await client.post("/api/vacancies", headers=auth_965,
                                          json={"title": "Affiliate Manager", "author_workspace": "company"})
                check(resp.status == 200, "Дима (Админ) публикует вакансию от лица 1xBet -> 200")
                body = await resp.json()
                check(body["author_id"] == 960, "вакансия принадлежит КОМПАНИИ (960), не личному id Димы (965)")
                check(body["published_by_user_id"] == 965,
                      "но известно, КТО конкретно её опубликовал (раздел 6 ТЗ, внутренняя аналитика)")

                resp = await client.get("/api/vacancies/mine", headers=auth_965)
                check(resp.status == 200, "GET /api/vacancies/mine у Димы -> 200")
                body = await resp.json()
                check(any(v["title"] == "Affiliate Manager" for v in body["vacancies"]),
                      "Дима видит ОБЩИЕ вакансии компании в 'Мои вакансии', хотя они не 'его личные'")

                # Повторная заявка от ДРУГОГО человека, ещё не одобренная —
                # ALREADY_REQUESTED специфичен именно этому заявителю, у Олега
                # своя, независимая.
                st.save_profile({"user_id": 966, "username": "oleg_am", "name": "Oleg"})
                auth_966 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 966, "username": "oleg_am"})}
                resp = await client.post("/api/company/join_request", headers=auth_966,
                                          json={"company_id": 960, "position_text": "Affiliate Manager"})
                check(resp.status == 200, "Олег тоже подаёт заявку -> 200")
                oleg_request_id = (await resp.json())["id"]

                resp = await client.post(f"/api/company/team/requests/{oleg_request_id}/reject", headers=auth_960)
                check(resp.status == 200, "Владелец отклоняет заявку Олега -> 200")
                resp = await client.post(f"/api/company/team/requests/{oleg_request_id}/reject", headers=auth_960)
                check(resp.status == 404, "повторное отклонение уже решённой заявки -> 404")

                resp = await client.post("/api/company/join_request", headers=auth_966,
                                          json={"company_id": 960, "position_text": "Affiliate Manager"})
                check(resp.status == 200, "после отклонения Олег МОЖЕТ подать заявку заново -> 200")
                oleg_request_id = (await resp.json())["id"]  # НОВАЯ заявка, старая (rejected) уже не годится

                # Потолок участников по тарифу (раздел 3.4 ТЗ) — Basic = 5,
                # у 1xBet уже 2 (Маша+Дима), нужно ещё 3 одобрения, чтобы упереться.
                for uid, uname in ((967, "u967"), (968, "u968"), (969, "u969")):
                    st.save_profile({"user_id": uid, "username": uname, "name": uname})
                    auth_u = {"Authorization": "tma " + _guro_make_init_data(token, {"id": uid, "username": uname})}
                    resp = await client.post("/api/company/join_request", headers=auth_u, json={"company_id": 960})
                    check(resp.status == 200, f"{uname} подаёт заявку -> 200")
                    req_id = (await resp.json())["id"]
                    resp = await client.post(f"/api/company/team/requests/{req_id}/approve", headers=auth_960)
                    check(resp.status == 200, f"{uname} одобрен -> 200")

                resp = await client.get("/api/company/team", headers=auth_960)
                body = await resp.json()
                check(body["member_count"] == 5, "теперь ровно 5 из 5 (потолок Basic исчерпан)")

                resp = await client.post(f"/api/company/team/requests/{oleg_request_id}/approve", headers=auth_960)
                check(resp.status == 409, "6-е одобрение при потолке 5/5 -> 409 MEMBER_LIMIT_REACHED")
                body = await resp.json()
                check(body["error"] == "MEMBER_LIMIT_REACHED" and body.get("limit") == 5, "код + limit понятны")

                # Лимит одобрений/день (раздел 3.5 ТЗ, "не более 5 в день") —
                # отдельная свежая компания с оверрайдом=1, чтобы не городить
                # 5 реальных одобрений ради одной проверки.
                st.save_profile({"user_id": 1050, "username": "owner1050", "name": "Owner1050"})
                auth_1050 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 1050, "username": "owner1050"})}
                resp = await client.post("/api/company/create", headers=auth_1050, json={"name": "DailyLimitCo"})
                check(resp.status == 200, "владелец 2-й тестовой компании (для лимита одобрений/день) создан -> 200")
                app["storage"].set_user_limit_override(1050, GC.LIMIT_KEY_COMPANY_APPROVALS_PER_DAY, 1)

                for uid, uname in ((1051, "d1051"), (1052, "d1052")):
                    st.save_profile({"user_id": uid, "username": uname, "name": uname})
                    auth_u = {"Authorization": "tma " + _guro_make_init_data(token, {"id": uid, "username": uname})}
                    resp = await client.post("/api/company/join_request", headers=auth_u, json={"company_id": 1050})
                    req_id = (await resp.json())["id"]
                    resp = await client.post(f"/api/company/team/requests/{req_id}/approve", headers=auth_1050)
                    if uid == 1051:
                        check(resp.status == 200, "1-е одобрение сегодня (оверрайд=1) -> 200")
                    else:
                        check(resp.status == 429, "2-е одобрение в тот же день -> 429 DAILY_APPROVAL_LIMIT_REACHED")
                        body = await resp.json()
                        check(body["error"] == "DAILY_APPROVAL_LIMIT_REACHED" and body.get("resets_at"),
                              "код + resets_at понятны")

                # Удаление участника (раздел 4 ТЗ) — прошлая вакансия Димы
                # остаётся нетронутой (снимок на момент события).
                resp = await client.post("/api/company/team/members/965/remove", headers=auth_965)
                check(resp.status == 403, "участник не может удалить сам себя (не Владелец) -> 403")

                resp = await client.post("/api/company/team/members/960/remove", headers=auth_960)
                check(resp.status == 403, "Владелец не может удалить сам себя -> 403 (target_user_id == owner)")

                resp = await client.post("/api/company/team/members/965/remove", headers=auth_960)
                check(resp.status == 200, "Владелец удаляет Диму из команды -> 200")

                resp = await client.post("/api/company/profile", headers=auth_965,
                                          json={"field": "description", "value": "после увольнения"})
                check(resp.status == 403, "Дима больше не может править бренд-страницу после удаления")

                resp = await client.get("/api/vacancies/mine", headers=auth_960)
                body = await resp.json()
                check(any(v["title"] == "Affiliate Manager" for v in body["vacancies"]),
                      "вакансия, опубликованная Димой ДО удаления, осталась у компании как ни в чём не бывало")

                # Передача владения (раздел 5 ТЗ).
                resp = await client.post("/api/company/team/members/967/transfer", headers=auth_965)
                check(resp.status == 403, "передать владение может только ТЕКУЩИЙ Владелец -> 403 (Дима уже не в команде)")

                resp = await client.post("/api/company/team/members/960/transfer", headers=auth_960)
                check(resp.status == 403, "нельзя передать владение самому себе")

                resp = await client.post("/api/company/team/members/967/transfer", headers=auth_960)
                check(resp.status == 200, "Маша передаёт владение участнику 967 -> 200")

                resp = await client.get("/api/company/team", headers=auth_960)
                body = await resp.json()
                check(body["my_role"] == "admin", "Маша теперь Админ/Рекрутер (не потеряла доступ к компании)")
                check("requests" not in body, "и больше не видит заявки — та же логика, что и у любого Админа")

                resp = await client.post("/api/company/create", headers=auth_960, json={"name": "Should Fail"})
                check(resp.status == 409,
                      "Маша всё ещё СОСТОИТ в 1xBet (теперь как Админ) -> создать вторую компанию нельзя")

                # Раздел 6 ТЗ — сделка "от лица компании" (as_company), любой
                # участник (не только Владелец) может её подтвердить.
                st.save_profile({"user_id": 1060, "username": "counterparty1060", "name": "CP"})
                resp = await client.post("/api/partnerships", headers=auth_960, json={
                    "confirmer_username": "counterparty1060", "ptype": "deal", "as_company": True,
                })
                check(resp.status == 200, "сделка 'от лица компании' (as_company), инициатор — Админ (Маша) -> 200")
                partnership_id_company = (await resp.json())["id"]
                prow = app["storage"].get_partnership(partnership_id_company)
                check(prow["company_id"] == 960, "партнёрство атрибутировано на company_id (раздел 6 ТЗ)")
                check(prow["initiator_id"] == 960, "но initiator_id — конкретный человек, который её вёл")
                company_history = app["storage"].list_company_partnerships(960)
                check(len(company_history) == 1 and company_history[0]["id"] == partnership_id_company,
                      "list_company_partnerships видит сделку как часть единой истории компании")

                # Раздел 3.0.1 ТЗ «Роли и команда» (06.09.2026): занятое название
                # больше НЕ создаёт вторую такую же компанию. Раньше это было
                # мягкое предупреждение ПОСЛЕ создания, из-за чего человек
                # получал дубль и предложение оплатить ненужный тариф.
                st.save_profile({"user_id": 1070, "username": "similar_test", "name": "SimilarTest"})
                auth_1070 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 1070, "username": "similar_test"})}
                resp = await client.post("/api/company/create", headers=auth_1070, json={"name": "1xBet Casino"})
                check(resp.status == 409, "создание компании с занятым названием -> 409 (не создаём дубль)")
                body = await resp.json()
                check(body.get("error") == "COMPANY_NAME_TAKEN", "код отказа понятен фронту")
                check(body.get("matches") and any("1xBet" in m["name"] for m in body["matches"]),
                      "в отказе приехали найденные компании")
                check(body["matches"][0].get("company_id"),
                      "у найденной компании есть company_id — на нём держится кнопка присоединения")

                # Проверка названия ДО создания: ничего не создаёт, но находит.
                resp = await client.get("/api/company/name_check?name=1xBet%20Casino", headers=auth_1070)
                check(resp.status == 200, "GET /api/company/name_check -> 200")
                body = await resp.json()
                check(body.get("matches") and body["matches"][0].get("company_id"),
                      "проверка названия возвращает найденную компанию с company_id")

                resp = await client.get("/api/company/name_check?name=Freshly%20Unique%20Name", headers=auth_1070)
                body = await resp.json()
                check(body.get("matches") == [], "свободное название совпадений не даёт")

                # Пункт 5 раздела 3.0.1: одноимённые компании бывают разными
                # юрлицами (888 во Франции и 888 в Португалии) — выход есть.
                resp = await client.post("/api/company/create", headers=auth_1070,
                                          json={"name": "1xBet Casino", "confirm_different": True})
                check(resp.status == 200, "с confirm_different создание проходит (пункт 5 раздела 3.0.1)")

                # --- личные сообщения внутри прилы (Фаза 1, 11.08.2026) -------
                # ВАЖНО: auth_300 к этому моменту УЖЕ подписан (см. тест
                # crypto-вебхука выше, user_id=300 получил подписку через него) —
                # для проверок "нет подписки" берём отдельного, гарантированно
                # неподписанного юзера.
                st.save_profile({"user_id": 350, "username": "nosub", "name": "No Sub"})
                auth_350 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 350, "username": "nosub"})}
                check(not app["storage"].is_subscribed(350), "350 действительно не подписан (для чистоты теста)")

                resp = await client.post("/api/messages", headers=auth_350,
                                          json={"recipient_id": 200, "body": "Привет!"})
                check(resp.status == 402,
                      "первое сообщение незнакомцу БЕЗ подписки отправителя -> 402 SUBSCRIPTION_REQUIRED")
                body = await resp.json()
                check(body["error"] == "SUBSCRIPTION_REQUIRED", "тело содержит понятный код ошибки")

                resp = await client.post("/api/messages", headers=auth_100,
                                          json={"recipient_id": 100, "body": "себе"})
                check(resp.status == 400, "сообщение самому себе -> 400 SELF_MESSAGE")

                resp = await client.post("/api/messages", headers=auth_100,
                                          json={"recipient_id": 999, "body": "куда?"})
                check(resp.status == 404, "получатель без анкеты в боте -> 404 NO_RECIPIENT_PROFILE")

                resp = await client.post("/api/messages", headers=auth_100,
                                          json={"recipient_id": 200, "body": "   "})
                check(resp.status == 400, "пустое (после strip) сообщение -> 400 EMPTY_BODY")

                # initiator (100, подписан) пишет ПЕРВЫМ confirmer'у (200) -> новый тред
                resp = await client.post("/api/messages", headers=auth_100,
                                          json={"recipient_id": 200, "body": "Есть минутка обсудить сделку?"})
                check(resp.status == 200, "подписанный отправитель пишет первым -> 200")
                body = await resp.json()
                check("id" in body, "ответ содержит id созданного сообщения")

                resp = await client.get("/api/me", headers=auth_200)
                body = await resp.json()
                check(body["unread_messages"] == 1, "у получателя появилось 1 непрочитанное сообщение")

                resp = await client.get("/api/messages", headers=auth_200)
                check(resp.status == 200, "GET /api/messages -> 200")
                body = await resp.json()
                check(len(body["threads"]) == 1, "у получателя один тред")
                check(body["threads"][0]["other_user_id"] == 100, "тред с корректным собеседником")
                check(body["threads"][0]["unread_count"] == 1, "список тредов тоже показывает непрочитанное")
                check(body["threads"][0]["last_message"] == "Есть минутка обсудить сделку?",
                      "превью последнего сообщения")

                resp = await client.get("/api/messages/with/100", headers=auth_200)
                check(resp.status == 200, "GET /api/messages/with/<id> -> 200")
                body = await resp.json()
                check(len(body["messages"]) == 1, "в переписке одно сообщение")
                check(body["messages"][0]["mine"] is False, "сообщение от initiator -> mine=False у confirmer'а")
                check(body["other_name"] == "Init", "other_name подтягивается из профиля собеседника")
                check(body["can_send_first"] is True, "тред уже есть -> отвечать можно (can_send_first=True)")

                resp = await client.get("/api/me", headers=auth_200)
                body = await resp.json()
                check(body["unread_messages"] == 0,
                      "просмотр переписки (GET /api/messages/with/) отметил сообщение прочитанным")

                # confirmer (200) отвечает в уже созданном треде
                resp = await client.post("/api/messages", headers=auth_200,
                                          json={"recipient_id": 100, "body": "Да, давай завтра в 15:00"})
                check(resp.status == 200, "ответ в существующем треде -> 200")

                resp = await client.get("/api/me", headers=auth_100)
                body = await resp.json()
                check(body["unread_messages"] == 1, "у initiator появилось непрочитанное сообщение-ответ")

                # антиспам: подписанный 100 упирается в дневной лимит новых тредов
                # (один тред у него уже есть с 200 -> лимит исчерпается раньше конца цикла)
                for i in range(GC.MESSAGE_MAX_NEW_THREADS_PER_DAY):
                    st.save_profile({"user_id": 5000 + i, "username": f"spamtarget{i}", "name": f"Target {i}"})
                    r = await client.post("/api/messages", headers=auth_100,
                                           json={"recipient_id": 5000 + i, "body": "hi"})
                    if r.status != 200:
                        break
                check(r.status == 429, "после исчерпания дневного лимита новых тредов -> 429 RATE_LIMITED")
                body = await r.json()
                check(body["error"] == "RATE_LIMITED", "тело содержит понятный код ошибки")

                # ответ в уже существующем треде НЕ требует подписки отвечающего —
                # 500 (подписан) пишет первым 600 (НЕ подписан), затем 600 отвечает
                st.save_profile({"user_id": 500, "username": "sender500", "name": "Sender 500"})
                st.save_profile({"user_id": 600, "username": "target600", "name": "Target 600"})
                app["storage"].activate_subscription(500, 30)
                auth_500 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 500, "username": "sender500"})}
                auth_600 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 600, "username": "target600"})}

                resp = await client.post("/api/messages", headers=auth_500,
                                          json={"recipient_id": 600, "body": "Здравствуйте"})
                check(resp.status == 200,
                      "подписанный 500 пишет НЕподписанному 600 первым -> 200 (подписка проверяется у ОТПРАВИТЕЛЯ)")

                check(not app["storage"].is_subscribed(600), "600 действительно не подписан (для чистоты теста)")
                resp = await client.post("/api/messages", headers=auth_600,
                                          json={"recipient_id": 500, "body": "Добрый день"})
                check(resp.status == 200,
                      "600 БЕЗ подписки отвечает в уже существующем треде -> 200 "
                      "(подписка нужна только чтобы написать первым)")

                resp = await client.get("/api/messages/with/600", headers=auth_500)
                body = await resp.json()
                check(len(body["messages"]) == 2, "в треде 500<->600 два сообщения (от каждого по одному)")

                # пустой (ещё не начатый) тред — can_send_first зависит только от
                # подписки СМОТРЯЩЕГО
                resp = await client.get("/api/messages/with/200", headers=auth_350)
                check(resp.status == 200, "GET /api/messages/with/<id> для несуществующего треда -> 200, просто пусто")
                body = await resp.json()
                check(body["messages"] == [], "треда ещё нет -> пустой список сообщений")
                check(body["can_send_first"] is False, "350 не подписан и треда нет -> can_send_first=False")

                resp = await client.get("/api/messages/with/999999", headers=auth_100)
                check(resp.status == 404, "GET /api/messages/with/<id> для юзера без анкеты -> 404")

                # --- регистрация прямо в приложении (11.09.2026) --------------
                auth_700 = {"Authorization": "tma " + _guro_make_init_data(token, {"id": 700, "username": "newbie"})}

                resp = await client.post("/api/register", headers=auth_700, json={
                    "name": "Юлия Черных", "vertical": "Gambling", "grade": "Senior",
                    "profession": "не та должность",
                })
                check(resp.status == 400, "/api/register: профессия не из справочника этого грейда -> 400")
                body = await resp.json()
                check(body["error"] == "INVALID_PROFESSION", f"код ошибки: {body}")

                real_profession = C.professions_for("Gambling", "Senior")[0][1]
                resp = await client.post("/api/register", headers=auth_700, json={
                    "name": "Юлия Черных", "vertical": "Gambling", "grade": "Senior",
                    "profession": real_profession,
                })
                check(resp.status == 200, f"/api/register с валидными полями -> 200, получено {resp.status}")

                resp = await client.get("/api/me", headers=auth_700)
                check(resp.status == 200, "после регистрации /api/me -> 200 (профиль появился)")
                body = await resp.json()
                check(body["name"] == "Юлия Черных" and body["vertical"] == "Gambling",
                      "/api/me отражает только что созданную анкету")

                resp = await client.post("/api/register", headers=auth_700, json={
                    "name": "Ещё раз", "vertical": "Betting", "grade": "Junior / Entry",
                    "profession": C.professions_for("Betting", "Junior / Entry")[0][1],
                })
                check(resp.status == 409, "повторная регистрация того же user_id -> 409")
                body = await resp.json()
                check(body["error"] == "ALREADY_REGISTERED", f"код ошибки: {body}")

                # профессия хранится МЕТКОЙ (как у бота), не кодом справочника
                row = st.get_profile_by_telegram_id(700)
                check(row["profession"] == real_profession,
                      f"анкета из приложения хранит profession меткой, как бот: {row['profession']!r}")

                # --- скидка первого дня (11.09.2026) ---------------------------
                resp = await client.get("/api/plans?product=guro_id", headers=auth_700)
                check(resp.status == 200, "/api/plans с авторизацией -> 200")
                body = await resp.json()
                monthly = body["plans"]["monthly"]
                check(monthly.get("discount_pct") == 20, f"анкета создана сегодня -> скидка 20%: {monthly}")
                check(monthly["discount_stars_price"] == 320, f"400 - 20% = 320 звёзд: {monthly}")
                check(monthly["discount_crypto_price_usd"] == 4.8, f"$6 - 20% = $4.8: {monthly}")
                check("discount_pct" not in body["plans"]["yearly"],
                      "у годового тарифа своя скидка (-30%), первого дня для него нет")

                # без Authorization эндпойнт остаётся публичным (регрессия)
                resp = await client.get("/api/plans")
                check(resp.status == 200, "/api/plans без Authorization по-прежнему 200 (скидка её не закрыла)")
                body = await resp.json()
                check("discount_pct" not in body["plans"]["monthly"],
                      "без авторизации скидку показать некому -> полей скидки нет")

                # цена в реальном инвойсе Stars — УЖЕ со скидкой
                _FakeTGBot.invoice_calls.clear()
                resp = await client.post("/api/subscribe", headers=auth_700, json={"plan": "monthly"})
                check(resp.status == 200, "/api/subscribe (monthly, скидочный день) -> 200")
                charged = _FakeTGBot.invoice_calls[-1]["prices"][0].amount
                check(charged == 320, f"инвойс выставлен на дисконтированную сумму, не на 400: {charged}")

                # у анкеты со вчерашним created_at скидки уже нет
                st._conn.execute(
                    "UPDATE profiles SET created_at = datetime('now', '-1 day') WHERE user_id = 700"
                )
                st._conn.commit()
                resp = await client.get("/api/plans?product=guro_id", headers=auth_700)
                body = await resp.json()
                check("discount_pct" not in body["plans"]["monthly"],
                      "анкета создана вчера -> скидки первого дня уже нет")

                _FakeTGBot.invoice_calls.clear()
                resp = await client.post("/api/subscribe", headers=auth_700, json={"plan": "monthly"})
                charged = _FakeTGBot.invoice_calls[-1]["prices"][0].amount
                check(charged == 400, f"вчерашняя анкета -> инвойс на полную цену: {charged}")

                # --- баг-фикс 11.09.2026: форма ответа POST /api/anketa --------
                # EditableField (Shared.jsx, общий для CV/сайта/рекрутера/компании/
                # анкеты) после сохранения делает onSaved(updated[field]) — ждёт
                # значение ПОД КЛЮЧОМ ИМЕНИ ПОЛЯ. Раньше /api/anketa отдавал
                # {"field": ..., "value": ...}, updated["name"] был undefined,
                # и поле мгновенно "пустело" на экране сразу после сохранения
                # (при том что в БД значение уже лежало верно — баг-репорт
                # "после заполнения и попытки сохранить данные отображаются как
                # незаполненные, но при переходе туда и обратно всё на месте").
                resp = await client.post("/api/anketa", headers=auth_700,
                                          json={"field": "name", "value": "Новое Имя"})
                check(resp.status == 200, "POST /api/anketa (текстовое поле) -> 200")
                body = await resp.json()
                check(body.get("name") == "Новое Имя",
                      f"ответ отдаёт значение ПОД КЛЮЧОМ ИМЕНИ ПОЛЯ (контракт EditableField.onSaved(updated[field])), получено: {body}")
                check("field" not in body and "value" not in body,
                      f"старая форма {{'field':..,'value':..}} действительно убрана: {body}")

                resp = await client.post("/api/anketa", headers=auth_700,
                                          json={"field": "vertical", "value": "Betting"})
                check(resp.status == 200, "POST /api/anketa (справочное поле vertical) -> 200")
                body = await resp.json()
                check(body.get("vertical") == "Betting", f"то же самое для справочных полей: {body}")
            finally:
                await client.close()


async def _run_guro_partnerships_sim():
    print("== guro_id: bot-side partnership/payment handlers ==")
    import sqlite3
    import tempfile
    from datetime import datetime, timedelta, timezone

    from guro_storage import GuroStorage
    from handlers.guro_partnerships import cb_guro_partnership_response
    from handlers.guro_payments import on_guro_pre_checkout, on_guro_successful_payment

    with tempfile.TemporaryDirectory() as d:
        bot_data = _bot_data(d)
        storage = bot_data["storage"]
        db_path = bot_data["settings"].database_path
        storage.save_profile({"user_id": 1, "username": "alice", "name": "Alice"})
        storage.save_profile({"user_id": 2, "username": "bob", "name": "Bob"})
        storage.save_profile({"user_id": 3, "username": "carl", "name": "Carl"})

        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE profiles SET created_at=?", (old_ts,))
        conn.commit()
        conn.close()

        gstorage = GuroStorage(db_path)
        p12 = gstorage.create_partnership(1, 2, "casino", None)
        p13 = gstorage.create_partnership(1, 3, "casino", None)

        context = FakeContext(bot_data)

        # ответ не от confirmer -> alert, ничего не меняется
        wrong_q = FakeQuery(f"guro:confirm:{p12['id']}", chat_id=1)
        wrong_q.from_user = FakeUser(1, "alice")
        await cb_guro_partnership_response(FakeUpdate(query=wrong_q, user=wrong_q.from_user), context)
        check(wrong_q.answered and "не вам" in (wrong_q.last_answer_text or ""),
              "confirm не тем пользователем -> alert 'не вам'")

        # confirm от настоящего confirmer
        ok_q = FakeQuery(f"guro:confirm:{p12['id']}", chat_id=2)
        ok_q.from_user = FakeUser(2, "bob")
        await cb_guro_partnership_response(FakeUpdate(query=ok_q, user=ok_q.from_user), context)
        check(ok_q.answered, "confirm от confirmer -> answer()")
        check("подтверждено" in ok_q.message.text, "confirm -> сообщение обновлено на подтверждение")
        check(any("подтвердил" in t for _, t in context.bot.sent), "инициатор уведомлён о подтверждении")
        check(gstorage.get_partnership(p12["id"])["status"] == "confirmed", "статус партнёрства -> confirmed")
        # 25.08.2026, формула v2: без активной подписки у обеих сторон
        # партнёрство подтверждается (видно, счётчик сделок растёт), но не
        # учитывается в рейтинге — этот сценарий отдельно и подробно
        # покрыт в test_guro_id_storage/test_guro_id_reputation_formula,
        # тут просто убеждаемся, что bot-side confirm не падает и не считает
        # молча вопреки правилу.
        check(gstorage.get_partnership(p12["id"])["counts_toward_rating"] == 0,
              "без активной подписки сторон -> НЕ учитывается в рейтинге, даже у старых аккаунтов")

        # повторный confirm -> already resolved
        repeat_q = FakeQuery(f"guro:confirm:{p12['id']}", chat_id=2)
        repeat_q.from_user = FakeUser(2, "bob")
        await cb_guro_partnership_response(FakeUpdate(query=repeat_q, user=repeat_q.from_user), context)
        check("Уже обработано" in (repeat_q.last_answer_text or ""), "повторный confirm -> alert 'уже обработано'")

        # decline другого партнёрства
        decline_q = FakeQuery(f"guro:decline:{p13['id']}", chat_id=3)
        decline_q.from_user = FakeUser(3, "carl")
        await cb_guro_partnership_response(FakeUpdate(query=decline_q, user=decline_q.from_user), context)
        check("отклонено" in decline_q.message.text, "decline -> сообщение обновлено на отклонение")
        check(gstorage.get_partnership(p13["id"])["status"] == "declined", "статус партнёрства -> declined")
        check(any("отклонил" in t for _, t in context.bot.sent), "инициатор уведомлён об отклонении")

        # pre_checkout / successful_payment
        class _FakePreCheckout:
            def __init__(self, payload):
                self.invoice_payload = payload
                self.answered_ok = None

            async def answer(self, ok=True, **kw):
                self.answered_ok = ok

        class _Ns:
            pass

        u_ours = _Ns()
        u_ours.pre_checkout_query = _FakePreCheckout("guro_id_subscription:monthly:1")
        await on_guro_pre_checkout(u_ours, context)
        check(u_ours.pre_checkout_query.answered_ok is True, "pre_checkout нашего payload -> answer(ok=True)")

        u_other = _Ns()
        u_other.pre_checkout_query = _FakePreCheckout("some_other_flow:1")
        await on_guro_pre_checkout(u_other, context)
        check(u_other.pre_checkout_query.answered_ok is None, "pre_checkout чужого payload -> не отвечаем")

        class _FakeSuccessfulPayment:
            def __init__(self, payload):
                self.invoice_payload = payload

        replies = []
        msg = FakeMessage("", chat_id=1)
        # план "yearly" в payload -> должна примениться длительность 365 дней,
        # а не дефолтные 30 (проверка на _plan_from_payload в guro_payments.py)
        msg.successful_payment = _FakeSuccessfulPayment("guro_id_subscription:yearly:1")

        async def _capture_reply(text, **kw):
            replies.append(text)

        msg.reply_text = _capture_reply
        u_payment = _Ns()
        u_payment.message = msg
        u_payment.effective_user = FakeUser(1, "alice")
        await on_guro_successful_payment(u_payment, context)
        check(gstorage.is_subscribed(1), "successful_payment -> подписка активирована")
        _status, _expires_at = gstorage.get_subscription(1)
        days_left = (_expires_at - datetime.now(timezone.utc)).days
        check(days_left > 300, f"план yearly -> подписка на ~365 дней, а не 30 (осталось {days_left} дн.)")
        check(any("активирована" in t for t in replies), "successful_payment -> подтверждение юзеру")
        import guro_constants as GC
        check((bot_data["settings"].community_chat_id, 1, GC.GURO_TAG) in context.bot.set_tag_calls,
              "successful_payment -> тег GURO ID появляется в чате")

        # Кабинет рекрутера (Фаза 3, 12.08.2026) — тот же bot-side хендлер,
        # другой продукт по префиксу payload, отдельная подписка/таблица.
        msg2 = FakeMessage("", chat_id=2)
        msg2.successful_payment = _FakeSuccessfulPayment("guro_id_recruiter_subscription:yearly:2")
        replies2 = []

        async def _capture_reply2(text, **kw):
            replies2.append(text)

        msg2.reply_text = _capture_reply2
        u_payment2 = _Ns()
        u_payment2.message = msg2
        u_payment2.effective_user = FakeUser(2, "bob")
        await on_guro_successful_payment(u_payment2, context)
        check(gstorage.is_recruiter_subscribed(2), "successful_payment recruiter -> подписка рекрутера активирована")
        check(not gstorage.is_subscribed(2),
              "recruiter-подписка НЕ активирует базовую GURO ID подписку (разные продукты/таблицы)")
        check(any("рекрутера" in t for t in replies2), "successful_payment recruiter -> подтверждение про кабинет")
        check(not any(c[1] == 2 for c in context.bot.set_tag_calls),
              "recruiter-подписка не трогает статус-тег в чате (тот привязан только к базовой подписке)")

        # Кабинет "Компания" (Фаза 5, 17.08.2026; 27.08.2026 — payload-префикс
        # разделён на company_basic/company_pro, ТЗ "Тарифы и лимиты") — та
        # же bot-side цепочка, оба тира пишут в ОДНУ таблицу company_profiles.
        msg3 = FakeMessage("", chat_id=3)
        msg3.successful_payment = _FakeSuccessfulPayment("guro_id_company_basic_subscription:yearly:3")
        replies3 = []

        async def _capture_reply3(text, **kw):
            replies3.append(text)

        msg3.reply_text = _capture_reply3
        u_payment3 = _Ns()
        u_payment3.message = msg3
        u_payment3.effective_user = FakeUser(3, "carol")
        await on_guro_successful_payment(u_payment3, context)
        check(gstorage.is_company_subscribed(3), "successful_payment company_basic -> подписка компании активирована")
        check(not gstorage.is_subscribed(3),
              "company-подписка НЕ активирует базовую GURO ID подписку (разные продукты/таблицы)")
        check(any("компании" in t for t in replies3), "successful_payment company_basic -> подтверждение про кабинет")
        check(gstorage.get_company_tier(3) == "basic", "successful_payment company_basic -> тир 'basic'")
        check(not any(c[1] == 3 for c in context.bot.set_tag_calls),
              "company-подписка не трогает статус-тег в чате (тот привязан только к базовой подписке)")

        msg4 = FakeMessage("", chat_id=4)
        msg4.successful_payment = _FakeSuccessfulPayment("guro_id_company_pro_subscription:yearly:4")
        replies4 = []

        async def _capture_reply4(text, **kw):
            replies4.append(text)

        msg4.reply_text = _capture_reply4
        u_payment4 = _Ns()
        u_payment4.message = msg4
        u_payment4.effective_user = FakeUser(4, "dave")
        await on_guro_successful_payment(u_payment4, context)
        check(gstorage.is_company_subscribed(4), "successful_payment company_pro -> подписка компании активирована")
        check(gstorage.get_company_tier(4) == "pro", "successful_payment company_pro -> тир 'pro'")


async def _run_guro_tags_sim():
    print("== guro_id: статус-тег в чате (guro_tags) ==")
    import tempfile
    from pathlib import Path
    from telegram.constants import ChatMemberStatus

    import guro_constants as GC
    import guro_tags as GT
    from guro_storage import GuroStorage
    from storage import Storage

    CHAT = -100999888777

    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "t.sqlite3"
        Storage(db_path)  # создаёт таблицу profiles (её читает get_or_create_guro_user)
        gstorage = GuroStorage(db_path)
        bot = FakeBot()

        gstorage.get_or_create_guro_user(10)
        await GT.sync_member_tag(bot, CHAT, gstorage, 10, reason="test")
        check(len(bot.set_tag_calls) == 0,
              "новый guro_user без подписки -> тега нет (заход в Mini App сам по себе тег не даёт)")

        gstorage.activate_subscription(10, 30)
        await GT.sync_member_tag(bot, CHAT, gstorage, 10, reason="test")
        check((CHAT, 10, GC.GURO_TAG) in bot.set_tag_calls,
              "оплаченная подписка -> появляется тег GURO ID")

        # тег уже актуален -> повторный вызов ничего не шлёт
        calls_before = len(bot.set_tag_calls)
        await GT.sync_member_tag(bot, CHAT, gstorage, 10, reason="test")
        check(len(bot.set_tag_calls) == calls_before, "тег уже актуален -> повторный вызов no-op")

        # подписка истекла -> тег снимается (единственное место, где это обнаруживается —
        # периодическая синхронизация, guro_tags_sync.py)
        gstorage._conn.execute(
            "UPDATE guro_users SET subscription_expires_at=? WHERE user_id=?",
            ("2000-01-01 00:00:00", 10),
        )
        gstorage._conn.commit()
        await GT.sync_member_tag(bot, CHAT, gstorage, 10, reason="test")
        check((CHAT, 10, "") in bot.set_tag_calls, "истёкшая подписка -> тег снимается")
        check(not bot.member_tag_map.get(10), "после истечения подписки тега у юзера больше нет")

        # админа/овнера не трогаем, даже если он подписан (у них уже своя вкладка custom title)
        gstorage.get_or_create_guro_user(11)
        gstorage.activate_subscription(11, 30)
        bot.member_status_map[11] = ChatMemberStatus.ADMINISTRATOR
        await GT.sync_member_tag(bot, CHAT, gstorage, 11, reason="test")
        check(11 not in bot.member_tag_map, "администратора группы не трогаем")

        # ручной тег участника не перетираем
        gstorage.get_or_create_guro_user(12)
        bot.member_tag_map[12] = "мой тег"
        await GT.sync_member_tag(bot, CHAT, gstorage, 12, reason="test")
        check(bot.member_tag_map[12] == "мой тег", "ручной (не наш) тег участника не перетирается")

        # chat_id не настроен -> no-op, без падения
        await GT.sync_member_tag(bot, 0, gstorage, 10, reason="test")

        # sync_all_members обходит список целиком (тег появляется только у подписанных)
        gstorage.get_or_create_guro_user(20)
        gstorage.activate_subscription(20, 30)
        gstorage.get_or_create_guro_user(21)  # без подписки
        bot2 = FakeBot()
        await GT.sync_all_members(bot2, CHAT, gstorage, [20, 21], reason="bulk")
        check((CHAT, 20, GC.GURO_TAG) in bot2.set_tag_calls, "sync_all_members -> тег подписанному")
        check(not any(c[1] == 21 for c in bot2.set_tag_calls), "sync_all_members -> без подписки тег не ставится")


async def _run_admin_guro_sim():
    print("== guro_id: admin dashboard (acms_guro) ==")
    import tempfile
    from pathlib import Path

    import guro_constants as GC
    from handlers import admin_guro

    with tempfile.TemporaryDirectory() as d:
        bot_data = _bot_data(d)
        bot_data["storage"].save_profile({"user_id": 1, "username": "alice", "name": "Alice"})
        bot_data["storage"].save_profile({"user_id": 2, "username": "bob", "name": "Bob"})
        gstorage = bot_data["guro_storage"]
        gstorage.create_partnership(1, 2, "casino", None)

        ctx = FakeContext(bot_data)
        ctx.user_data["adm_chat"] = 555
        ctx.user_data["adm_mid"] = 9101
        q = FakeQuery("acms_guro", chat_id=555)
        q.from_user = FakeUser(1417059280, "owner")
        update = FakeUpdate(query=q, user=q.from_user)

        state = await admin_guro.nav_guro(update, ctx)
        check(q.answered, "nav_guro отвечает на callback_query")
        check(state == 0, "nav_guro возвращает BROWSE (0)")
        check("GURO ID" in (ctx.bot.last_text or ""), "дашборд содержит заголовок GURO ID")
        check("Партнёрств всего" in (ctx.bot.last_text or ""), "дашборд содержит блок партнёрств")
        check("1" in (ctx.bot.last_text or ""), "дашборд отражает 1 партнёрство (свежие аккаунты — не в рейтинге, но в счётчике)")
        check("/guro_limit" in (ctx.bot.last_text or ""), "дашборд подсказывает команду /guro_limit")
        check("USDT" not in (ctx.bot.last_text or ""),
              "без настроенного crypto-токена строки про крипту в дашборде нет")

        # --- «Получено в USDT» (11.09.2026) --------------------------------
        import guro_crypto as GCR
        from unittest import mock

        bot_data["settings"].cryptobot_api_token = "old-token"
        captured_token = {}

        async def _fake_get_paid_total(api_token, asset):
            captured_token["token"] = api_token
            return 123.45

        with mock.patch.object(GCR, "get_paid_total", _fake_get_paid_total):
            state = await admin_guro.nav_guro(update, ctx)
        check(captured_token.get("token") == "old-token",
              "единственный настроенный токен -> он же 'бизнес' (личной доли ещё нет)")
        check("💰 Получено в USDT (крипта): 123.45" in (ctx.bot.last_text or ""),
              f"строка с суммой в USDT появилась в дашборде: {ctx.bot.last_text!r}")

        # оба токена настроены -> считаем НОВЫЙ ("бизнес"), не старый
        # (личная доля владельца) — тот же принцип, что у active_subscriptions
        bot_data["settings"].cryptobot_api_token_new = "new-token"
        with mock.patch.object(GCR, "get_paid_total", _fake_get_paid_total):
            await admin_guro.nav_guro(update, ctx)
        check(captured_token.get("token") == "new-token",
              "при двух токенах в статистику идёт НОВЫЙ (бизнес), не личная доля владельца")

        async def _boom_get_paid_total(api_token, asset):
            raise GCR.CryptoBotError("boom")

        with mock.patch.object(GCR, "get_paid_total", _boom_get_paid_total):
            state = await admin_guro.nav_guro(update, ctx)
        check(state == 0 and "USDT" not in (ctx.bot.last_text or ""),
              "сбой CryptoBot API -> дашборд не падает, просто без строки крипты")

        bot_data["settings"].cryptobot_api_token = ""
        bot_data["settings"].cryptobot_api_token_new = ""

        # --- /guro_limit — оверрайд лимитов на аккаунт (ТЗ "Тарифы и
        # лимиты", раздел 3, 27.08.2026) --------------------------------
        def _cmd(args):
            replies = []
            msg = FakeMessage("/guro_limit", chat_id=555)

            async def _capture(text, **kw):
                replies.append(text)

            msg.reply_text = _capture
            ctx2 = FakeContext(bot_data)
            ctx2.args = args
            upd = FakeUpdate(message=msg, user=FakeUser(1417059280, "owner"))
            return upd, ctx2, replies

        upd, ctx2, replies = _cmd([])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("Тарифы и лимиты" in r for r in replies), "/guro_limit без аргументов -> список текущих значений")
        check(any(GC.LIMIT_KEY_VIEWS_RECRUITER in r for r in replies), "листинг включает все известные ключи")

        upd, ctx2, replies = _cmd(["777"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("нет персональных оверрайдов" in r for r in replies), "/guro_limit <user_id> без оверрайдов -> честный ответ")

        upd, ctx2, replies = _cmd(["777", "not_a_key", "5"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("Формат" in r for r in replies), "неизвестный ключ -> подсказка формата, не падение")
        check(gstorage.get_user_limit_override(777, "not_a_key") is None, "невалидный ключ не записался")

        upd, ctx2, replies = _cmd(["777", GC.LIMIT_KEY_VIEWS_RECRUITER, "7"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("✅" in r for r in replies), "/guro_limit <id> <key> <value> -> подтверждение")
        check(gstorage.get_user_limit_override(777, GC.LIMIT_KEY_VIEWS_RECRUITER) == 7,
              "оверрайд реально записан в guro_user_limit_overrides")

        upd, ctx2, replies = _cmd(["777"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any(f"{GC.LIMIT_KEY_VIEWS_RECRUITER} = 7" in r for r in replies),
              "/guro_limit <user_id> теперь показывает записанный оверрайд")

        upd, ctx2, replies = _cmd(["777", GC.LIMIT_KEY_VIEWS_RECRUITER, "reset"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("снят" in r for r in replies), "reset -> снимает оверрайд")
        check(gstorage.get_user_limit_override(777, GC.LIMIT_KEY_VIEWS_RECRUITER) is None,
              "после reset оверрайда больше нет")

        upd, ctx2, replies = _cmd(["global", GC.LIMIT_KEY_NEW_VACANCIES, "9"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(gstorage.get_config(GC.LIMIT_KEY_NEW_VACANCIES, -1) == 9,
              "/guro_limit global <key> <value> -> меняет глобальный дефолт")

        upd, ctx2, replies = _cmd(["not_a_number"])
        await admin_guro.guro_limit_command(upd, ctx2)
        check(any("числом" in r for r in replies), "нечисловой user_id -> понятная ошибка, не падение")

        # --- верификация компании из /admin (ТЗ "Компания. каб", раздел 2) -
        gstorage.get_or_create_company_profile(500)
        gstorage.set_company_extra_field(500, "name", "Verify Me Ltd")
        gstorage.request_company_verification(500)
        q2 = FakeQuery("acms_guro_companyverify", chat_id=555)
        q2.from_user = FakeUser(1417059280, "owner")
        update2 = FakeUpdate(query=q2, user=q2.from_user)
        state2 = await admin_guro.nav_guro_company_verify(update2, ctx)
        check(state2 == 0, "nav_guro_company_verify возвращает BROWSE")
        check("Verify Me Ltd" in (ctx.bot.last_text or ""), "компания, подавшая заявку, видна в списке на верификацию")

        q3 = FakeQuery("guro_cv_on:500", chat_id=555)
        q3.from_user = FakeUser(1417059280, "owner")
        update3 = FakeUpdate(query=q3, user=q3.from_user)
        await admin_guro.guro_company_verify_toggle(update3, ctx)
        check(gstorage.is_company_verified(500), "guro_cv_on:<id> -> бейдж верификации включён")
        check(q3.answered, "callback отвечен (второй, безаргументный .answer() внутри nav_guro_company_verify "
              "перетирает last_answer_text — тот же паттерн, что у guro_addr_review, не баг)")


async def _run_paywall_sim():
    print("== платный вход в сообщество (09.09.2026) ==")
    import tempfile
    from datetime import timedelta

    import community_access as CA
    import guro_crypto as GCR
    import guro_logic as GL
    import ui
    from handlers import admin_guro, admin_profiles, flow, guro_payments, paywall

    with tempfile.TemporaryDirectory() as d:
        bot_data = _bot_data(d)
        st, gst, content = bot_data["storage"], bot_data["guro_storage"], bot_data["content"]
        # 1 — старый участник (освобождён), 2 — новый, 3 — новый, но уже оплатил в приложении
        for uid, uname in ((1, "old"), (2, "newbie"), (3, "prepaid")):
            st.save_profile({"user_id": uid, "username": uname, "name": uname})
        st.grant_community_access(1)
        gst.activate_subscription(3, 30)

        # --- признак и развилка ---------------------------------------
        check(st.has_community_access(1) and not st.has_community_access(2), "признак: у старого есть, у нового нет")
        check(not st.grant_community_access(999), "выдача без анкеты -> False (нечему выдавать)")
        ctx = FakeContext(bot_data)
        check(not flow._needs_payment(ctx, 1), "освобождённый -> оплата не нужна")
        check(flow._needs_payment(ctx, 2), "новый без подписки -> экран оплаты")
        check(not flow._needs_payment(ctx, 3), "оплатил в приложении до конца анкеты -> экран оплаты НЕ показываем")
        st.revoke_community_access(1)
        check(flow._needs_payment(ctx, 1), "снятие освобождения возвращает под общее правило")
        st.grant_community_access(1)

        # --- кнопки экрана оплаты -------------------------------------
        kb = ui.paywall_kb(content)
        labels = kb_texts(kb)
        check(labels[0].startswith("Криптой") and labels[1].startswith("Криптой"), f"крипта первой (приоритет владельца): {labels}")
        check(labels[-1] == "Оплачу позже", "последняя кнопка — «Оплачу позже»")
        datas = [b.callback_data for row in kb.inline_keyboard for b in row]
        check(datas[0] == "paywall:crypto:monthly" and datas[2] == "paywall:stars:monthly", f"callback_data самодостаточна: {datas}")

        async def _press(data, uid=2):
            q = FakeQuery(data, chat_id=uid)
            q.from_user = FakeUser(uid, "newbie")
            upd = FakeUpdate(query=q, user=q.from_user)
            c2 = FakeContext(bot_data)
            await paywall.on_paywall(upd, c2)
            return c2

        c2 = await _press("paywall:later")
        check(any(content.txt("paywall_later") == t for _, t in c2.bot.sent), "«Оплачу позже» -> текст с точкой возврата")
        check("Оплачу позже" in kb_texts(c2.bot.last_send_kwargs.get("reply_markup")), "«Оплачу позже» -> под ответом те же кнопки оплаты")

        c2 = await _press("paywall:stars:monthly")
        inv = getattr(c2.bot, "invoices", [])
        check(len(inv) == 1 and inv[0][1]["currency"] == "XTR", "звёзды -> нативный инвойс XTR")
        check(inv[0][1]["payload"] == "guro_id_subscription:monthly:2",
              f"payload тот же, что у приложения (иначе подтверждение никто не обработает): {inv[0][1]['payload']}")
        check(inv[0][1]["prices"][0].amount == 400, "цена месяца = 400 звёзд")

        c2 = await _press("paywall:stars:bogus")
        check(not getattr(c2.bot, "invoices", []) and not c2.bot.sent, "неизвестный план -> ничего не шлём, не падаем")

        c2 = await _press("paywall:crypto:yearly")
        check(any("недоступна" in t for _, t in c2.bot.sent), "крипта не настроена -> подсказка платить звёздами, не 500")

        bot_data["settings"].cryptobot_api_token = "tok"
        captured = {}

        async def _fake_create_invoice(api_token, **kw):
            captured.update(kw, token=api_token)
            return {"invoice_id": 7, "pay_url": "https://t.me/CryptoBot?start=IV7"}

        real_create = GCR.create_invoice
        GCR.create_invoice = _fake_create_invoice
        try:
            c2 = await _press("paywall:crypto:yearly")
        finally:
            GCR.create_invoice = real_create
        check(captured.get("payload") == "guro_id_subscription:yearly:2", f"крипта: payload приложения: {captured.get('payload')}")
        check(captured.get("amount") == 50.25 and captured.get("asset") == "USDT", f"крипта: год = 50.25 USDT: {captured}")
        mk = c2.bot.last_send_kwargs.get("reply_markup")
        check(mk and mk.inline_keyboard[0][0].url == "https://t.me/CryptoBot?start=IV7", "крипта: кнопка ведёт на pay_url")
        bot_data["settings"].cryptobot_api_token = ""

        # --- выдача после оплаты звёздами -----------------------------
        class _Pay:
            def __init__(self, payload):
                self.invoice_payload = payload

        async def _paid(uid):
            msg = FakeMessage("", chat_id=uid)
            msg.successful_payment = _Pay(f"guro_id_subscription:monthly:{uid}")
            upd = FakeUpdate(message=msg, user=FakeUser(uid, "u"))
            c3 = FakeContext(bot_data)
            await guro_payments.on_guro_successful_payment(upd, c3)
            return c3

        c3 = await _paid(2)
        check(gst.is_subscribed(2), "оплата звёздами активирует подписку")
        check(len(c3.bot.invite_links) == 1 and c3.bot.invite_links[0][1] == 1, "новому после оплаты -> ОДНОРАЗОВАЯ ссылка в группу")
        check(any(content.txt("paywall_granted") == t for _, t in c3.bot.sent), "новому после оплаты -> текст «оплата получена»")
        check(not st.has_community_access(2), "оплата НЕ ставит признак освобождения (иначе выселение не сработает)")
        c3 = await _paid(1)
        check(not c3.bot.invite_links, "освобождённому после продления ссылку НЕ шлём — он уже в группе")

        # --- выборки задания: напоминание и выселение ------------------
        now = gst._now()
        fmt = GL.format_db_datetime

        def _set_exp(uid, dt, status="active"):
            gst.get_or_create_guro_user(uid)
            gst._conn.execute("UPDATE guro_users SET subscription_status=?, subscription_expires_at=? WHERE user_id=?",
                              (status, fmt(dt), uid))
            gst._conn.commit()

        st.save_profile({"user_id": 4, "username": "later", "name": "later"})  # «Оплачу позже», ни разу не платил
        gst.get_or_create_guro_user(4)
        _set_exp(1, now - timedelta(days=3))            # освобождённый с истёкшей подпиской
        _set_exp(2, now + timedelta(days=1))            # новый, истекает завтра
        _set_exp(3, now - timedelta(hours=1))           # новый, истёк час назад

        exp_ids = [r["user_id"] for r in gst.list_paywall_expiring(2)]
        check(exp_ids == [2], f"напомнить только тому, чей срок в окне 2 дней и кто не освобождён: {exp_ids}")
        gst.mark_paywall_reminded(2, fmt(now + timedelta(days=1)))
        check(gst.list_paywall_expiring(2) == [], "об одном сроке напоминаем один раз")

        kick_ids = [r["user_id"] for r in gst.list_paywall_expired()]
        check(kick_ids == [3], f"выселить только неосвобождённого с истёкшей подпиской: {kick_ids}")
        check(4 not in kick_ids, "«Оплачу позже» без единой оплаты не выселяется — его в группе нет")
        check(1 not in kick_ids, "освобождённый с истёкшей подпиской НЕ выселяется")
        gst.mark_paywall_kicked(3, fmt(now - timedelta(hours=1)))
        check(gst.list_paywall_expired() == [], "по одному сроку выселяем один раз")
        gst.activate_subscription(3, 30)
        _set_exp(3, now - timedelta(minutes=5))
        check([r["user_id"] for r in gst.list_paywall_expired()] == [3],
              "новый оплаченный цикл с новым сроком -> отметка о прошлом выселении не мешает")

        fb = FakeBot()
        ok = await CA.revoke_access(fb, bot_data["settings"], 3)
        check(ok and fb.bans == [(-100999888777, 3)] and fb.unbans[0][2] is True,
              "выселение = ban + unban(only_if_banned): кик без вечного бана")

        # --- админ: пустить без оплаты -----------------------------------
        pid = st._conn.execute("SELECT id FROM profiles WHERE user_id=4").fetchone()[0]
        ctx4 = FakeContext(bot_data)
        ctx4.user_data["adm_chat"], ctx4.user_data["adm_mid"] = 555, 1
        q = FakeQuery(f"acms_pf_access:{pid}", chat_id=555)
        q.from_user = FakeUser(42, "admin")
        await admin_profiles.pf_toggle_access(FakeUpdate(query=q, user=q.from_user), ctx4)
        check(st.has_community_access(4), "кнопка карточки -> признак освобождения поставлен")
        check(len(ctx4.bot.invite_links) == 1 and any(content.txt("paywall_admin_granted") == t for _, t in ctx4.bot.sent),
              "кнопка карточки -> человеку сразу уходит одноразовая ссылка")
        check("без оплаты" in (ctx4.bot.last_text or ""), "карточка после выдачи показывает «🎟 без оплаты»")
        check(any("Снять доступ без оплаты" in t for t in kb_texts(ctx4.bot.last_markup)), "кнопка переключилась на снятие")
        logs = st._conn.execute("SELECT action FROM admin_audit_log WHERE action LIKE 'community_access%'").fetchall()
        check([r[0] for r in logs] == ["community_access_grant"], f"выдача записана в журнал действий: {[r[0] for r in logs]}")

        await admin_profiles.pf_toggle_access(FakeUpdate(query=q, user=q.from_user), ctx4)
        check(not st.has_community_access(4), "второе нажатие снимает освобождение")
        check(any("Пустить без оплаты" in t for t in kb_texts(ctx4.bot.last_markup)), "кнопка вернулась к выдаче")

        replies = []
        msg = FakeMessage("/guro_access", chat_id=555)

        async def _cap(text, **kw):
            replies.append(text)

        msg.reply_text = _cap
        ctx5 = FakeContext(bot_data)
        ctx5.args = ["4"]
        await admin_guro.guro_access_command(FakeUpdate(message=msg, user=FakeUser(42, "admin")), ctx5)
        check(st.has_community_access(4) and "выдан" in replies[-1], f"/guro_access <id> выдаёт доступ: {replies[-1]}")
        ctx5.args = ["999"]
        await admin_guro.guro_access_command(FakeUpdate(message=msg, user=FakeUser(42, "admin")), ctx5)
        check("Анкеты нет" in replies[-1], "/guro_access без анкеты -> понятный ответ")
        ctx5.args = ["4", "revoke"]
        await admin_guro.guro_access_command(FakeUpdate(message=msg, user=FakeUser(42, "admin")), ctx5)
        check(not st.has_community_access(4), "/guro_access <id> revoke снимает")


def main():
    test_data()
    test_logic()
    test_storage()
    test_country_formatter()
    test_gossip_storage()
    test_news_storage()
    test_greeting_video_pool()
    test_admin_panel_storage()
    test_cms_storage()
    test_captcha_logic()
    test_menu()
    test_persistence()
    test_admin_start_entry_point()
    test_guro_id_init_data()
    test_guro_id_reputation_formula()
    test_guro_id_storage()
    test_guro_id_recruiter_dashboard()
    asyncio.run(_run_scenarios())
    asyncio.run(_run_lang())
    asyncio.run(_run_admin_cms())
    asyncio.run(_run_captcha_sim())
    asyncio.run(_run_gossip_sim())
    asyncio.run(_run_news_sim())
    asyncio.run(_run_news_poster_sim())
    asyncio.run(_run_referral_group_sim())
    asyncio.run(_run_admin_panel_sim())
    asyncio.run(_run_guro_id_api_sim())
    asyncio.run(_run_guro_partnerships_sim())
    asyncio.run(_run_guro_tags_sim())
    asyncio.run(_run_admin_guro_sim())
    asyncio.run(_run_paywall_sim())
    print(f"\nPASS={PASS} FAIL={FAIL}")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
