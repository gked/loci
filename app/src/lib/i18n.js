// UI strings. The English text is the key: `t("All loci")` returns itself in
// English and the entry below in Russian, so the English UI (and every e2e test
// that reads it) never depends on this table, and a string missing from it
// falls back to English rather than showing a hole.
//
// The Latin half of a "latin · english" label is part of the design and stays
// Latin in every language; only the working-language half is translated. Type
// names, relation names, field names, uids and data-testid values are
// identifiers, never translated.

export const LANGUAGES = ["en", "ru-RU"];
export const DEFAULT_LANGUAGE = "en";
export const LANGUAGE_LABELS = { "en": "EN", "ru-RU": "RU" };
export const STORAGE_KEY = "loci_language";

// Mirrors loci.language.normalize (src/loci/language.py); both are checked
// against tests/fixtures/language-normalize.json — change them together.
// "ru", "ru_RU", "ru-ru" -> "ru-RU"; anything unknown -> null.
export function normalizeLanguage(value) {
  if (typeof value !== "string") return null;
  const v = value.trim().replace("_", "-").toLowerCase();
  if (v === "en" || v.startsWith("en-")) return "en";
  if (v === "ru" || v === "ru-ru") return "ru-RU";
  return null;
}

// Short labels sit in the instrument rail, so they are nouns or imperatives,
// never sentences. Counted phrases put the number last ("активных: 3") because
// a placeholder cannot decline the noun that follows it.
const ru = {
  // App
  "Cannot reach API — is": "Нет связи с API — возможно,",
  " running?": " не запущен?",
  "← back": "← назад",
  "loading topology…": "загрузка топологии…",
  "Calibration": "Калибровка",
  "calibratio · vault health": "calibratio · состояние хранилища",
  "vault": "хранилище",
  "valetudo · health": "valetudo · состояние",
  "loci in vault": "loci в хранилище",

  // Rail
  "revoca · undo last change": "revoca · отменить последнее изменение",
  "undo this": "отменить это",
  "This note was deleted on another computer, but an edit kept it.": "Эта заметка удалена на другом компьютере, но правка её сохранила.",
  "delete again": "удалить снова",
  "{n} conflicted copies · merge": "копий-конфликтов: {n} · слить",
  "edits to different lines · merges on its own": "правки в разных строках · сливается само",
  "both computers changed the same lines · choose": "на обоих компьютерах изменены одни строки · выберите",
  "deleted on one computer, edited on the other · the edit is kept": "удалено на одном компьютере, изменено на другом · правка сохраняется",
  "two different notes share this name · both are kept": "две разные заметки с одним именем · остаются обе",
  "clash {n}": "расхождение {n}",
  "this file": "этот файл",
  "the copy": "копия",
  "merge": "слить",
  "cancel": "отмена",
  "undone · {message}": "отменено · {message}",
  "ok": "ок",
  "prima · primary": "prima · основное",
  "genera · types": "genera · типы",
  "instrumenta · tools": "instrumenta · инструменты",
  "All loci": "Все loci",
  "Recent": "Недавние",
  "Topology": "Топология",
  "Command": "Команда",
  "Settings": "Настройки",
  "subtypes": "подтипы",
  "yours": "ваши",
  "vault · {n} loci": "хранилище · {n} loci",
  "Language": "Язык",

  // Index
  "gradus · zoom": "gradus · масштаб",
  "of {n}": "из {n}",
  "nodes": "узлов",
  "sorted by": "сортировка:",
  "updated": "обновлено",
  "{n} archived": "{n} в архиве",
  "{n} ghost": "{n} призрачных",
  "⌘K to search": "⌘K — поиск",
  "type": "тип",
  "all": "все",
  "filter by uid or title…": "фильтр по uid или названию…",
  "Clear filter": "Сбросить фильтр",
  "ghost": "призрак",
  "archived": "архив",
  "title": "название",
  "missing node": "узел не найден",
  "vacuum · no match for \"{q}\"": "vacuum · ничего не найдено по «{q}»",
  "vacuum · no loci found": "vacuum · loci не найдены",

  // Node
  "vacuum · empty": "vacuum · пусто",
  "Select a locus from the vault.": "Выберите locus из хранилища.",
  "traverse": "обход",
  "{n}w": "{n} сл.",
  "corpus · body": "corpus · текст",
  "res · asset": "res · ассет",
  "… truncated": "… обрезано",
  "nexus · outbound": "nexus · исходящие",
  "← nexus inbound": "← nexus входящие",

  // Palette
  "praeceptum · command": "praeceptum · команда",
  "esc to close": "esc — закрыть",
  "search vault — title, tag, uid": "поиск по хранилищу — название, тег, uid",
  "search vault": "поиск по хранилищу",
  "vacuum · no results for \"{q}\"": "vacuum · ничего не найдено по «{q}»",
  "open": "открыть",
  "{n} results": "результатов: {n}",

  // Graph
  "{nodes} nodes · {edges} edges": "узлов: {nodes} · связей: {edges}",
  "{n}-hop": "шаг {n}",
  "⏸ pause": "⏸ пауза",
  "▶ resume": "▶ продолжить",
  "reset": "сброс",
  "Types · Genera": "Типы · Genera",
  "Relations · Vincula": "Связи · Vincula",
  "{n} active": "активных: {n}",
  "click to isolate": "клик — изолировать",
  "Focus · Inspector": "Фокус · Inspector",
  "degree": "степень",
  "out · in": "исх. · вх.",
  "open node →": "открыть узел →",
  "Click a locus to isolate its first-degree neighbourhood. Drag to fix in place. Double-click to open.":
    "Нажмите на locus, чтобы выделить его ближайшее окружение. Перетащите, чтобы закрепить на месте. Двойной клик открывает узел.",
  "drag · pin · dblclick · open": "перетащить · закрепить · двойной клик · открыть",
  "space · pause · esc · close": "пробел · пауза · esc · закрыть",
};

export const MESSAGES = { "ru-RU": ru };

// translate("{n} active", "ru-RU", { n: 3 }) -> "активных: 3"
export function translate(text, language, vars) {
  const table = MESSAGES[language];
  let out = (table && Object.prototype.hasOwnProperty.call(table, text)) ? table[text] : text;
  if (vars) {
    out = out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  }
  return out;
}
