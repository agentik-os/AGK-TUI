import "./styles.css";

import {
  ORGANISATIONS,
  STORAGE_KEY,
  dashboardPath,
  getOrganisation,
  resolveOrganisationId,
  withOrganisation,
  type OrganisationId,
} from "./organisations";

const appElement = document.querySelector<HTMLDivElement>("#app");

if (!appElement) {
  throw new Error("Application root is missing");
}

const app = appElement;

app.innerHTML = `
  <main class="fleet-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="AGK Hermes Fleet, accueil">
        <span class="brand-mark" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
        <span class="brand-copy">
          <strong>HERMES</strong>
          <small>FLEET</small>
        </span>
      </a>

      <div class="current-context" aria-live="polite">
        <span class="context-eyebrow">Organisation active</span>
        <span class="context-name" data-current-name>Operator</span>
      </div>

      <div class="topbar-actions">
        <a
          class="open-separately"
          data-open-separately
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>Ouvrir séparément</span>
          <svg aria-hidden="true" viewBox="0 0 16 16" fill="none">
            <path d="M6 3h7v7M13 3 5 11M11 9v4H3V5h4" />
          </svg>
        </a>

        <div class="organisation-picker">
          <button
            class="organisation-trigger"
            type="button"
            aria-haspopup="menu"
            aria-expanded="false"
            aria-controls="organisation-menu"
          >
            <span class="status-dot" data-status-dot aria-hidden="true"></span>
            <span>Organisation</span>
            <svg class="chevron" aria-hidden="true" viewBox="0 0 16 16" fill="none">
              <path d="m4 6 4 4 4-4" />
            </svg>
          </button>

          <div
            class="organisation-menu"
            id="organisation-menu"
            role="menu"
            aria-label="Choisir une organisation"
            hidden
          >
            <div class="menu-heading">
              <span>Changer d’espace</span>
              <kbd>Esc</kbd>
            </div>
            <div class="menu-options">
              ${ORGANISATIONS.map(
                (organisation) => `
                  <button
                    class="organisation-option"
                    type="button"
                    role="menuitemradio"
                    aria-checked="false"
                    data-organisation="${organisation.id}"
                  >
                    <span
                      class="option-icon"
                      style="--organisation-accent: ${organisation.accent}"
                      aria-hidden="true"
                    >${organisation.label.slice(0, 1)}</span>
                    <span class="option-copy">
                      <strong>${organisation.label}</strong>
                      <small>${organisation.description}</small>
                    </span>
                    <svg class="option-check" aria-hidden="true" viewBox="0 0 16 16" fill="none">
                      <path d="m3 8 3 3 7-7" />
                    </svg>
                  </button>
                `,
              ).join("")}
            </div>
            <p class="menu-note">Chaque espace conserve ses propres sessions, secrets et connexions.</p>
          </div>
        </div>
      </div>
    </header>

    <section class="dashboard-stage" aria-label="Tableau de bord Hermes">
      <div class="dashboard-loading" data-loading role="status">
        <span class="loading-orbit" aria-hidden="true"></span>
        <span>Connexion à Hermes</span>
      </div>
      <iframe
        class="dashboard-frame"
        data-dashboard-frame
        title="Dashboard Hermes Operator"
        referrerpolicy="same-origin"
      ></iframe>
    </section>
  </main>
`;

function requiredElement<T extends Element>(selector: string): T {
  const element = app.querySelector<T>(selector);
  if (!element) {
    throw new Error(`Hermes Fleet UI element is missing: ${selector}`);
  }
  return element;
}

const trigger = requiredElement<HTMLButtonElement>(".organisation-trigger");
const menu = requiredElement<HTMLDivElement>(".organisation-menu");
const currentName = requiredElement<HTMLElement>("[data-current-name]");
const statusDot = requiredElement<HTMLElement>("[data-status-dot]");
const openSeparately = requiredElement<HTMLAnchorElement>("[data-open-separately]");
const frame = requiredElement<HTMLIFrameElement>("[data-dashboard-frame]");
const loading = requiredElement<HTMLElement>("[data-loading]");
const options = Array.from(
  app.querySelectorAll<HTMLButtonElement>("[data-organisation]"),
);

let activeId = resolveOrganisationId(
  window.location.search,
  window.localStorage.getItem(STORAGE_KEY),
);

function closeMenu({ restoreFocus = false } = {}): void {
  menu.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) {
    trigger.focus();
  }
}

function openMenu(): void {
  menu.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  const selected = options.find(
    (option) => option.dataset.organisation === activeId,
  );
  (selected ?? options[0])?.focus();
}

function setOrganisation(id: OrganisationId): void {
  const organisation = getOrganisation(id);
  const path = dashboardPath(id);

  activeId = id;
  currentName.textContent = organisation.label;
  statusDot.style.setProperty("--current-accent", organisation.accent);
  openSeparately.href = path;
  openSeparately.setAttribute(
    "aria-label",
    `Ouvrir le dashboard ${organisation.label} séparément`,
  );

  for (const option of options) {
    const isCurrent = option.dataset.organisation === id;
    option.setAttribute("aria-checked", String(isCurrent));
    option.classList.toggle("is-current", isCurrent);
  }

  window.localStorage.setItem(STORAGE_KEY, id);
  const nextSearch = withOrganisation(window.location.search, id);
  window.history.replaceState(null, "", `${window.location.pathname}${nextSearch}${window.location.hash}`);

  if (frame.getAttribute("src") !== path) {
    loading.hidden = false;
    frame.classList.remove("is-ready");
    frame.title = `Dashboard Hermes ${organisation.label}`;
    frame.src = path;
  }
}

trigger.addEventListener("click", () => {
  if (menu.hidden) {
    openMenu();
  } else {
    closeMenu();
  }
});

for (const option of options) {
  option.addEventListener("click", () => {
    const id = option.dataset.organisation;
    if (
      id === "operator" ||
      id === "agentik" ||
      id === "mission" ||
      id === "private"
    ) {
      setOrganisation(id);
      closeMenu({ restoreFocus: true });
    }
  });
}

menu.addEventListener("keydown", (event) => {
  const currentIndex = options.indexOf(document.activeElement as HTMLButtonElement);
  let nextIndex: number | null = null;

  if (event.key === "ArrowDown") {
    nextIndex = (currentIndex + 1) % options.length;
  } else if (event.key === "ArrowUp") {
    nextIndex = (currentIndex - 1 + options.length) % options.length;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = options.length - 1;
  }

  if (nextIndex !== null) {
    event.preventDefault();
    options[nextIndex]?.focus();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !menu.hidden) {
    event.preventDefault();
    closeMenu({ restoreFocus: true });
  }
});

document.addEventListener("pointerdown", (event) => {
  if (!menu.hidden && !menu.parentElement?.contains(event.target as Node)) {
    closeMenu();
  }
});

frame.addEventListener("load", () => {
  loading.hidden = true;
  frame.classList.add("is-ready");
});

window.addEventListener("popstate", () => {
  setOrganisation(
    resolveOrganisationId(window.location.search, window.localStorage.getItem(STORAGE_KEY)),
  );
});

setOrganisation(activeId);
