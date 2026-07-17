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
        self.edits = 0
        self.sent = []

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
        return True

    async def send_message(self, chat_id, text="", **kw):
        self.sent.append((chat_id, text))
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

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, **kw):
        self.restricts = getattr(self, "restricts", [])
        self.restricts.append((chat_id, user_id, permissions))
        return True

    async def get_chat(self, chat_id):
        class _FakeChat:
            permissions = None
        return _FakeChat()


class FakeUser:
    def __init__(self, uid=42, username="tester"):
        self.id = uid
        self.username = username


class FakeChat:
    def __init__(self, chat_id=555, chat_type="private"):
        self.id = chat_id
        self.type = chat_type


class FakeUpdate:
    def __init__(self, message=None, query=None, user=None):
        self.message = message
        self.callback_query = query
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
    )
    from google_sheets_sync import SheetSync
    from content import Content
    storage = Storage(settings.database_path)
    return {
        "settings": settings,
        "storage": storage,
        "sheet": SheetSync(settings),
        "content": Content(storage),
    }


async def _run_scenarios():
    print("== flow simulation ==")
    import handlers.flow as F

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

        st = await F.pick_grade(FakeUpdate(query=FakeQuery("g:0")), ctx)
        check(st == F.S.PROFESSION, "A: grade C-Level -> PROFESSION")

        st = await F.profession_page(FakeUpdate(query=FakeQuery("pg:1")), ctx)
        check(st == F.S.PROFESSION and ctx.user_data["page"] == 1, "A: pagination")

        st = await F.pick_profession(FakeUpdate(query=FakeQuery("p:0")), ctx)
        check(st == F.S.REQUEST and ctx.user_data["profile"]["profession"], "A: profession picked")

        st = await F.request_text(FakeUpdate(message=FakeMessage("ищу партнёров")), ctx)
        check(st == F.S.NAME, "A: request -> NAME")
        st = await F.name_text(FakeUpdate(message=FakeMessage("Иван")), ctx)
        check(st == F.S.COMPANY, "A: name -> COMPANY")
        st = await F.company_text(FakeUpdate(message=FakeMessage("Acme")), ctx)
        check(st == F.S.LINKEDIN, "A: company -> LINKEDIN")
        st = await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "A: finish END")

        rows = bd["storage"].all_profiles()
        check(len(rows) == 1, "A: одна анкета в БД")
        p = rows[0]
        check(p["vertical"] == "Gambling" and p["grade"] == "C-Level", "A: поля анкеты")
        check(p["linkedin"] == C.SKIPPED_VALUE, "A: linkedin пропущен")
        check(len(ctx.bot.sent) >= 1, "A: уведомление админу отправлено")

    # --- сценарий B: инвестор-ветка (Gambling) ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
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
        await F.company_text(FakeUpdate(message=FakeMessage("Fund X")), ctx)
        st = await F.linkedin_text(FakeUpdate(message=FakeMessage("linkedin.com/in/x")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "B: finish END")
        p = bd["storage"].all_profiles()[0]
        check(p["grade"] == "Инвестор" and p["investor_type"] and p["investor_amount"], "B: инвестор-поля")
        check(p["investor_needs"] == logic.needs_to_text([0, 2]), "B: needs текст")
        check(not p["profession"], "B: профессия пуста у инвестора")

    # --- сценарий C: Other-вертикаль + Другое-профессия + back ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)
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
        await F.company_text(FakeUpdate(message=FakeMessage("NDA")), ctx)
        await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        p = bd["storage"].all_profiles()[0]
        check(p["profession"] == "Growth Lead", "C: своя профессия сохранена")

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

    # --- сценарий E: админ жмёт /start — сразу справка, анкета не показывается ---
    with tempfile.TemporaryDirectory() as d:
        bd = _bot_data(d)  # admin_ids=(42,) — дефолтный FakeUser() как раз id=42
        ctx = FakeContext(bd)
        u = FakeUpdate(message=FakeMessage("/start"))
        st = await F.start(u, ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "E: админ /start -> END, без анкеты")
        check(u.message.deleted, "E: команда /start у админа тоже удаляется (Clean Chat)")
        admin_texts = [t for cid, t in ctx.bot.sent if "/admin" in t]
        check(len(admin_texts) == 1, "E: админу прислана справка с командами")
        check(bd["storage"].count() == 0, "E: анкета за админом не создалась")


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
        check(st == F.S.COMPANY, "EN: name -> COMPANY")
        st = await F.company_text(FakeUpdate(message=FakeMessage("Acme")), ctx)
        check(st == F.S.LINKEDIN, "EN: company -> LINKEDIN")
        st = await F.linkedin_skip(FakeUpdate(query=FakeQuery("skip_li")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "EN: finish END")
        check(len(bd["storage"].all_profiles()) == 1, "EN: анкета сохранена")
        fkb = ui.final_kb(bd["content"].view("ru"), "https://t.me/x")
        fbd = fkb.inline_keyboard[0][0].to_dict()
        check(fbd.get("style") == "primary", "кнопка «Вступить» синяя по умолчанию")
        check(fbd.get("icon_custom_emoji_id") == C.JOIN_BUTTON_EMOJI_ID,
              "кнопка «Вступить» с премиум-иконкой (ракета)")
        wbd = ui.welcome_kb(bd["content"].view("ru")).inline_keyboard[0][0].to_dict()
        check(wbd.get("style") == "primary"
              and wbd.get("icon_custom_emoji_id") == C.START_BUTTON_EMOJI_ID,
              "кнопка «Получить доступ»: синяя + звезда")


async def _run_admin_cms():
    print("== admin cms simulation ==")
    import handlers.admin_cms as A
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

        st = await A.admin_exit(FakeUpdate(query=FakeQuery("acms_exit")), ctx)
        from telegram.ext import ConversationHandler
        check(st == ConversationHandler.END, "cms: выход END")

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
        check(kb is not None
              and sum(len(r) for r in kb.inline_keyboard) == enabled_n
              and len(kb.inline_keyboard) == math.ceil(enabled_n / 2),
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
            return CapMsg(chat_id)

        async def send_animation(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("animation", caption))
            self.markups.append(kw.get("reply_markup"))
            return CapMsg(chat_id, animation=object())

        async def send_video(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("video", caption))
            self.markups.append(kw.get("reply_markup"))
            return CapMsg(chat_id, video=object())

        async def send_photo(self, chat_id, file_id, caption="", **kw):
            self.sent.append(("photo", caption))
            self.markups.append(kw.get("reply_markup"))
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
        sender_chat = None

    class CapMsgUpdate:
        def __init__(self, chat, user):
            self.effective_chat = chat
            self.effective_user = user
            self.effective_message = CapTextMsg()

    class CapContext:
        def __init__(self, bot_data, bot):
            self.bot = bot
            self.bot_data = bot_data
            self.chat_data = {}

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
        check(len(bot2.sent) == 1 and "Main Chat" in bot2.sent[0][1], "с анкетой → приветствие")
        kb = bot2.markups[0]
        n = len(C.MENU_BUTTON_DEFAULTS)  # 5
        check(kb is not None
              and sum(len(r) for r in kb.inline_keyboard) == n
              and len(kb.inline_keyboard) == math.ceil(n / 2),
              "приветствие с 5 кнопками-ссылками, по 2 в ряд")
        styles = [btn.to_dict().get("style") for r in kb.inline_keyboard for btn in r]
        check(styles == ["primary", "success", "success", "primary", "primary"],
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
        check(len(bot.sent) == 2 and "Main Chat" in bot.sent[1][1], "после размута → приветствие")
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
        check(not bot.restricts and len(bot.sent) == 1, "гейт выкл → вход: приветствие без мута")
        bd["storage"].set_flag("greeting_enabled", False)
        await G.on_chat_member(_join(chat, CapUser(778)), ctx)
        check(len(bot.sent) == 1, "приветствие выкл → тишина при входе")
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


async def _run_admin_panel_sim():
    print("== admin panel (dashboard/анкеты/рассылка/журнал) simulation ==")
    import handlers.admin_cms as A
    import handlers.admin_broadcast as BC
    import handlers.admin_log as LOGV
    import handlers.admin_profiles as PF
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
        await A.nav_modes(FakeUpdate(query=FakeQuery("acms_modes")), ctx)
        await A.toggle_mode(FakeUpdate(query=FakeQuery("acms_tgl:greet"), user=FakeUser(42)), ctx)
        check(storage.audit_log_count() == 1, "panel: toggle_mode пишет действие в журнал")
        check(storage.audit_log_page(0, 10)[0]["action"] == "greeting_toggle",
              "panel: залогировано именно переключение приветствия")

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
        await asyncio.gather(*ctx.application.created_tasks)
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

        # --- раздел «Журнал» ---
        st = await LOGV.nav_log(FakeUpdate(query=FakeQuery("acms_log")), ctx)
        check(st == A.BROWSE and "Журнал действий" in ctx.bot.last_text, "panel: журнал открыт")
        check("рассылка" in ctx.bot.last_text.lower(), "panel: журнал видит запись о рассылке")

        storage.close()


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
    app.add_handler(build_admin_cms())
    for h in build_gossip_handlers():
        app.add_handler(h)
    check(True, "persistent ConversationHandler-ы подключены с persistence")


def main():
    test_data()
    test_logic()
    test_storage()
    test_gossip_storage()
    test_admin_panel_storage()
    test_cms_storage()
    test_captcha_logic()
    test_menu()
    test_persistence()
    asyncio.run(_run_scenarios())
    asyncio.run(_run_lang())
    asyncio.run(_run_admin_cms())
    asyncio.run(_run_captcha_sim())
    asyncio.run(_run_gossip_sim())
    asyncio.run(_run_admin_panel_sim())
    print(f"\nPASS={PASS} FAIL={FAIL}")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
