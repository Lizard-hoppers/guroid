// Эффект "Liquid Glass" (стиль iOS 26 / WWDC 2025) для капли таббара —
// 15.08.2026, по прямому запросу владельца ("найди реальную каплю как в
// iOS 26"). Мат. часть (SDF скруглённого прямоугольника -> displacement-
// карта -> цепочка SVG-фильтров feDisplacementMap/feColorMatrix для
// преломления+хроматической аберрации) адаптирована из открытого пакета
// liquid-glass-react (MIT, © 2025 Max Rovensky,
// https://github.com/PallavAg/liquid-glass-web-react) — сохраняем
// уведомление об авторстве по условиям MIT-лицензии. Наша капля
// переиспользует ТОЛЬКО визуальный слой (эту SVG-подложку под ней) — вся
// логика позиционирования/drag/пружины осталась своя, в TabBar.jsx.
//
// Карта строится ОДИН раз на размер капли (не на каждый кадр/драг) —
// дешёвый прямой проход по пикселям в canvas, ~70x44 = не заметно даже на
// слабом телефоне. Пересчитывается только если ширина/высота капли
// реально изменились (ресайз экрана), см. useEffect в TabBar.jsx.

function smoothStep(a, b, t) {
  t = Math.max(0, Math.min(1, (t - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

function vecLength(x, y) {
  return Math.sqrt(x * x + y * y);
}

function roundedRectSDF(x, y, width, height, radius) {
  const qx = Math.abs(x) - width + radius;
  const qy = Math.abs(y) - height + radius;
  return Math.min(Math.max(qx, qy), 0) + vecLength(Math.max(qx, 0), Math.max(qy, 0)) - radius;
}

// "Форма" преломления — та же, что у апстрима: линза сильнее гнёт свет
// ближе к центру формы (скруглённый прямоугольник) и плавно сходит на
// нет к краю, а не резкий обрыв.
function liquidGlassFragment(uv) {
  const ix = uv.x - 0.5;
  const iy = uv.y - 0.5;
  const distanceToEdge = roundedRectSDF(ix, iy, 0.3, 0.2, 0.6);
  const displacement = smoothStep(0.8, 0, distanceToEdge - 0.15);
  const scaled = smoothStep(0, 1, displacement);
  return { x: ix * scaled + 0.5, y: iy * scaled + 0.5 };
}

// Строит PNG data-URL (R/G-каналы = dx/dy смещения) через offscreen canvas —
// именно ЭТА картинка потом кормится в SVG <feImage>/<feDisplacementMap>
// как карта преломления под формой капли.
export function generateLiquidGlassDisplacementMap(width, height) {
  const w = Math.max(1, Math.round(width));
  const h = Math.max(1, Math.round(height));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  let maxScale = 0;
  const rawValues = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const uv = { x: x / w, y: y / h };
      const pos = liquidGlassFragment(uv);
      const dx = pos.x * w - x;
      const dy = pos.y * h - y;
      maxScale = Math.max(maxScale, Math.abs(dx), Math.abs(dy));
      rawValues.push(dx, dy);
    }
  }
  maxScale = maxScale > 0 ? Math.max(maxScale, 1) : 1;

  const imageData = ctx.createImageData(w, h);
  const data = imageData.data;
  let rawIndex = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dx = rawValues[rawIndex++];
      const dy = rawValues[rawIndex++];
      // Плавно гасим смещение у самой рамки канвы — без этого на стыке
      // получался бы заметный шов.
      const edgeDistance = Math.min(x, y, w - x - 1, h - y - 1);
      const edgeFactor = Math.min(1, edgeDistance / 2);
      const r = (dx * edgeFactor) / maxScale + 0.5;
      const g = (dy * edgeFactor) / maxScale + 0.5;
      const i = (y * w + x) * 4;
      data[i] = Math.max(0, Math.min(255, r * 255));
      data[i + 1] = Math.max(0, Math.min(255, g * 255));
      data[i + 2] = Math.max(0, Math.min(255, g * 255));
      data[i + 3] = 255;
    }
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas.toDataURL();
}

// Firefox исторически некорректно комбинирует filter:url(#svg) поверх
// backdrop-filter (тот же фикс, что в апстриме) — там просто остаётся
// обычный блюр без преломления, деградация не ломает вид. Держим тот же
// защитный чек — если движок Telegram Desktop (Qt WebEngine) поведёт себя
// так же, деградация будет такой же безопасной (обычный блюр вместо краша).
export function supportsGlassRefraction() {
  if (typeof navigator === "undefined") return true;
  return !navigator.userAgent.toLowerCase().includes("firefox");
}
