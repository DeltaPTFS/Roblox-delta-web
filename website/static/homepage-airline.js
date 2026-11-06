/* Accessible, progressive-enhancement tabs for the Delta Roblox travel hub. */
(() => {
  "use strict";
  const tabs = [...document.querySelectorAll("[data-air-tab]")];
  const panels = [...document.querySelectorAll("[data-air-panel]")];
  if (!tabs.length || !panels.length) return;

  const activate = (tab, focus = false) => {
    const name = tab.dataset.airTab;
    for (const button of tabs) {
      const active = button === tab;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    }
    for (const panel of panels) {
      panel.hidden = panel.dataset.airPanel !== name;
    }
    if (focus) tab.focus();
  };
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next === null) return;
      event.preventDefault();
      activate(tabs[next], true);
    });
  }
})();