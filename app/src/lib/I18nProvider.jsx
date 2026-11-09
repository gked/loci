import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "./api.js";
import { DEFAULT_LANGUAGE, STORAGE_KEY, normalizeLanguage, translate } from "./i18n.js";

const I18nContext = createContext(null);

function storedLanguage() {
  try {
    return normalizeLanguage(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null; // localStorage throws in some sandboxed contexts
  }
}

// The language is the user's pick in the rail (kept in this browser), else the
// one the server is configured for (`language` in config.yml / LOCI_LANGUAGE),
// else English.
export function I18nProvider({ children }) {
  const [chosen, setChosen] = useState(storedLanguage);
  // Same key and options as the rail's health query, so this is one request.
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: Infinity,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const language = chosen || normalizeLanguage(health?.language) || DEFAULT_LANGUAGE;

  useEffect(() => {
    document.documentElement.lang = language === "ru-RU" ? "ru" : "en";
  }, [language]);

  const setLanguage = useCallback((next) => {
    const value = normalizeLanguage(next);
    if (!value) return;
    try { localStorage.setItem(STORAGE_KEY, value); } catch { /* not persisted */ }
    setChosen(value);
  }, []);

  const value = useMemo(() => ({
    language,
    setLanguage,
    t: (text, vars) => translate(text, language, vars),
  }), [language, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}
