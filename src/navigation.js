export function resolvePage(hash = "") {
  const key = typeof hash === "string" ? hash.replace(/^#/, "") : "";
  if (["collection", "stamps"].includes(key)) return { view: key, anchor: null, openJourneys: false };
  if (["playroom", "missions", "quick-play"].includes(key)) return { view: "playroom", anchor: null, openJourneys: false };
  if (key === "theme-journeys") return { view: "playroom", anchor: "theme-journeys", openJourneys: true };
  if (["departure", "railway-map"].includes(key)) return { view: "home", anchor: "departure", openJourneys: false };
  return { view: "home", anchor: null, openJourneys: false };
}
