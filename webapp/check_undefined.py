"""Проверка: используется ли в JSX компонент, которого нет в файле.

Зачем. `npm run build` собирает без единой жалобы файл, в котором
обращаются к необъявленному имени, — падает уже в браузере. За проект это
случилось дважды: 05.09.2026 (вырезанная applySafeAreaInsets) и 06.09.2026
(TurnoverCard в кабинете рекрутера без импорта). Оба раза находил
пользователь, а не я.

Что делает: для каждого .jsx собирает имена, которые он ОТРИСОВЫВАЕТ как
компоненты (<Name ...>), и проверяет, что каждое либо импортировано, либо
объявлено в этом же файле.

Чего сознательно НЕ делает: не разбирает JS целиком и не ищет любые
необъявленные переменные — для этого нужен настоящий линтер. Это узкая
проверка ровно того класса ошибок, который уже дважды доехал до продакшена.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("/opt/gambling_community_bot/webapp/src")

# <Name ...> и <Name.Sub ...>, только с заглавной — строчные это теги HTML.
USED_RE = re.compile(r"<([A-Z][A-Za-z0-9_]*)")
# import { A, B as C } from "..."  и  import D from "..."
NAMED_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from", re.S)
DEFAULT_IMPORT_RE = re.compile(r"import\s+([A-Za-z_$][\w$]*)\s*(?:,|from)")
# Деструктуризация: const { Icon } = tab  и  ({ Icon }) => ...
# Без неё проверка ругается на имена, привязанные разбором объекта, —
# именно так задаются иконки табов, и это законно.
DESTRUCT_RE = re.compile(r"(?:(?:const|let|var)\s*\{([^}]*)\}\s*=|\(\s*\{([^}]*)\}\s*\)\s*=>)")
# function Name(...) / const Name = ... / class Name
DECL_RE = re.compile(
    r"(?:^|\n)\s*(?:export\s+)?(?:async\s+)?"
    r"(?:function\s+([A-Z][\w$]*)|(?:const|let|var|class)\s+([A-Z][\w$]*))"
)

problems: list[str] = []
checked = 0

for path in sorted(SRC.rglob("*.jsx")):
    if ".bak" in path.name:
        continue
    text = path.read_text()
    checked += 1

    declared: set[str] = set()
    for block in NAMED_IMPORT_RE.findall(text):
        for piece in block.split(","):
            piece = piece.strip()
            if not piece:
                continue
            name = piece.split(" as ")[-1].strip()
            if name:
                declared.add(name)
    declared.update(n for n in DEFAULT_IMPORT_RE.findall(text) if n and n[0].isupper())
    for a, b in DECL_RE.findall(text):
        declared.add(a or b)
    for group in DESTRUCT_RE.findall(text):
        for block in group:
            for piece in block.split(","):
                name = piece.split(":")[-1].split("=")[0].strip().strip("{}").strip()
                if name and name[0].isupper():
                    declared.add(name)

    for name in sorted(set(USED_RE.findall(text))):
        # <> фрагменты и заведомо встроенные имена не в счёт.
        if name in {"Fragment", "React"}:
            continue
        if name not in declared:
            problems.append(f"{path.relative_to(SRC)}: <{name}> используется, но не объявлен и не импортирован")

print(f"проверено файлов: {checked}")
if problems:
    print("\nНАЙДЕНЫ ОБРАЩЕНИЯ К НЕСУЩЕСТВУЮЩИМ КОМПОНЕНТАМ:")
    for p in problems:
        print("  ❌", p)
    sys.exit(1)
print("обращений к необъявленным компонентам нет")
