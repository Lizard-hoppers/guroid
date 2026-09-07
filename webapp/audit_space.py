"""Отступы вне сетки 4·8·12·16·20 — с селектором, чтобы судить по смыслу."""
import re, collections, sys

css = open("src/styles.css").read()
ALLOWED = {0, 4, 8, 12, 16, 20}

# разбираем на правила: селектор { тело }
rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
found = collections.defaultdict(list)
for sel, body in rules:
    sel = " ".join(sel.split())[-70:]
    for m in re.finditer(r"((?:margin|padding|gap|row-gap|column-gap)[a-z-]*)\s*:\s*([^;]+);", body):
        prop, val = m.group(1), m.group(2).strip()
        if "var(" in val or "calc(" in val or "%" in val or "auto" in val:
            continue
        nums = [int(x) for x in re.findall(r"(\d+)px", val)]
        bad = [x for x in nums if x not in ALLOWED]
        if bad:
            found[tuple(sorted(set(bad)))].append((sel, prop, val))

total = sum(len(v) for v in found.values())
print(f"объявлений с недопустимыми значениями: {total}\n")
by_val = collections.defaultdict(list)
for key, items in found.items():
    for it in items:
        by_val[key].append(it)
for key in sorted(by_val, key=lambda k: -len(by_val[k])):
    print(f"--- значения {', '.join(str(x)+'px' for x in key)} ({len(by_val[key])}) ---")
    for sel, prop, val in by_val[key][:60]:
        print(f"    {sel:<58} {prop}: {val}")
    print()
