(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry) return;

  const React = SDK.React;
  const h = React.createElement;
  const hooks = SDK.hooks;
  const useState = hooks.useState;
  const useEffect = hooks.useEffect;
  const useCallback = hooks.useCallback;
  const useRef = hooks.useRef;
  const components = SDK.components || {};
  const Card = components.Card;
  const CardHeader = components.CardHeader;
  const CardTitle = components.CardTitle;
  const CardContent = components.CardContent;
  const Badge = components.Badge;
  const Button = components.Button;
  const Separator = components.Separator;
  const Tabs = components.Tabs;
  const TabsList = components.TabsList;
  const TabsTrigger = components.TabsTrigger;
  const timeAgo = SDK.utils && SDK.utils.timeAgo
    ? SDK.utils.timeAgo
    : function () { return "Recently"; };

  const API_URL = "/api/plugins/agentik-os/catalog";

  function asList(value) {
    return Array.isArray(value) ? value.filter(Boolean) : [];
  }

  function normalizeCatalog(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    const registrySource = source.registry && typeof source.registry === "object"
      ? source.registry
      : {};
    const syncSource = source.sync && typeof source.sync === "object" ? source.sync : {};

    return {
      environment: String(source.environment || "unknown"),
      registry: {
        available: Boolean(registrySource.available),
        healthy: Boolean(registrySource.healthy),
        package_count: Number(registrySource.package_count || 0),
        invalid_count: Number(registrySource.invalid_count || 0),
        packages: asList(registrySource.packages),
      },
      agents: asList(source.agents),
      sync: {
        agent_count: Number(syncSource.agent_count || 0),
        active_session_count: Number(syncSource.active_session_count || 0),
      },
    };
  }

  function formatError(error) {
    const raw = error && error.message ? String(error.message) : "Catalog request failed";
    const match = raw.match(/^\d{3}:\s*(.*)$/s);
    const body = match ? match[1] : raw;
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed.detail === "string") return parsed.detail;
    } catch (_error) {
      // The response was not a JSON error envelope.
    }
    return body || "Catalog request failed";
  }

  function Icon(props) {
    const name = props.name;
    const common = {
      className: "agk-os-icon " + (props.className || ""),
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.8,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": "true",
    };

    if (name === "package") {
      return h("svg", common,
        h("path", { d: "m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" }),
        h("path", { d: "m4.5 7.8 7.5 4.3 7.5-4.3M12 12v9" })
      );
    }
    if (name === "agent") {
      return h("svg", common,
        h("rect", { x: "5", y: "7", width: "14", height: "12", rx: "3" }),
        h("path", { d: "M9 3h6M12 3v4M9 12h.01M15 12h.01M9 16h6" })
      );
    }
    if (name === "activity") {
      return h("svg", common,
        h("path", { d: "M3 12h4l2.4-6 4.2 12 2.4-6h5" })
      );
    }
    if (name === "refresh") {
      return h("svg", common,
        h("path", { d: "M20 6v5h-5M4 18v-5h5" }),
        h("path", { d: "M18.5 9A7 7 0 0 0 6.2 6.5L4 9M5.5 15a7 7 0 0 0 12.3 2.5L20 15" })
      );
    }
    if (name === "check") {
      return h("svg", common,
        h("path", { d: "m5 12 4 4L19 6" })
      );
    }
    if (name === "alert") {
      return h("svg", common,
        h("path", { d: "m12 3 9 16H3L12 3Z" }),
        h("path", { d: "M12 9v4M12 16h.01" })
      );
    }
    return h("svg", common,
      h("circle", { cx: "12", cy: "12", r: "9" }),
      h("path", { d: "M12 8v4l3 2" })
    );
  }

  function StatusPill(props) {
    const tone = props.tone || "neutral";
    const badgeTone = tone === "success" || tone === "live"
      ? "success"
      : tone === "warning"
        ? "warning"
        : tone === "accent"
          ? "secondary"
          : "outline";
    return h(Badge, { tone: badgeTone, className: "agk-os-status agk-os-status--" + tone },
      props.dot === false ? null : h("span", { className: "agk-os-status__dot", "aria-hidden": "true" }),
      props.children
    );
  }

  function TagList(props) {
    const values = asList(props.values);
    const limit = props.limit || 5;
    if (!values.length) return null;
    const visible = values.slice(0, limit);
    const rest = values.length - visible.length;
    return h("div", { className: "agk-os-tags", "aria-label": props.label || "Tags" },
      visible.map(function (value) {
        return h(Badge, { tone: "outline", className: "agk-os-tag", key: String(value) }, String(value));
      }),
      rest > 0 ? h(Badge, { tone: "secondary", className: "agk-os-tag agk-os-tag--more" }, "+" + rest) : null
    );
  }

  function SummaryCard(props) {
    return h(Card, { className: "agk-os-summary-card" },
      h(CardContent, { className: "agk-os-summary-card__content" },
        h("div", { className: "agk-os-summary-card__top" },
          h("span", { className: "agk-os-summary-card__label" }, props.label),
          h(Icon, { name: props.icon })
        ),
        h("strong", { className: "agk-os-summary-card__value" }, String(props.value)),
        h("span", { className: "agk-os-summary-card__detail" }, props.detail)
      )
    );
  }

  function EmptyState(props) {
    return h(Card, { className: "agk-os-empty" },
      h(CardContent, { className: "agk-os-empty__content" },
        h("div", { className: "agk-os-empty__icon" }, h(Icon, { name: props.icon })),
        h("div", null,
          h("h3", null, props.title),
          h("p", null, props.description)
        )
      )
    );
  }

  function PackageCard(props) {
    const item = props.item || {};
    const componentCount = asList(item.skills).length
      + asList(item.workflows).length
      + asList(item.agents).length
      + asList(item.tools).length
      + asList(item.commands).length
      + asList(item.knowledge).length
      + asList(item.evals).length;

    return h(Card, { className: "agk-os-package-card" },
      h(CardHeader, { className: "agk-os-package-card__header" },
        h("div", { className: "agk-os-card__heading" },
          h("div", { className: "agk-os-card__title-row" },
            h(Icon, { name: "package" }),
            h(CardTitle, null, item.name || item.id || "Unnamed OS")
          ),
          h(StatusPill, { tone: item.allowed_here ? "success" : "neutral" },
            item.allowed_here ? "Available here" : "Installed elsewhere"
          )
        ),
        h("div", { className: "agk-os-card__identity" },
          h("code", { className: "agk-os-code" }, String(item.id || "unknown")),
          item.version ? h(Badge, { tone: "secondary", className: "agk-os-version" }, "v" + item.version) : null
        )
      ),
      h(CardContent, { className: "agk-os-package-card__content" },
        item.description ? h("p", { className: "agk-os-card__description" }, item.description) : null,
        h("div", { className: "agk-os-card__metric" },
          h("span", null, "Validated components"),
          h("strong", null, String(componentCount))
        ),
        h(TagList, { values: item.capabilities, label: "Capabilities", limit: 4 }),
        h(Separator, { className: "agk-os-card__separator" }),
        h("div", { className: "agk-os-card__footer" },
          h("span", null, asList(item.scope).length + " scopes"),
          h("span", null, asList(item.agents).length + " agents"),
          h("span", null, asList(item.workflows).length + " workflows")
        )
      )
    );
  }

  function SessionRow(props) {
    const session = props.session || {};
    const isActive = Boolean(session.active);
    const timestamp = Number(session.last_activity || 0);
    const epoch = timestamp && timestamp < 1000000000000 ? timestamp * 1000 : timestamp;
    const lastSeen = epoch ? timeAgo(epoch) : "No activity timestamp";
    const status = String(session.status || (isActive ? "running" : "idle"));

    return h("li", { className: "agk-os-session" },
      h("span", { className: "agk-os-session__pulse agk-os-session__pulse--" + (isActive ? "active" : "idle"), "aria-hidden": "true" }),
      h("div", { className: "agk-os-session__identity" },
        h("strong", null, session.name || session.id || "Unnamed session"),
        h("span", null, String(session.runtime || "runtime") + " · " + lastSeen)
      ),
      h("div", { className: "agk-os-session__state" },
        h(StatusPill, { tone: isActive ? "live" : "neutral", dot: false }, status),
        session.exit_code !== null && session.exit_code !== undefined
          ? h("span", { className: "agk-os-code" }, "exit " + session.exit_code)
          : null
      )
    );
  }

  function AgentCard(props) {
    const agent = props.agent || {};
    const sessions = asList(agent.sessions);
    const definitionReady = Boolean(agent.prompt_present && agent.definition_hash);

    return h(Card, { className: "agk-os-agent-card" },
      h(CardHeader, { className: "agk-os-agent-card__header" },
        h("div", { className: "agk-os-card__heading" },
          h("div", { className: "agk-os-card__title-row" },
            h(Icon, { name: "agent" }),
            h(CardTitle, null, agent.name || agent.id || "Unnamed agent")
          ),
          h("div", { className: "agk-os-card__statuses" },
            h(StatusPill, { tone: definitionReady ? "success" : "warning" },
              definitionReady ? "Definition valid" : "Definition incomplete"
            ),
            h(StatusPill, { tone: agent.allowed_here ? "accent" : "neutral" },
              agent.allowed_here ? "Available here" : "Scope restricted"
            )
          )
        ),
        h("div", { className: "agk-os-card__identity" },
          h("code", { className: "agk-os-code" }, String(agent.id || "unknown")),
          agent.version ? h(Badge, { tone: "secondary", className: "agk-os-version" }, "v" + agent.version) : null
        )
      ),
      h(CardContent, { className: "agk-os-agent-card__content" },
        agent.description ? h("p", { className: "agk-os-card__description" }, agent.description) : null,
        h("dl", { className: "agk-os-agent-meta" },
          h("div", null, h("dt", null, "Runtime"), h("dd", null, String(agent.runtime || "Hermes"))),
          h("div", null, h("dt", null, "Distribution"), h("dd", null, String(agent.distribution || "local"))),
          h("div", null, h("dt", null, "Linked sessions"), h("dd", null, String(sessions.length)))
        ),
        h(TagList, { values: agent.scope, label: "Agent scopes", limit: 6 }),
        h(Separator, { className: "agk-os-card__separator" }),
        h("div", { className: "agk-os-agent-card__sessions" },
        h("div", { className: "agk-os-subhead" },
          h("div", null,
            h("span", { className: "agk-os-label" }, "Runtime layer"),
            h("h4", null, "Linked runtime sessions")
          ),
          h(Badge, { tone: "secondary", className: "agk-os-count" }, String(sessions.length))
        ),
        sessions.length
          ? h("ul", { className: "agk-os-session-list" }, sessions.map(function (session, index) {
              return h(SessionRow, { session: session, key: session.id || session.name || index });
            }))
          : h("div", { className: "agk-os-session-empty" },
              h(Icon, { name: "activity" }),
              h("p", null, "No linked runtime session. The agent definition remains installed independently.")
            )
        )
      )
    );
  }

  function OverviewPanel(props) {
    const data = props.data;
    const agents = data.agents;
    const registryReady = props.registryReady;
    const definitionsReady = props.definitionsReady;

    return h("div", { className: "agk-os-overview", role: "tabpanel", id: "agk-os-panel-overview", "aria-labelledby": "agk-os-tab-overview" },
      h(Card, { className: "agk-os-overview-card" },
        h(CardHeader, null,
          h("div", { className: "agk-os-overview-card__heading" },
            h(CardTitle, null, "Registry health"),
            h(StatusPill, { tone: registryReady ? "success" : "warning" },
              registryReady ? "Healthy" : "Needs review"
            )
          )
        ),
        h(CardContent, { className: "agk-os-overview-card__content" },
          h("p", null, registryReady
            ? "The canonical registry is available and validated for this profile."
            : "The catalog is visible, but registry health is not fully confirmed."),
          h("dl", { className: "agk-os-overview-list" },
            h("div", null, h("dt", null, "Environment"), h("dd", null, data.environment)),
            h("div", null, h("dt", null, "Validated systems"), h("dd", null, String(data.registry.package_count))),
            h("div", null, h("dt", null, "Invalid packages hidden"), h("dd", null, String(data.registry.invalid_count)))
          )
        )
      ),
      h(Card, { className: "agk-os-overview-card" },
        h(CardHeader, null,
          h("div", { className: "agk-os-overview-card__heading" },
            h(CardTitle, null, "Hermes agents"),
            h(StatusPill, { tone: definitionsReady === agents.length ? "success" : "warning" },
              definitionsReady + " of " + agents.length + " definitions valid"
            )
          )
        ),
        h(CardContent, { className: "agk-os-overview-card__content" },
          h("p", null, "Definitions, profile availability, and linked runtime sessions stay independently observable."),
          h("dl", { className: "agk-os-overview-list" },
            h("div", null, h("dt", null, "Installed agents"), h("dd", null, String(data.sync.agent_count || agents.length))),
            h("div", null, h("dt", null, "Valid definitions"), h("dd", null, String(definitionsReady))),
            h("div", null, h("dt", null, "Active sessions"), h("dd", null, String(data.sync.active_session_count)))
          )
        )
      )
    );
  }

  function catalogValue(kind, item, index) {
    return kind + ":" + String(item.id || item.name || index);
  }

  function CatalogTrigger(props) {
    return h(TabsTrigger, {
      className: "agk-os-catalog-trigger",
      id: "agk-os-view-" + props.value.replace(/[^a-z0-9_-]+/gi, "-"),
      value: props.value,
      active: props.active,
      role: "tab",
      "aria-selected": props.active,
      "aria-controls": "agk-os-panel-detail",
      "data-catalog-kind": props.kind,
      onClick: props.onClick,
    },
      h("span", { className: "agk-os-catalog-trigger__icon" }, h(Icon, { name: props.icon })),
      h("span", { className: "agk-os-catalog-trigger__copy" },
        h("strong", null, props.title),
        h("small", null, props.description)
      ),
      props.meta === undefined || props.meta === null
        ? null
        : h(Badge, { tone: "secondary", className: "agk-os-catalog-trigger__meta" }, String(props.meta))
    );
  }

  function CatalogNavigation(props) {
    return h("aside", { className: "agk-os-context-panel", "aria-label": "OS and agent catalog" },
      h("header", { className: "agk-os-context-header" },
        h("div", null,
          h("span", { className: "agk-os-label" }, "Workspace"),
          h("h2", null, "Supervision")
        ),
        h(StatusPill, { tone: props.registryReady ? "success" : "warning", dot: false },
          props.registryReady ? "Healthy" : "Review"
        ),
        h("p", null, "Select a system or Hermes agent to inspect its validated state.")
      ),
      h(TabsList, { className: "agk-os-catalog-list", role: "tablist", "aria-label": "Catalog entities" },
        h("span", { className: "agk-os-catalog-group" }, "Dashboard"),
        h(CatalogTrigger, {
          value: "overview",
          kind: "overview",
          active: props.activeView === "overview",
          icon: "activity",
          title: "Overview",
          description: "Health and activity",
          onClick: function () { props.setActiveView("overview"); },
        }),
        h("span", { className: "agk-os-catalog-group" }, "Operative systems"),
        props.packages.length
          ? props.packages.map(function (item, index) {
              const value = catalogValue("system", item, index);
              return h(CatalogTrigger, {
                key: value,
                value: value,
                kind: "system",
                active: props.activeView === value,
                icon: "package",
                title: item.name || item.id || "Unnamed OS",
                description: item.allowed_here ? "Available here" : "Installed elsewhere",
                meta: item.version ? "v" + item.version : null,
                onClick: function () { props.setActiveView(value); },
              });
            })
          : h("span", { className: "agk-os-catalog-empty" }, "No validated systems"),
        h("span", { className: "agk-os-catalog-group" }, "Hermes agents"),
        props.agents.length
          ? props.agents.map(function (agent, index) {
              const value = catalogValue("agent", agent, index);
              return h(CatalogTrigger, {
                key: value,
                value: value,
                kind: "agent",
                active: props.activeView === value,
                icon: "agent",
                title: agent.name || agent.id || "Unnamed agent",
                description: String(agent.runtime || "Hermes") + " runtime",
                meta: asList(agent.sessions).length,
                onClick: function () { props.setActiveView(value); },
              });
            })
          : h("span", { className: "agk-os-catalog-empty" }, "No installed agents")
      ),
      h("footer", { className: "agk-os-context-footer" },
        h("div", null,
          h("span", { className: "agk-os-status-light agk-os-status-light--" + (props.activeSessions ? "live" : "idle"), "aria-hidden": "true" }),
          h("span", null, props.activeSessions + " active session" + (props.activeSessions === 1 ? "" : "s"))
        ),
        h("code", null, props.environment)
      )
    );
  }

  function LoadingPage() {
    return h("div", { className: "agk-os-hub", "aria-busy": "true", "aria-live": "polite" },
      h("div", { className: "agk-os-skeleton agk-os-skeleton--header" }),
      h("div", { className: "agk-os-summary-grid" }, [0, 1, 2, 3].map(function (index) {
        return h(Card, { className: "agk-os-skeleton agk-os-skeleton--card", key: index });
      })),
      h("span", { className: "agk-os-sr-only" }, "Loading OS and agent catalog")
    );
  }

  function ErrorPage(props) {
    return h("div", { className: "agk-os-hub" },
      h(Card, { className: "agk-os-error", role: "alert" },
        h(CardContent, { className: "agk-os-error__content" },
          h("div", { className: "agk-os-error__icon" }, h(Icon, { name: "alert" })),
          h("div", { className: "agk-os-error__copy" },
            h("span", { className: "agk-os-label" }, "Catalog unavailable"),
            h("h2", null, "Hermes could not load OS and agent state"),
            h("p", null, props.message)
          ),
          h(Button, { className: "agk-os-button", type: "button", size: "sm", outlined: true, onClick: props.onRetry },
            h(Icon, { name: "refresh" }),
            "Try again"
          )
        )
      )
    );
  }

  function AgentikOSPage() {
    const catalogState = useState(null);
    const catalog = catalogState[0];
    const setCatalog = catalogState[1];
    const loadingState = useState(true);
    const loading = loadingState[0];
    const setLoading = loadingState[1];
    const refreshingState = useState(false);
    const refreshing = refreshingState[0];
    const setRefreshing = refreshingState[1];
    const errorState = useState("");
    const error = errorState[0];
    const setError = errorState[1];
    const requestRef = useRef(null);

    const loadCatalog = useCallback(function (isRefresh) {
      if (requestRef.current) requestRef.current.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError("");

      return SDK.fetchJSON(API_URL, { signal: controller.signal })
        .then(function (payload) {
          if (!controller.signal.aborted) setCatalog(normalizeCatalog(payload));
        })
        .catch(function (requestError) {
          if (!controller.signal.aborted) setError(formatError(requestError));
        })
        .finally(function () {
          if (!controller.signal.aborted) {
            setLoading(false);
            setRefreshing(false);
          }
        });
    }, []);

    useEffect(function () {
      loadCatalog(false);
      return function () {
        if (requestRef.current) requestRef.current.abort();
      };
    }, [loadCatalog]);

    if (loading && !catalog) return h(LoadingPage);
    if (error && !catalog) return h(ErrorPage, { message: error, onRetry: function () { loadCatalog(false); } });

    const data = catalog || normalizeCatalog({});
    const packages = data.registry.packages;
    const agents = data.agents;
    const activeSessions = data.sync.active_session_count;
    const registryReady = data.registry.available && data.registry.healthy;
    const definitionsReady = agents.filter(function (agent) {
      return Boolean(agent.prompt_present && agent.definition_hash);
    }).length;
    const packageEntries = packages.map(function (item, index) {
      return { value: catalogValue("system", item, index), item: item };
    });
    const agentEntries = agents.map(function (agent, index) {
      return { value: catalogValue("agent", agent, index), item: agent };
    });

    return h("main", { className: "agk-os-hub" },
      h(Tabs, { className: "agk-os-workspace", defaultValue: "overview" }, function (activeView, setActiveView) {
        const packageEntry = packageEntries.find(function (entry) { return entry.value === activeView; });
        const agentEntry = agentEntries.find(function (entry) { return entry.value === activeView; });
        const selectedPackage = packageEntry ? packageEntry.item : null;
        const selectedAgent = agentEntry ? agentEntry.item : null;
        const viewKind = selectedPackage ? "system" : (selectedAgent ? "agent" : "overview");
        const detailTitle = selectedPackage
          ? (selectedPackage.name || selectedPackage.id || "Operative System")
          : selectedAgent
            ? (selectedAgent.name || selectedAgent.id || "Hermes Agent")
            : "Control overview";
        const detailDescription = selectedPackage
          ? (selectedPackage.description || "Validated OS package from the canonical Agentik registry.")
          : selectedAgent
            ? (selectedAgent.description || "Installed Hermes agent definition and linked runtime state.")
            : "Monitor registry health, validated systems, installed agents, and their active runtime sessions.";
        const viewLabel = viewKind === "system" ? "Systems" : (viewKind === "agent" ? "Agents" : "Dashboard");
        const triggerId = "agk-os-view-" + (viewKind === "overview" ? "overview" : activeView.replace(/[^a-z0-9_-]+/gi, "-"));

        return h(React.Fragment, null,
          h(CatalogNavigation, {
            activeView: activeView,
            setActiveView: setActiveView,
            packages: packages,
            agents: agents,
            registryReady: registryReady,
            activeSessions: activeSessions,
            environment: data.environment,
          }),
          h("section", {
            className: "agk-os-detail-panel",
            id: "agk-os-panel-detail",
            role: "tabpanel",
            "aria-labelledby": triggerId,
          },
            h("header", { className: "agk-os-page-header" },
              h("div", { className: "agk-os-page-heading" },
                h("div", { className: "agk-os-kicker" },
                  h("span", null, "OS & Agents"),
                  h("span", { "aria-hidden": "true" }, "/"),
                  h("span", null, viewLabel),
                  h(Badge, { tone: "outline", className: "agk-os-environment" }, data.environment)
                ),
                h("h1", null, detailTitle),
                h("p", null, detailDescription)
              ),
              h(Button, {
                className: "agk-os-button agk-os-refresh-button",
                type: "button",
                size: "sm",
                outlined: true,
                onClick: function () { loadCatalog(true); },
                disabled: refreshing,
                "aria-label": "Refresh OS and agent catalog",
              },
                h(Icon, { name: "refresh", className: refreshing ? "agk-os-spin" : "" }),
                refreshing ? "Refreshing" : "Refresh"
              )
            ),
            error ? h("div", { className: "agk-os-inline-alert", role: "status" },
              h(Icon, { name: "alert" }),
              h("span", null, "Refresh failed. Showing the last loaded response."),
              h(Button, { type: "button", size: "sm", ghost: true, onClick: function () { loadCatalog(true); } }, "Retry")
            ) : null,
            viewKind === "overview"
              ? h("div", { className: "agk-os-detail-body agk-os-detail-body--dashboard" },
                  h("section", { className: "agk-os-summary-grid", "aria-label": "Catalog summary" },
                    h(SummaryCard, {
                      icon: "package",
                      label: "Validated OS",
                      value: data.registry.package_count,
                      detail: data.registry.invalid_count ? data.registry.invalid_count + " invalid hidden" : "Registry validated only",
                    }),
                    h(SummaryCard, {
                      icon: "agent",
                      label: "Installed agents",
                      value: data.sync.agent_count || agents.length,
                      detail: definitionsReady + " definitions valid",
                    }),
                    h(SummaryCard, {
                      icon: "activity",
                      label: "Active sessions",
                      value: activeSessions,
                      detail: "Linked runtime processes",
                    }),
                    h(SummaryCard, {
                      icon: registryReady ? "check" : "alert",
                      label: "Registry state",
                      value: registryReady ? "Healthy" : (data.registry.available ? "Needs review" : "Unavailable"),
                      detail: "Current profile · " + data.environment,
                    })
                  ),
                  h(OverviewPanel, { data: data, registryReady: registryReady, definitionsReady: definitionsReady })
                )
              : h("div", { className: "agk-os-detail-body agk-os-detail-body--entity" },
                  selectedPackage
                    ? h(PackageCard, { item: selectedPackage })
                    : selectedAgent
                      ? h(AgentCard, { agent: selectedAgent })
                      : h(EmptyState, {
                          icon: "alert",
                          title: "The selected catalog entry is unavailable",
                          description: "Refresh the catalog or select another entry from the supervision panel.",
                        })
                )
          )
        );
      })
    );
  }

  registry.register("agentik-os", AgentikOSPage);
})();
