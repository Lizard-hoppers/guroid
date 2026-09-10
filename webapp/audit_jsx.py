"""Отступы, заданные прямо в разметке (style={{...}}), против сетки
4·8·12·16·20. Разбор styles.css их не видел."""
import re, pathlib, collections

ALLOWED = {0, 4, 8, 12, 16, 20}
PROP = re.compile(r"\b(margin|padding|gap|rowGap|columnGap)(Top|Right|Bottom|Left)?\s*:\s*(-?\d+)\b")

found = collections.defaultdict(list)
total = 0
for p in sorted(pathlib.Path("src").rglob("*.jsx")):
    if ".bak" in p.name:
        continue
    for i, line in enumerate(p.read_text().splitlines(), 1):
        for m in PROP.finditer(line):
            val = int(m.group(3))
            if abs(val) in ALLOWED:
                continue
            found[abs(val)].append((str(p).replace("src/components/", ""), i,
                                    m.group(1) + (m.group(2) or ""), val))
            total += 1

print(f"значений вне сетки в разметке: {total}\n")
for val in sorted(found, key=lambda v: -len(found[v])):
    items = found[val]
    print(f"--- {val}px ({len(items)}) ---")
    for f, ln, prop, v in items:
        print(f"    {f}:{ln}  {prop}: {v}")
    print()
