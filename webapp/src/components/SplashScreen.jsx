import { useEffect } from "react";
import { motion } from "framer-motion";
import { useLang } from "../i18n.jsx";
import iconUrl from "../assets/favicon.png";

// Заставка при старте Mini App (28.08.2026, фидбек владельца: "убрать
// загрузку рулетки" — раньше тут были слот-барабаны, складывающие буквы
// "GURO ID", 1.73 сек до готовности, см. git-историю SlotIntro.jsx). По
// макету ("00 · Иконка приложения") — статичный брендовый экран: иконка,
// название, подзаголовок, "Telegram Mini App". Держим коротко (SHOW_MS) —
// достаточно, чтобы не мигнуть пустым экраном, пока грузится сама вкладка
// профиля, но не задерживать пользователя ради красоты.
const SHOW_MS = 550;

export function SplashScreen({ onDone }) {
  const { t } = useLang();

  useEffect(() => {
    const timer = setTimeout(onDone, SHOW_MS);
    return () => clearTimeout(timer);
  }, [onDone]);

  return (
    <motion.div className="splash-overlay" exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
      <motion.img
        src={iconUrl}
        alt=""
        className="splash-icon"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      />
      <motion.div
        className="splash-title"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.3 }}
      >
        GURO ID
      </motion.div>
      <motion.div
        className="splash-subtitle"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.18, duration: 0.3 }}
      >
        {t("app.subtitle")}
      </motion.div>
      <motion.div
        className="splash-badge"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.26, duration: 0.3 }}
      >
        Telegram Mini App
      </motion.div>
    </motion.div>
  );
}
