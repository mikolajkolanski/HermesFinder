/* Tlo rozszerzenia (Manifest V3): zapytania do aplikacji, licznik tez na ikonie,
   menu kontekstowe. Firefox laduje je jako background.scripts, Chromium jako
   service worker (wtedy ustawienia wczytuje importScripts). */
"use strict";

if (typeof importScripts === "function") {
  importScripts("shared/langdetect.js", "shared/i18n.js", "shared/settings.js", "shared/api.js");
}

const api = CV.api;
const menus = api.menus || api.contextMenus;   // Firefox: menus, Chromium: contextMenus
const IS_FIREFOX = !!api.menus;
api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // zgodnosc wstecz: panel i okno pytaja aplikacje same (shared/api.js)
  if (msg.type === "analyze") {
    CV.analyze(msg.thesis, msg.context).then(sendResponse);
    return true;
  }
  if (msg.type === "health") {
    CV.health().then(sendResponse);
    return true;
  }
  if (msg.type === "claims-count" && sender.tab) {
    const n = msg.count || 0;
    api.action.setBadgeText({ tabId: sender.tab.id, text: n ? String(n) : "" });
    api.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: "#1d4e89" });
    if (api.action.setBadgeTextColor) {
      api.action.setBadgeTextColor({ tabId: sender.tab.id, color: "#ffffff" });
    }
    return false;
  }
  return false;
});

// Prawy przycisk na zaznaczonym tekscie: "Analyze with Hermes Finder" -> ten sam
// panel w rogu strony, co po kliknieciu podkreslonej tezy.
async function createMenu() {
  await CV.loadSettings();             // jezyk napisow w menu
  await menus.removeAll();
  menus.create({
    id: "cv-check-selection",
    title: CV.t("menuAnalyze"),
    contexts: ["selection"],
  });
  if (IS_FIREFOX) {
    // tylko Firefox podaje tekst linku (info.linkText)
    menus.create({
      id: "cv-check-link",
      title: CV.t("menuLink"),
      contexts: ["link"],
    });
  }
}
api.runtime.onInstalled.addListener(createMenu);
if (api.runtime.onStartup) api.runtime.onStartup.addListener(createMenu);
// zmiana jezyka w ustawieniach -> nowe napisy w menu
api.storage.onChanged.addListener((changes, area) => {
  if (area === "sync" && changes.language) createMenu();
});

menus.onClicked.addListener((info, tab) => {
  if (!tab) return;
  let thesis = "";
  if (info.menuItemId === "cv-check-selection") thesis = info.selectionText || "";
  else if (info.menuItemId === "cv-check-link") thesis = info.linkText || "";
  else return;
  CV.openInPage(tab.id, { type: "open-panel", thesis }).then((ok) => {
    if (ok) return;
    // strona zamknieta dla rozszerzen (about:, sklep z dodatkami) - analiza w nowej karcie
    CV.loadSettings().then((s) => api.tabs.create({ url: CV.fullUrl(s.backendUrl, thesis) }));
  });
});
