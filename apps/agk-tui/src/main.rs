mod data;
mod input;
mod model;
mod paste;
mod selection;
mod system_info;
mod terminal;
mod theme;
mod ui;

use std::{
    env,
    io::{self, Write},
    os::unix::process::CommandExt,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use anyhow::{Context, Result};
use crossterm::{
    cursor::Show,
    event::{
        self, DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture,
        Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers, KeyboardEnhancementFlags,
        MouseButton, MouseEvent, MouseEventKind, PopKeyboardEnhancementFlags,
        PushKeyboardEnhancementFlags,
    },
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use data::RegistryClient;
use input::Action;
use model::{App, Density, Focus, Mode, Overlay, SessionOrigin, SessionTarget, View, density};
use ratatui::{Terminal, backend::CrosstermBackend};
use ratatui_rmux::PaneState;
use rmux_sdk::{Pane, PaneCursor, PaneSnapshot, Rmux};
use selection::Selection;
use system_info::SystemInfoService;
use theme::Preferences;
use ui::SessionPreview;

const FRAME_TIME: Duration = Duration::from_millis(33);
const INPUT_DRAIN_BUDGET: Duration = Duration::from_millis(8);
const PREVIEW_REFRESH_TIME: Duration = Duration::from_millis(100);
const FOOTER_CONTEXT_REFRESH_TIME: Duration = Duration::from_millis(250);
const SESSION_START_TIMEOUT: Duration = Duration::from_secs(8);
const DOUBLE_TAB_TIME: Duration = Duration::from_millis(320);
const DOUBLE_CLICK_TIME: Duration = Duration::from_millis(400);
/// Consecutive failed refreshes before the RMUX connection is rebuilt.
const RECONNECT_AFTER_FAILURES: u32 = 3;
/// More recoveries than this inside the window mean a real fault, not a blip.
const MAX_RECOVERIES: usize = 5;
const RECOVERY_WINDOW: Duration = Duration::from_secs(60);

/// Set once the terminal accepted the kitty keyboard protocol, so it is
/// popped again on every exit path (including panics).
static KEYBOARD_ENHANCED: AtomicBool = AtomicBool::new(false);

#[derive(Debug)]
struct PendingSession {
    name: String,
    started_at: Instant,
    enter_terminal: bool,
}

impl PendingSession {
    fn created(name: String) -> Self {
        Self {
            name,
            started_at: Instant::now(),
            enter_terminal: true,
        }
    }

    fn renamed(name: String) -> Self {
        Self {
            name,
            started_at: Instant::now(),
            enter_terminal: false,
        }
    }
}

#[derive(Debug, Eq, PartialEq)]
enum PendingResolution {
    Waiting,
    Ready { name: String, enter_terminal: bool },
    TimedOut { name: String, registered: bool },
}

#[tokio::main]
async fn main() -> Result<()> {
    install_panic_hook();
    let environment = std::env::var("AGK_ENVIRONMENT")
        .unwrap_or_else(|_| std::env::var("USER").unwrap_or_else(|_| "agentik".into()));
    let (preferences, preference_warning) = match Preferences::load() {
        Ok(preferences) => (preferences, None),
        Err(error) => (
            Preferences::default(),
            Some(format!("Preferences could not be loaded: {error}")),
        ),
    };
    let registry = RegistryClient::discover(environment.clone());
    let mut rmux = connect_rmux().await?;

    let mut app = App::new(preferences);
    app.current_rmux_session = current_rmux_session();
    app.status = preference_warning;
    refresh(&rmux, &registry, &mut app).await?;

    enable_raw_mode().context("enable terminal raw mode")?;
    let _restore = RestoreTerminal;
    // Ask the terminal for its real colors before the event reader exists,
    // so the replies cannot be mistaken for key presses.
    app.terminal = terminal::probe();
    let mut stdout = io::stdout();
    enter_screen(&mut stdout)?;
    let mut terminal = Terminal::new(CrosstermBackend::new(stdout))?;
    terminal.clear()?;

    // A dropped RMUX connection or a transient terminal error must not drop
    // the user back to a bare shell: reconnect and keep the same UI state.
    let mut recoveries: Vec<Instant> = Vec::new();
    loop {
        let error = match run(&mut terminal, &rmux, &registry, &mut app).await {
            Ok(()) => return Ok(()),
            Err(error) => error,
        };
        log_event(&format!("recovering from: {error:#}"));
        let now = Instant::now();
        recoveries.retain(|at| now.duration_since(*at) < RECOVERY_WINDOW);
        recoveries.push(now);
        if recoveries.len() > MAX_RECOVERIES {
            return Err(error.context("AGK could not recover; see ~/.agentik/logs/agk-tui.log"));
        }
        app.status = Some(format!("Recovered · {error:#}"));
        app.selection = None;
        tokio::time::sleep(Duration::from_millis(400)).await;
        match connect_rmux().await {
            Ok(connection) => rmux = connection,
            Err(reconnect) => {
                log_event(&format!("reconnect failed: {reconnect:#}"));
                app.status = Some(format!("RMUX is unreachable · retrying · {reconnect:#}"));
            }
        }
        let _ = terminal.clear();
    }
}

async fn connect_rmux() -> Result<Rmux> {
    Rmux::builder()
        .default_timeout(Duration::from_secs(3))
        .connect_or_start()
        .await
        .context("connect to RMUX")
}

/// Puts the host terminal into AGK's interactive state.
fn enter_screen(stdout: &mut impl Write) -> Result<()> {
    terminal::push_title();
    execute!(
        stdout,
        EnterAlternateScreen,
        EnableMouseCapture,
        EnableBracketedPaste
    )?;
    // The kitty keyboard protocol is what makes Shift-Enter, Ctrl-Space and
    // Esc distinguishable; terminals without it keep the legacy encoding.
    if crossterm::terminal::supports_keyboard_enhancement().unwrap_or(false)
        && execute!(
            stdout,
            PushKeyboardEnhancementFlags(KeyboardEnhancementFlags::DISAMBIGUATE_ESCAPE_CODES)
        )
        .is_ok()
    {
        KEYBOARD_ENHANCED.store(true, Ordering::SeqCst);
    }
    Ok(())
}

/// Returns the host terminal to the state AGK found it in.
fn leave_screen(stdout: &mut impl Write) -> io::Result<()> {
    if KEYBOARD_ENHANCED.swap(false, Ordering::SeqCst) {
        let _ = execute!(stdout, PopKeyboardEnhancementFlags);
    }
    let result = execute!(
        stdout,
        DisableBracketedPaste,
        DisableMouseCapture,
        LeaveAlternateScreen,
        Show
    );
    terminal::pop_title();
    result
}

struct RestoreTerminal;

impl Drop for RestoreTerminal {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = leave_screen(&mut io::stdout());
    }
}

/// A panic must leave a usable terminal and a trace of what happened.
fn install_panic_hook() {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = disable_raw_mode();
        let _ = leave_screen(&mut io::stdout());
        log_event(&format!("panic: {info}"));
        default_hook(info);
    }));
}

fn log_path() -> Option<PathBuf> {
    env::var_os("HOME")
        .filter(|home| !home.is_empty())
        .map(|home| PathBuf::from(home).join(".agentik/logs/agk-tui.log"))
}

/// Appends one line to the local AGK log; never fails the caller.
fn log_event(message: &str) {
    let Some(path) = log_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    // Keep the log bounded without a rotation dependency.
    if std::fs::metadata(&path).is_ok_and(|metadata| metadata.len() > 512 * 1024) {
        let _ = std::fs::rename(&path, path.with_extension("log.1"));
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        let _ = writeln!(
            file,
            "{} pid={} {message}",
            unix_now() as u64,
            std::process::id()
        );
    }
}

fn unix_now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0.0, |elapsed| elapsed.as_secs_f64())
}

async fn refresh(rmux: &Rmux, registry: &RegistryClient, app: &mut App) -> Result<()> {
    let live_names = rmux
        .list_sessions()
        .await
        .context("list RMUX sessions")?
        .into_iter()
        .map(|name| name.as_ref().to_owned())
        .collect::<Vec<_>>();
    let mut snapshot = registry.load(&live_names);
    // Without fresh facts the modes are unknown, which reads as "plain pane".
    app.pane_facts = pane_facts().unwrap_or_default();
    data::apply_pane_facts(&mut snapshot, &app.pane_facts, unix_now());
    app.set_snapshot(snapshot);
    Ok(())
}

/// One cheap CLI call that tells what every session is really doing.
fn pane_facts() -> Option<std::collections::HashMap<String, data::PaneFacts>> {
    let output = Command::new("rmux")
        .args(["list-panes", "-a", "-F", data::PANE_FACTS_FORMAT])
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| data::parse_pane_facts(&String::from_utf8_lossy(&output.stdout)))
}

async fn run(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    rmux: &Rmux,
    registry: &RegistryClient,
    app: &mut App,
) -> Result<()> {
    let mut host = SystemInfoService::new();
    let mut last_refresh = Instant::now();
    let mut refresh_requested = false;
    let mut pending_session: Option<PendingSession> = None;
    let mut preview_cache = PreviewCache::default();
    let mut observed_status = app.status.clone();
    let mut status_since = Instant::now();
    let mut last_preview_refresh = Instant::now() - PREVIEW_REFRESH_TIME;
    let mut last_footer_refresh = Instant::now() - FOOTER_CONTEXT_REFRESH_TIME;
    let mut last_tab_at: Option<Instant> = None;
    let mut preview_refresh_requested = true;
    let mut rendered_layout = None;
    let mut refresh_failures = 0u32;
    let mut last_click: Option<(u16, u16, Instant)> = None;
    let mut grid_capture_pending = false;
    let mut shown_title: Option<String> = None;
    // Text a provider copied (OSC 52, copy-mode) lands in an RMUX buffer.
    // AGK mirrors panes without attaching a client, so it relays new buffers
    // to the real clipboard itself. The buffer present at startup is old.
    let mut seen_buffer = terminal::newest_buffer();

    'event_loop: loop {
        if app.status != observed_status {
            observed_status.clone_from(&app.status);
            status_since = Instant::now();
        } else if app.status.is_some() && status_since.elapsed() >= Duration::from_secs(4) {
            app.status = None;
            observed_status = None;
        }
        let refresh_interval = Duration::from_millis(app.preferences.refresh_ms.max(100));
        if refresh_requested || last_refresh.elapsed() >= refresh_interval {
            match refresh(rmux, registry, app).await {
                Ok(()) => {
                    refresh_failures = 0;
                    let resolution = pending_session
                        .as_ref()
                        .map(|pending| resolve_pending_session(app, pending, Instant::now()));
                    match resolution {
                        Some(PendingResolution::Ready {
                            name,
                            enter_terminal,
                        }) => {
                            pending_session = None;
                            if enter_terminal {
                                app.mode = Mode::Terminal;
                                app.focus = Focus::Detail;
                                app.expanded = false;
                                app.scroll_preview_live();
                                preview_cache.clear();
                                preview_refresh_requested = true;
                                app.status = Some(format!("Created and opened {name}"));
                            } else {
                                app.status = Some(format!("Renamed and selected {name}"));
                            }
                        }
                        Some(PendingResolution::TimedOut { name, registered }) => {
                            pending_session = None;
                            app.status = Some(if registered {
                                format!(
                                    "Session {name} was created but its provider terminal did not stay live"
                                )
                            } else {
                                format!("Session {name} did not appear in RMUX after creation")
                            });
                        }
                        Some(PendingResolution::Waiting) | None => {}
                    }
                    if refresh_requested {
                        app.status
                            .get_or_insert_with(|| "RMUX and MCP registries refreshed".into());
                    }
                }
                Err(error) => {
                    refresh_failures += 1;
                    if refresh_failures >= RECONNECT_AFTER_FAILURES {
                        return Err(error.context("lost the RMUX connection"));
                    }
                    app.status = Some(format!("Refresh failed: {error:#}"));
                }
            }
            let newest = terminal::newest_buffer();
            if newest.is_some() && newest != seen_buffer {
                if let Some(text) = newest
                    .as_ref()
                    .and_then(|stamp| terminal::buffer_text(&stamp.name))
                {
                    copy_to_clipboard(app, &text, "Provider copy");
                }
                seen_buffer = newest;
            }
            last_refresh = Instant::now();
            refresh_requested = false;
        }

        let title = app
            .selected_session_name()
            .filter(|_| app.view == View::Sessions)
            .map_or_else(|| "AGK".to_owned(), |name| format!("AGK · {name}"));
        if shown_title.as_deref() != Some(title.as_str()) {
            terminal::set_title(&title);
            shown_title = Some(title);
        }

        if last_footer_refresh.elapsed() >= FOOTER_CONTEXT_REFRESH_TIME {
            update_footer(&mut host, app);
            last_footer_refresh = Instant::now();
        }
        let size = terminal.size()?;
        let layout = (
            app.mode,
            app.view,
            app.expanded,
            app.preferences.split_preview,
            size.width,
            size.height,
        );
        if rendered_layout != Some(layout) {
            // Mode changes and responsive pane transitions rewrite large areas.
            // Force the physical terminal to match Ratatui's model instead of
            // trusting a stale differential buffer after an alternate-screen
            // transition or resize.
            terminal.clear()?;
            preview_cache.invalidate_layout();
            preview_refresh_requested = true;
            rendered_layout = Some(layout);
        }
        if app.mode == Mode::Terminal {
            let pane = ui::terminal_preview_area(size, app.expanded);
            app.preview_width = pane.width;
            app.preview_height = pane.height;
        }
        // A pane snapshot is an RPC and must never sit in front of queued
        // keyboard input. Capture only a visible preview, and never rediscover
        // the same pane on every frame or keystroke.
        let input_pending = event::poll(Duration::ZERO)?;
        let history_requested = app.preview_scroll > 0 && preview_cache.history.is_none();
        // The pane is frozen while the pointer is selecting, otherwise the
        // text would scroll away from under the highlight.
        if !app.selecting()
            && preview_is_visible(app)
            && (preview_refresh_requested
                || history_requested
                || (!input_pending && last_preview_refresh.elapsed() >= PREVIEW_REFRESH_TIME))
        {
            refresh_preview(rmux, app, &mut preview_cache).await;
            last_preview_refresh = Instant::now();
            preview_refresh_requested = false;
        } else if app.view != View::Sessions {
            preview_cache.clear();
        }
        let frame = terminal.draw(|frame| ui::draw(frame, app, preview_cache.view()))?;
        if grid_capture_pending || app.selecting() {
            app.preview_grid = app
                .preview_rect
                .map(|rect| ui::capture_preview_grid(frame.buffer, rect));
            grid_capture_pending = false;
        }

        if !input_pending && !event::poll(FRAME_TIME)? {
            continue;
        }
        let drain_started = Instant::now();
        let mut queued_events = vec![event::read()?];
        while drain_started.elapsed() < INPUT_DRAIN_BUDGET && event::poll(Duration::ZERO)? {
            queued_events.push(event::read()?);
        }

        for event in queued_events {
            let mut terminal_action = None;
            if !matches!(&event, Event::Key(key) if accepts_key(key) && key.code == KeyCode::Tab) {
                last_tab_at = None;
            }
            if let Event::Mouse(mouse) = &event
                && let Some(wheel) = program_wheel(app, mouse)
            {
                // A full-screen program has no RMUX scrollback: the wheel is
                // its own, exactly as in a directly attached terminal.
                let target = preview_cache
                    .target
                    .clone()
                    .or_else(|| app.current_session().map(|run| run.rmux_session.clone()));
                if let Some(target) = target {
                    send_wheel(&target, &wheel);
                    app.scroll_preview_live();
                    preview_refresh_requested = true;
                }
                continue;
            }
            if let Event::Mouse(mouse) = &event {
                match select_with_mouse(app, mouse, &mut last_click, Instant::now()) {
                    SelectionOutcome::Ignored => {}
                    SelectionOutcome::Started => grid_capture_pending = true,
                    SelectionOutcome::Consumed => continue,
                    SelectionOutcome::Copy(text) => {
                        copy_to_clipboard(app, &text, "Copied");
                        preview_refresh_requested = true;
                        continue;
                    }
                }
            }
            if app.mode == Mode::Terminal {
                match &event {
                    Event::Key(key) if accepts_key(key) && terminal_returns_to_control(key) => {
                        app.mode = Mode::Control;
                        app.view = View::Sessions;
                        app.focus = Focus::List;
                        app.expanded = false;
                        app.scroll_preview_live();
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key) if accepts_key(key) && key.code == KeyCode::Tab => {
                        let double = register_tab(&mut last_tab_at, Instant::now());
                        let _ = session_tab(app, true, double);
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::Detail
                            && !program_owns_screen(app)
                            && terminal_scroll_key(app, key) =>
                    {
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::List
                            && terminal_sidebar_control_key(key) =>
                    {
                        // The visible sidebar remains the Sessions control
                        // surface while a provider owns the right pane. Route
                        // its actions through the normal dispatcher so n/x/r
                        // cannot be swallowed by terminal input handling.
                        app.mode = Mode::Control;
                        app.view = View::Sessions;
                        app.expanded = false;
                        let size = terminal.size()?;
                        let detail_available = app.current_session().is_some();
                        terminal_action = Some(input::handle_key_for_layout(
                            app,
                            *key,
                            detail_available,
                            density(size.width, size.height) == Density::Compact,
                        ));
                        preview_cache.clear();
                        preview_refresh_requested = true;
                    }
                    Event::Key(key)
                        if accepts_key(key)
                            && app.focus == Focus::List
                            && terminal_top_nav_key(app, key) =>
                    {
                        preview_cache.clear();
                        preview_refresh_requested = true;
                        continue;
                    }
                    Event::Key(key) if accepts_key(key) && app.focus == Focus::List => {
                        let selected_before = app.selected_session_name().map(str::to_owned);
                        if terminal_sidebar_key(app, key)
                            && selected_before.as_deref() != app.selected_session_name()
                        {
                            preview_cache.clear();
                            preview_refresh_requested = true;
                        }
                        continue;
                    }
                    Event::Mouse(mouse) => {
                        let size = terminal.size()?;
                        match ui::terminal_focus_at(size, app.expanded, mouse.column, mouse.row) {
                            Some(Focus::List) => {
                                let selected_before =
                                    app.selected_session_name().map(str::to_owned);
                                app.expanded = false;
                                app.focus = Focus::List;
                                match mouse.kind {
                                    MouseEventKind::ScrollUp => {
                                        for _ in 0..3 {
                                            app.select_previous();
                                        }
                                    }
                                    MouseEventKind::ScrollDown => {
                                        for _ in 0..3 {
                                            app.select_next();
                                        }
                                    }
                                    _ => {}
                                }
                                if selected_before.as_deref() != app.selected_session_name() {
                                    preview_cache.clear();
                                    preview_refresh_requested = true;
                                }
                                continue;
                            }
                            Some(Focus::Detail) => {
                                app.focus = Focus::Detail;
                                match mouse.kind {
                                    MouseEventKind::ScrollUp => {
                                        app.scroll_preview_up(3);
                                        preview_refresh_requested = true;
                                        continue;
                                    }
                                    MouseEventKind::ScrollDown => {
                                        app.scroll_preview_down(3);
                                        preview_refresh_requested = true;
                                        continue;
                                    }
                                    _ => {}
                                }
                            }
                            Some(Focus::Nav) | None => continue,
                        }
                    }
                    Event::Resize(_, _) => {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        continue;
                    }
                    _ => {}
                }
                if terminal_action.is_none() && app.focus == Focus::Detail {
                    if app.preview_scroll > 0 {
                        app.scroll_preview_live();
                        preview_refresh_requested = true;
                    }
                    send_terminal_event(rmux, app, &mut preview_cache, event.clone()).await;
                }
                if terminal_action.is_none() {
                    continue;
                }
            }

            let detail_available = detail_available(app);
            let preview_scroll_before = app.preview_scroll;
            let selected_session_before = app.selected_session_name().map(str::to_owned);
            let action = if let Some(action) = terminal_action {
                action
            } else {
                match event {
                    Event::Mouse(mouse) => {
                        let outcome = handle_mouse(app, mouse, terminal.size()?);
                        if outcome.preview_scrolled {
                            preview_refresh_requested = true;
                        }
                        if outcome.activate_session {
                            Action::EnterTerminal
                        } else {
                            Action::None
                        }
                    }
                    Event::Key(key)
                        if accepts_key(&key)
                            && key.code == KeyCode::Tab
                            && app.view == View::Sessions =>
                    {
                        let double = register_tab(&mut last_tab_at, Instant::now());
                        if session_tab(app, detail_available, double) {
                            Action::EnterTerminal
                        } else {
                            Action::None
                        }
                    }
                    Event::Key(key) if accepts_key(&key) => {
                        let size = terminal.size()?;
                        input::handle_key_for_layout(
                            app,
                            key,
                            detail_available,
                            density(size.width, size.height) == Density::Compact,
                        )
                    }
                    Event::Paste(text) => input::handle_paste(app, &text),
                    Event::Resize(_, _) => {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                        Action::None
                    }
                    _ => Action::None,
                }
            };
            if app.preview_scroll != preview_scroll_before {
                preview_refresh_requested = true;
            }
            if selected_session_before.as_deref() != app.selected_session_name() {
                preview_cache.clear();
                preview_refresh_requested = true;
            }
            match action {
                Action::None => {}
                Action::Quit => break 'event_loop,
                Action::Reload => return reload_agk(terminal),
                Action::Refresh => {
                    registry.forget_detected_projects();
                    refresh_requested = true;
                    preview_cache.clear();
                    preview_refresh_requested = true;
                }
                Action::PersistPreferences => match app.preferences.save() {
                    Ok(()) => {
                        if app.status.is_none() {
                            app.status = Some("Preferences saved".into());
                        }
                    }
                    Err(error) => {
                        app.status = Some(format!("Could not save preferences: {error}"));
                    }
                },
                Action::InstallProvider { id } => match install_provider(terminal, &id) {
                    Ok(true) => {
                        app.status = Some(format!("Provider {id} installed and verified"));
                        refresh_requested = true;
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                    Ok(false) => {
                        app.status = Some(format!("Provider {id} setup did not complete"));
                        refresh_requested = true;
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Provider setup failed: {error:#}"));
                        rendered_layout = None;
                        preview_refresh_requested = true;
                    }
                },
                Action::EnterTerminal => {
                    if enter_selected_terminal(app) {
                        preview_cache.invalidate_layout();
                        preview_refresh_requested = true;
                    }
                }
                Action::CreateSession { kind, name } => {
                    match create_session(kind.slug(), &name, app.session_origin.as_ref()) {
                        Ok(message) => {
                            app.session_origin = None;
                            app.status = Some(format!("{message} · opening provider terminal…"));
                            pending_session = Some(PendingSession::created(name));
                            refresh_requested = true;
                        }
                        Err(error) => {
                            app.status = Some(format!("Session creation failed: {error:#}"));
                            app.overlay = Overlay::NewName { kind, value: name };
                        }
                    }
                }
                Action::OpenAgent { id, session } => match open_agent(&id, &session) {
                    Ok(message) => {
                        app.status = Some(format!("{message} · opening agent terminal…"));
                        pending_session = Some(PendingSession::created(session));
                        refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Agent launch failed: {error:#}"));
                    }
                },
                Action::ResumeConversation { target } => match resume_conversation(&target) {
                    Ok(message) => {
                        app.status = Some(format!("{message} · opening synced conversation…"));
                        pending_session = Some(PendingSession::created(target.name));
                        refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Conversation resume failed: {error:#}"));
                    }
                },
                Action::RenameSession { target, name } => match rename_session(&target, &name) {
                    Ok(message) => {
                        if app.current_rmux_session.as_deref() == Some(target.rmux_session.as_str())
                        {
                            app.current_rmux_session = Some(name.clone());
                        }
                        app.status = Some(message);
                        pending_session = Some(PendingSession::renamed(name));
                        refresh_requested = true;
                        preview_cache.clear();
                        preview_refresh_requested = true;
                    }
                    Err(error) => {
                        app.status = Some(format!("Session rename failed: {error:#}"));
                    }
                },
                Action::CloseSession { target } => {
                    if app.current_rmux_session.as_deref() == Some(target.rmux_session.as_str()) {
                        app.status = Some(
                            "AGK cannot close the RMUX session that is running this interface"
                                .into(),
                        );
                    } else {
                        match close_session(&target) {
                            Ok(message) => {
                                app.status = Some(message);
                                refresh_requested = true;
                                preview_cache.clear();
                                preview_refresh_requested = true;
                            }
                            Err(error) => {
                                app.status = Some(format!("Session close failed: {error:#}"));
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn reload_agk(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>) -> Result<()> {
    disable_raw_mode().context("leave raw mode before AGK reload")?;
    leave_screen(terminal.backend_mut()).context("restore terminal before AGK reload")?;
    let executable = env::current_exe().context("resolve the running AGK executable")?;
    let error = Command::new(&executable).exec();
    Err(error).with_context(|| format!("reload AGK from {}", executable.display()))
}

fn install_provider(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    provider: &str,
) -> Result<bool> {
    disable_raw_mode().context("leave raw mode for provider setup")?;
    leave_screen(terminal.backend_mut()).context("leave AGK screen for provider setup")?;

    let installer = env::var_os("AGK_TERMINAL_BIN").unwrap_or_else(|| "agk-terminal".into());
    let result = Command::new(installer)
        .args(["provider", "install", provider])
        .status()
        .context("run AGK-TUI provider installer");

    enable_raw_mode().context("restore raw mode after provider setup")?;
    enter_screen(terminal.backend_mut()).context("restore AGK screen after provider setup")?;
    terminal.clear().context("clear restored AGK screen")?;
    result.map(|status| status.success())
}

fn update_footer(host: &mut SystemInfoService, app: &mut App) {
    let directory = footer_directory(app);
    let usage = footer_model_usage(app);
    host.refresh_for_context(
        usage.map(data::ModelUsageRecord::io_tokens),
        usage.map(|usage| usage.model.as_str()),
        app.snapshot.runtimes.len(),
        directory.as_deref(),
    );
    app.footer = host.snapshot().clone();
}

fn footer_model_usage(app: &App) -> Option<&data::ModelUsageRecord> {
    let session = app.selected_session_name()?;
    app.snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == session)
        .and_then(|runtime| runtime.model_usage.first())
}

fn footer_directory(app: &App) -> Option<PathBuf> {
    if app.view == View::Projects {
        return app
            .current_object()
            .filter(|object| object.kind.eq_ignore_ascii_case("project"))
            .and_then(|object| object.path.as_deref())
            .map(PathBuf::from);
    }

    let session = app.selected_session_name()?;
    app.snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == session)
        .map(|runtime| PathBuf::from(&runtime.cwd))
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
enum PreviewState {
    Live,
    History,
    CurrentSession,
    #[default]
    Unavailable,
}

#[derive(Default)]
struct PreviewCache {
    session: Option<String>,
    handle: Option<Pane>,
    target: Option<String>,
    pane: Option<PaneState>,
    history: Option<Vec<String>>,
    size: Option<(u16, u16)>,
    /// Creation time of the RMUX session the handle was resolved for.
    created: Option<f64>,
    state: PreviewState,
}

impl PreviewCache {
    fn clear(&mut self) {
        self.session = None;
        self.handle = None;
        self.target = None;
        self.pane = None;
        self.history = None;
        self.size = None;
        self.created = None;
        self.state = PreviewState::Unavailable;
    }

    /// A session restarted under the same name is a new pane: forget the
    /// old handle instead of typing into a process that no longer exists.
    fn follow_session(&mut self, created: Option<f64>) {
        if created.is_some() && self.created != created {
            if self.created.is_some() {
                self.invalidate_handle();
            }
            self.created = created;
        }
    }

    fn select(&mut self, session: &str) {
        if self.session.as_deref() != Some(session) {
            self.clear();
            self.session = Some(session.to_owned());
        }
    }

    fn invalidate_layout(&mut self) {
        // Keep the last correct frame visible while the resized snapshot is
        // fetched. Dropping the whole cache here produces a visible offline
        // flash every time focus or fullscreen changes.
        self.size = None;
    }

    fn view(&self) -> SessionPreview<'_> {
        match self.state {
            PreviewState::Live => self
                .pane
                .as_ref()
                .map(SessionPreview::Live)
                .unwrap_or(SessionPreview::Unavailable),
            PreviewState::History => self
                .history
                .as_deref()
                .map(SessionPreview::History)
                .unwrap_or(SessionPreview::Unavailable),
            PreviewState::CurrentSession => SessionPreview::CurrentSession,
            PreviewState::Unavailable => SessionPreview::Unavailable,
        }
    }

    fn invalidate_handle(&mut self) {
        self.handle = None;
        self.target = None;
        self.size = None;
    }
}

fn preview_is_visible(app: &App) -> bool {
    app.view == View::Sessions
        && (app.mode == Mode::Terminal
            || (app.preview_width > 1
                && app.preview_height > 1
                && (app.focus == Focus::Detail || app.preferences.split_preview)))
}

async fn cached_primary_pane(
    rmux: &Rmux,
    session_name: &str,
    cache: &mut PreviewCache,
) -> Option<Pane> {
    cache.select(session_name);
    if let Some(pane) = cache.handle.clone() {
        return Some(pane);
    }
    let pane = primary_pane(rmux, session_name).await?;
    cache.target = Some(
        pane.id()
            .await
            .ok()
            .flatten()
            .map(|id| id.to_string())
            .unwrap_or_else(|| session_name.to_owned()),
    );
    cache.handle = Some(pane.clone());
    Some(pane)
}

async fn refresh_preview(rmux: &Rmux, app: &App, cache: &mut PreviewCache) {
    let Some(runtime) = app.current_session() else {
        cache.clear();
        return;
    };
    cache.select(&runtime.rmux_session);
    cache.follow_session(
        app.pane_facts
            .get(&runtime.rmux_session)
            .map(|facts| facts.created),
    );
    if app.selected_is_current_rmux_session() {
        cache.invalidate_handle();
        cache.pane = None;
        cache.history = None;
        cache.state = PreviewState::CurrentSession;
        return;
    }
    if !runtime.live {
        cache.invalidate_handle();
        cache.pane = None;
        cache.history = None;
        cache.state = PreviewState::Unavailable;
        return;
    }
    let session_name = runtime.rmux_session.clone();
    let Some(pane) = cached_primary_pane(rmux, &session_name, cache).await else {
        cache.state = PreviewState::Unavailable;
        return;
    };
    let width = app.preview_width;
    let height = app.preview_height;
    let target = cache.target.clone().unwrap_or_else(|| session_name.clone());
    if width > 1 && height > 1 && cache.size != Some((width, height)) {
        // A pane cannot grow beyond its window. The SDK's pane.resize() is
        // therefore a no-op for the usual one-pane AGK sessions; resize the
        // owning rmux window so the agent receives SIGWINCH.
        let _ = resize_window(&target, width, height);
        cache.size = Some((width, height));
    }
    if app.preview_scroll > 0 {
        if cache.history.is_none() {
            cache.history = capture_history(&target);
        }
        if cache.history.is_some() {
            cache.pane = None;
            cache.state = PreviewState::History;
            return;
        }
    }
    cache.history = None;
    let snapshot = pane.snapshot().await.ok();
    if snapshot.is_none() {
        cache.invalidate_handle();
    }
    cache.pane = snapshot
        .map(|snapshot| crop_snapshot_to_height(snapshot, height))
        .map(PaneState::from_snapshot);
    cache.state = if cache.pane.is_some() {
        PreviewState::Live
    } else {
        PreviewState::Unavailable
    };
}

fn resize_window(target: &str, width: u16, height: u16) -> bool {
    Command::new("rmux")
        .args([
            "resize-window",
            "-t",
            target,
            "-x",
            &width.to_string(),
            "-y",
            &height.to_string(),
        ])
        .output()
        .is_ok_and(|output| output.status.success())
}

fn crop_snapshot_to_height(snapshot: PaneSnapshot, height: u16) -> PaneSnapshot {
    if height == 0 || snapshot.rows <= height || snapshot.cols == 0 {
        return snapshot;
    }
    let first_row = snapshot.rows - height;
    let first_cell = usize::from(first_row) * usize::from(snapshot.cols);
    // A snapshot whose cell count disagrees with its geometry is rendered
    // as-is rather than sliced out of bounds.
    let Some(tail) = snapshot.cells.get(first_cell..) else {
        return snapshot;
    };
    let cells = tail.to_vec();
    let cursor_in_view = snapshot.cursor.row >= first_row;
    let cursor = PaneCursor::new(
        snapshot.cursor.row.saturating_sub(first_row),
        snapshot.cursor.col,
        snapshot.cursor.visible && cursor_in_view,
        snapshot.cursor.style,
    );
    PaneSnapshot {
        cols: snapshot.cols,
        rows: height,
        cells,
        cursor,
        revision: snapshot.revision,
    }
}

fn capture_history(target: &str) -> Option<Vec<String>> {
    let output = Command::new("rmux")
        .args(["capture-pane", "-p", "-t", target, "-S", "-500000"])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(
        String::from_utf8_lossy(&output.stdout)
            .lines()
            .map(str::to_owned)
            .collect(),
    )
}

fn create_session(kind: &str, name: &str, origin: Option<&SessionOrigin>) -> Result<String> {
    let output = Command::new("agk")
        .args(create_session_arguments(kind, name, origin))
        .output()
        .context("run `agk new`")?;
    if !output.status.success() {
        let error = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        anyhow::bail!(if error.is_empty() {
            format!("agk exited with {}", output.status)
        } else {
            error
        });
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Created {name}")
    } else {
        message
    })
}

fn create_session_arguments(kind: &str, name: &str, origin: Option<&SessionOrigin>) -> Vec<String> {
    let mut arguments = vec!["new".to_owned(), kind.to_owned(), name.to_owned()];
    if let Some(origin) = origin {
        arguments.extend([
            "--cwd".to_owned(),
            origin.cwd.clone(),
            "--project".to_owned(),
            origin.project.clone(),
        ]);
    }
    arguments
}

fn open_agent(id: &str, session: &str) -> Result<String> {
    let mut command = Command::new("agk");
    command.args(["specialist", "start", id]);
    if !session.is_empty() {
        command.args(["--session", session]);
    }
    let output = command.output().context("run `agk specialist start`")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Opened {id}")
    } else {
        message
    })
}

fn resume_conversation(target: &SessionTarget) -> Result<String> {
    let mut command = Command::new("agk");
    if target.managed {
        command.args(["restart", target.id.as_str()]);
    } else {
        let native = target
            .native_session
            .as_deref()
            .context("synced conversation has no Hermes session id")?;
        command.args([
            "new",
            "hermes",
            target.name.as_str(),
            "--native-session",
            native,
        ]);
        if !target.cwd.is_empty() {
            command.args(["--cwd", target.cwd.as_str()]);
        }
        if let Some(profile) = target.hermes_profile.as_deref() {
            command.args(["--profile", profile]);
        }
    }
    let output = command
        .output()
        .context("resume Hermes conversation through AGK")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    let message = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    Ok(if message.is_empty() {
        format!("Resumed {}", target.name)
    } else {
        message
    })
}

fn resolve_pending_session(
    app: &mut App,
    pending: &PendingSession,
    now: Instant,
) -> PendingResolution {
    let runtime = app
        .snapshot
        .runtimes
        .iter()
        .find(|runtime| runtime.name == pending.name);
    let registered = runtime.is_some();
    let ready = runtime.is_some_and(|runtime| !pending.enter_terminal || runtime.live);
    if ready && app.select_session_by_name(&pending.name) {
        return PendingResolution::Ready {
            name: pending.name.clone(),
            enter_terminal: pending.enter_terminal,
        };
    }
    if now.duration_since(pending.started_at) >= SESSION_START_TIMEOUT {
        if registered {
            app.select_session_by_name(&pending.name);
        }
        return PendingResolution::TimedOut {
            name: pending.name.clone(),
            registered,
        };
    }
    PendingResolution::Waiting
}

fn rename_session(target: &SessionTarget, name: &str) -> Result<String> {
    let mut command = if target.managed {
        let mut command = Command::new("agk");
        command.args(["rename", &target.name, name]);
        command
    } else {
        let mut command = Command::new("rmux");
        command.args(["rename-session", "-t", &target.rmux_session, name]);
        command
    };
    let output = command.output().context("rename selected session")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    Ok(format!("Renamed {} to {name}", target.name))
}

fn close_session(target: &SessionTarget) -> Result<String> {
    if !target.managed && !rmux_session_exists(&target.rmux_session) {
        return Ok(format!("{} was already closed", target.name));
    }
    let mut command = if target.managed {
        let mut command = Command::new("agk");
        command.args(["close", "--yes", &target.name]);
        command
    } else {
        let mut command = Command::new("rmux");
        command.args(["kill-session", "-t", &target.rmux_session]);
        command
    };
    let output = command.output().context("close selected session")?;
    if !output.status.success() {
        anyhow::bail!(command_error(&output));
    }
    if rmux_session_exists(&target.rmux_session) {
        anyhow::bail!("RMUX session {} is still running", target.rmux_session);
    }
    Ok(format!("Closed {}", target.name))
}

fn rmux_session_exists(name: &str) -> bool {
    Command::new("rmux")
        .args(["has-session", "-t", name])
        .output()
        .is_ok_and(|output| output.status.success())
}

fn command_error(output: &std::process::Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    if !stderr.is_empty() {
        stderr
    } else if !stdout.is_empty() {
        stdout
    } else {
        format!("command exited with {}", output.status)
    }
}

async fn send_terminal_event(rmux: &Rmux, app: &App, cache: &mut PreviewCache, event: Event) {
    let Some(runtime) = app.current_session() else {
        return;
    };
    let Some(pane) = cached_primary_pane(rmux, &runtime.rmux_session, cache).await else {
        return;
    };
    let result = match event {
        Event::Paste(text) => {
            // RMUX's paste path honors the pane's own bracketed-paste mode.
            // The manual path remains for an empty paste (how agent CLIs
            // learn that the clipboard holds an image) and as a fallback.
            let target = cache
                .target
                .clone()
                .unwrap_or_else(|| runtime.rmux_session.clone());
            if terminal::paste_into_pane(&target, &text) {
                Ok(())
            } else {
                paste::send(&pane, &text).await
            }
        }
        Event::Key(key) if accepts_key(&key) => {
            if key.code == KeyCode::Enter
                && key
                    .modifiers
                    .intersects(KeyModifiers::SHIFT | KeyModifiers::ALT)
            {
                if current_pane_facts(app).is_some_and(data::PaneFacts::runs_shell) {
                    // A shell continues the command line after a backslash.
                    match pane.send_text("\\").await {
                        Ok(_) => pane.send_key("Enter").await.map(|_| ()),
                        Err(error) => Err(error),
                    }
                } else {
                    // Ctrl-J is the one "new line without sending" key that
                    // Hermes, Claude Code, Codex and OpenCode all accept.
                    pane.send_key("C-j").await.map(|_| ())
                }
            } else if let KeyCode::Char(character) = key.code
                && !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT)
            {
                pane.send_text(character.to_string()).await.map(|_| ())
            } else if let Some(token) = rmux_key_token(key) {
                pane.send_key(token).await.map(|_| ())
            } else {
                return;
            }
        }
        Event::Mouse(_) => return,
        _ => return,
    };
    if result.is_err() {
        cache.invalidate_handle();
    }
}

async fn primary_pane(rmux: &Rmux, session_name: &str) -> Option<Pane> {
    rmux.find_panes()
        .session(session_name)
        .all()
        .await
        .ok()?
        .into_iter()
        .next()
        .map(|discovered| discovered.pane)
}

fn rmux_key_token(key: KeyEvent) -> Option<String> {
    let shift = key.modifiers.contains(KeyModifiers::SHIFT);
    let alt = key.modifiers.contains(KeyModifiers::ALT);
    let control = key.modifiers.contains(KeyModifiers::CONTROL);
    if matches!(key.code, KeyCode::Backspace) && (shift || alt || control) {
        return Some("C-w".into());
    }
    if matches!(key.code, KeyCode::Delete) && (shift || alt) {
        return Some("M-d".into());
    }
    if matches!(key.code, KeyCode::Left) && (alt || control) {
        return Some("M-b".into());
    }
    if matches!(key.code, KeyCode::Right) && (alt || control) {
        return Some("M-f".into());
    }
    let base = match key.code {
        // rmux's canonical token is `BSpace`; unknown names are sent as
        // literal text, which is why AGK previously typed "Backspace" into
        // the selected agent instead of deleting a character.
        KeyCode::Backspace => "BSpace".into(),
        KeyCode::Enter => "Enter".into(),
        KeyCode::Left => "Left".into(),
        KeyCode::Right => "Right".into(),
        KeyCode::Up => "Up".into(),
        KeyCode::Down => "Down".into(),
        KeyCode::Home => "Home".into(),
        KeyCode::End => "End".into(),
        KeyCode::PageUp => "PageUp".into(),
        KeyCode::PageDown => "PageDown".into(),
        KeyCode::Tab => "Tab".into(),
        KeyCode::BackTab => "BTab".into(),
        KeyCode::Delete => "Delete".into(),
        KeyCode::Insert => "IC".into(),
        KeyCode::F(number) => format!("F{number}"),
        // With the kitty keyboard protocol Ctrl-Space arrives as a real
        // space plus a modifier instead of NUL.
        KeyCode::Char(' ') if control => return Some("C-Space".into()),
        KeyCode::Char(character) => character.to_string(),
        KeyCode::Null => "C-Space".into(),
        KeyCode::Esc => "Escape".into(),
        _ => return None,
    };
    if matches!(key.code, KeyCode::Null) {
        return Some(base);
    }
    let mut prefixes = Vec::new();
    if key.modifiers.contains(KeyModifiers::CONTROL) {
        prefixes.push("C");
    }
    if key.modifiers.contains(KeyModifiers::ALT) {
        prefixes.push("M");
    }
    if key.modifiers.contains(KeyModifiers::SHIFT)
        && !matches!(key.code, KeyCode::Char(_) | KeyCode::BackTab)
    {
        prefixes.push("S");
    }
    if prefixes.is_empty() {
        Some(base)
    } else {
        Some(format!("{}-{base}", prefixes.join("-")))
    }
}

fn current_rmux_session() -> Option<String> {
    resolve_current_rmux_session_with(
        |name| std::env::var(name).ok(),
        |pane| {
            let output = Command::new("rmux")
                .args(["display-message", "-p", "-t", pane, "#{session_name}"])
                .output()
                .ok()?;
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        },
    )
}

fn resolve_current_rmux_session_with<E, D>(mut env_var: E, mut display_session: D) -> Option<String>
where
    E: FnMut(&str) -> Option<String>,
    D: FnMut(&str) -> Option<String>,
{
    fn nonempty(value: String) -> Option<String> {
        let value = value.trim();
        (!value.is_empty()).then(|| value.to_owned())
    }

    env_var("RMUX_PANE")
        .and_then(nonempty)
        .and_then(|pane| display_session(&pane))
        .and_then(nonempty)
        .or_else(|| env_var("RMUX_SESSION").and_then(nonempty))
        .or_else(|| env_var("TMUX_SESSION").and_then(nonempty))
}

fn current_pane_facts(app: &App) -> Option<&data::PaneFacts> {
    app.current_session()
        .filter(|runtime| runtime.live)
        .and_then(|runtime| app.pane_facts.get(&runtime.rmux_session))
}

/// True while a full-screen program (not RMUX) owns scrolling in the pane.
fn program_owns_screen(app: &App) -> bool {
    !app.selected_is_current_rmux_session()
        && current_pane_facts(app).is_some_and(|facts| facts.alternate)
}

/// How one wheel notch is delivered to a full-screen program.
#[derive(Clone, Debug, Eq, PartialEq)]
enum WheelInput {
    /// A real mouse report, for programs that asked for the mouse.
    Report(String),
    /// Arrow keys, for pagers and editors that did not.
    Keys(&'static str),
}

const WHEEL_LINES: &str = "3";

/// Translates a wheel event over the mirrored pane of a full-screen program.
fn program_wheel(app: &App, mouse: &MouseEvent) -> Option<WheelInput> {
    let up = match mouse.kind {
        MouseEventKind::ScrollUp => true,
        MouseEventKind::ScrollDown => false,
        _ => return None,
    };
    if app.view != View::Sessions || app.overlay.is_open() || !program_owns_screen(app) {
        return None;
    }
    let rect = app
        .preview_rect
        .filter(|rect| selection::inside(*rect, mouse.column, mouse.row))?;
    let facts = current_pane_facts(app)?;
    let keys = WheelInput::Keys(if up { "Up" } else { "Down" });
    if !facts.mouse {
        return Some(keys);
    }
    let button = if up { 64u16 } else { 65 };
    let column = mouse.column - rect.x + 1;
    let row = mouse.row - rect.y + 1;
    if facts.mouse_sgr {
        return Some(WheelInput::Report(format!(
            "\x1b[<{button};{column};{row}M"
        )));
    }
    // The legacy encoding is one byte per value; stay inside ASCII.
    let byte = |value: u16| u8::try_from(value + 32).ok().filter(u8::is_ascii);
    Some(match (byte(button), byte(column), byte(row)) {
        (Some(button), Some(column), Some(row)) => WheelInput::Report(format!(
            "\x1b[M{}{}{}",
            button as char, column as char, row as char
        )),
        _ => keys,
    })
}

fn send_wheel(target: &str, wheel: &WheelInput) {
    let mut command = Command::new("rmux");
    command.args(["send-keys", "-t", target]);
    match wheel {
        WheelInput::Report(report) => command.args(["-l", report.as_str()]),
        WheelInput::Keys(key) => command.args(["-N", WHEEL_LINES, key]),
    };
    let _ = command.output();
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum SelectionOutcome {
    /// Not a selection gesture; normal click and scroll handling applies.
    Ignored,
    /// A press inside the pane: it may become a drag, and still focuses.
    Started,
    Consumed,
    Copy(String),
}

/// Select-to-copy inside the mirrored pane: drag for a range, double-click
/// for the word under the pointer.
fn select_with_mouse(
    app: &mut App,
    mouse: &MouseEvent,
    last_click: &mut Option<(u16, u16, Instant)>,
    now: Instant,
) -> SelectionOutcome {
    let rect = app
        .preview_rect
        .filter(|_| app.view == View::Sessions && !app.overlay.is_open());
    match mouse.kind {
        MouseEventKind::Down(MouseButton::Left) => {
            let Some(rect) = rect.filter(|rect| selection::inside(*rect, mouse.column, mouse.row))
            else {
                app.selection = None;
                *last_click = None;
                return SelectionOutcome::Ignored;
            };
            let double = last_click.is_some_and(|(column, row, at)| {
                column == mouse.column
                    && row == mouse.row
                    && now.duration_since(at) <= DOUBLE_CLICK_TIME
            });
            if double
                && let Some(grid) = app.preview_grid.as_ref().filter(|grid| grid.rect == rect)
                && let Some(word) = selection::word_at(grid, mouse.column, mouse.row)
            {
                *last_click = None;
                app.selection = None;
                return SelectionOutcome::Copy(selection::extract(grid, &word));
            }
            *last_click = Some((mouse.column, mouse.row, now));
            app.selection = Some(Selection::at(mouse.column, mouse.row));
            SelectionOutcome::Started
        }
        MouseEventKind::Drag(MouseButton::Left) => match (app.selection.as_mut(), rect) {
            (Some(selection), Some(rect)) => {
                selection.drag_to(mouse.column, mouse.row, rect);
                SelectionOutcome::Consumed
            }
            _ => SelectionOutcome::Ignored,
        },
        MouseEventKind::Up(MouseButton::Left) => match app.selection.take() {
            Some(selection) if selection.moved => {
                let text = app
                    .preview_grid
                    .as_ref()
                    .map(|grid| selection::extract(grid, &selection))
                    .unwrap_or_default();
                if text.is_empty() {
                    SelectionOutcome::Consumed
                } else {
                    SelectionOutcome::Copy(text)
                }
            }
            _ => SelectionOutcome::Ignored,
        },
        _ => SelectionOutcome::Ignored,
    }
}

fn copy_to_clipboard(app: &mut App, text: &str, verb: &str) {
    let lines = text.lines().count().max(1);
    let size = if lines > 1 {
        format!("{lines} lines")
    } else {
        format!("{} characters", text.chars().count())
    };
    app.status = Some(match terminal::copy(text) {
        Ok(terminal::CopyRoute::Native) => format!("{verb} · {size} on your clipboard"),
        // Over SSH only the terminal itself can reach the clipboard, and it
        // does not confirm: say what was done, not what cannot be known.
        Ok(terminal::CopyRoute::Osc52) => {
            format!("{verb} · {size} sent to your terminal's clipboard (OSC 52)")
        }
        Err(error) => format!("Copy failed: {error}"),
    });
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
struct MouseOutcome {
    preview_scrolled: bool,
    activate_session: bool,
}

fn handle_mouse(
    app: &mut App,
    mouse: MouseEvent,
    terminal_size: ratatui::layout::Size,
) -> MouseOutcome {
    let mut outcome = MouseOutcome::default();
    if !matches!(
        mouse.kind,
        MouseEventKind::ScrollUp | MouseEventKind::ScrollDown
    ) && !matches!(mouse.kind, MouseEventKind::Down(MouseButton::Left))
    {
        return outcome;
    }
    if let Some(focus) = ui::focus_at(app, terminal_size, mouse.column, mouse.row) {
        // The top navigation is a direct horizontal axis, never a focus stop.
        // Panel focus remains stable when the user merely clicks its chrome.
        if focus != Focus::Nav {
            app.focus = focus;
            outcome.activate_session = app.view == View::Sessions
                && focus == Focus::Detail
                && matches!(mouse.kind, MouseEventKind::Down(MouseButton::Left));
        }
    }
    match mouse.kind {
        MouseEventKind::ScrollUp if app.focus == Focus::List => {
            for _ in 0..3 {
                app.select_previous();
            }
        }
        MouseEventKind::ScrollDown if app.focus == Focus::List => {
            for _ in 0..3 {
                app.select_next();
            }
        }
        MouseEventKind::ScrollUp if app.view == View::Sessions => {
            app.scroll_preview_up(3);
            outcome.preview_scrolled = true;
        }
        MouseEventKind::ScrollDown if app.view == View::Sessions => {
            app.scroll_preview_down(3);
            outcome.preview_scrolled = true;
        }
        MouseEventKind::ScrollUp => app.detail_scroll = app.detail_scroll.saturating_sub(3),
        MouseEventKind::ScrollDown => app.detail_scroll = app.detail_scroll.saturating_add(3),
        _ => {}
    }
    outcome
}

fn accepts_key(key: &KeyEvent) -> bool {
    matches!(key.kind, KeyEventKind::Press | KeyEventKind::Repeat)
}

fn terminal_returns_to_control(key: &KeyEvent) -> bool {
    key.code == KeyCode::Char('g') && key.modifiers.contains(KeyModifiers::CONTROL)
}

fn terminal_sidebar_control_key(key: &KeyEvent) -> bool {
    (key.modifiers.is_empty() && matches!(key.code, KeyCode::Char('n' | 'x' | 'r' | 'q')))
        || (key.modifiers == KeyModifiers::CONTROL && key.code == KeyCode::Char('r'))
}

fn enter_selected_terminal(app: &mut App) -> bool {
    if app.selected_is_current_rmux_session() {
        app.status =
            Some("This session is running AGK; recursive terminal mode is disabled".into());
        return false;
    }
    if !app.current_session().is_some_and(|runtime| runtime.live) {
        app.status = Some("This provider terminal is not live; press R to restart it".into());
        return false;
    }
    app.mode = Mode::Terminal;
    app.view = View::Sessions;
    app.focus = Focus::Detail;
    app.expanded = false;
    app.scroll_preview_live();
    true
}

fn register_tab(last_tab_at: &mut Option<Instant>, now: Instant) -> bool {
    let double =
        last_tab_at.is_some_and(|previous| now.duration_since(previous) <= DOUBLE_TAB_TIME);
    *last_tab_at = (!double).then_some(now);
    double
}

/// Returns true when the provider pane owns input after the transition.
fn session_tab(app: &mut App, detail_available: bool, double: bool) -> bool {
    if double && detail_available {
        app.expanded = true;
        app.focus = Focus::Detail;
        return true;
    }
    if app.expanded {
        app.expanded = false;
        app.focus = Focus::List;
        return false;
    }
    app.focus = if app.focus == Focus::List && detail_available {
        Focus::Detail
    } else {
        Focus::List
    };
    app.focus == Focus::Detail
}

fn terminal_sidebar_key(app: &mut App, key: &KeyEvent) -> bool {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            app.select_previous();
            true
        }
        KeyCode::Down | KeyCode::Char('j') => {
            app.select_next();
            true
        }
        KeyCode::Enter => {
            app.expanded = false;
            app.focus = Focus::Detail;
            true
        }
        _ => false,
    }
}

/// Left/right stays the global top-menu axis while the session sidebar owns
/// focus. Provider input keeps both arrows untouched when the live pane owns
/// focus, so shell and editor cursor movement remains native.
fn terminal_top_nav_key(app: &mut App, key: &KeyEvent) -> bool {
    match key.code {
        KeyCode::Left => app.previous_view(),
        KeyCode::Right => app.next_view(),
        _ => return false,
    }
    app.mode = Mode::Control;
    app.expanded = false;
    true
}

fn terminal_scroll_key(app: &mut App, key: &KeyEvent) -> bool {
    let modified_vertical = key
        .modifiers
        .intersects(KeyModifiers::ALT | KeyModifiers::SHIFT)
        && !key.modifiers.contains(KeyModifiers::CONTROL);
    match key.code {
        KeyCode::PageUp => app.scroll_preview_up(app.preview_height.max(8)),
        KeyCode::PageDown => app.scroll_preview_down(app.preview_height.max(8)),
        KeyCode::Home if key.modifiers.is_empty() => app.scroll_preview_home(),
        KeyCode::End if key.modifiers.is_empty() => app.scroll_preview_live(),
        KeyCode::Up if modified_vertical => app.scroll_preview_up(3),
        KeyCode::Down if modified_vertical => app.scroll_preview_down(3),
        _ => return false,
    }
    true
}

fn detail_available(app: &App) -> bool {
    match app.view {
        View::Sessions => app.current_session().is_some(),
        View::Projects => app.current_object().is_some(),
        View::Agents => app.current_agent().is_some(),
        View::Os => app.current_os().is_some(),
        View::Mcp => app.current_mcp().is_some(),
        View::Skills => app.current_skill().is_some(),
        View::Rules => app.current_rule().is_some(),
        View::Settings => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{RegistrySnapshot, RuntimeRecord};
    use rmux_sdk::{PaneCell, PaneGlyph};

    fn runtime(name: &str, live: bool) -> RuntimeRecord {
        RuntimeRecord {
            id: format!("runtime-{name}"),
            name: name.into(),
            kind: "hermes".into(),
            environment: "operator".into(),
            client: None,
            project: None,
            mission: None,
            native_session: None,
            hermes_profile: None,
            rmux_session: name.into(),
            cwd: "/home/operator".into(),
            status: if live { "running" } else { "interrupted" }.into(),
            created_at: 1.0,
            last_activity: 2.0,
            tokens: 0,
            model_usage: Vec::new(),
            managed: true,
            live,
        }
    }

    #[test]
    fn preview_refreshes_only_when_the_pane_is_rendered() {
        let mut app = App::new(Preferences::default());
        app.preview_width = 80;
        app.preview_height = 20;
        app.focus = Focus::List;
        app.preferences.split_preview = false;
        assert!(!preview_is_visible(&app));

        app.focus = Focus::Detail;
        assert!(preview_is_visible(&app));
        app.mode = Mode::Terminal;
        assert!(preview_is_visible(&app));
        app.view = View::Projects;
        assert!(!preview_is_visible(&app));
    }

    #[test]
    fn terminal_key_mapping_forwards_navigation_function_and_modifiers() {
        let cases = [
            (
                KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE),
                "BSpace",
            ),
            (KeyEvent::new(KeyCode::Insert, KeyModifiers::NONE), "IC"),
            (KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE), "Escape"),
            (KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE), "Tab"),
            (KeyEvent::new(KeyCode::BackTab, KeyModifiers::SHIFT), "BTab"),
            (KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE), "PageUp"),
            (KeyEvent::new(KeyCode::F(11), KeyModifiers::NONE), "F11"),
            (
                KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL),
                "C-c",
            ),
            (KeyEvent::new(KeyCode::Char('x'), KeyModifiers::ALT), "M-x"),
            (
                KeyEvent::new(
                    KeyCode::Char('x'),
                    KeyModifiers::CONTROL | KeyModifiers::ALT,
                ),
                "C-M-x",
            ),
            (KeyEvent::new(KeyCode::Up, KeyModifiers::SHIFT), "S-Up"),
            (
                KeyEvent::new(KeyCode::Backspace, KeyModifiers::CONTROL),
                "C-w",
            ),
            (KeyEvent::new(KeyCode::Left, KeyModifiers::ALT), "M-b"),
            (
                KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL),
                "C-r",
            ),
        ];
        for (key, expected) in cases {
            assert_eq!(rmux_key_token(key).as_deref(), Some(expected));
        }
    }

    #[test]
    fn terminal_escape_keys_do_not_capture_provider_control_r() {
        assert!(!terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Tab,
            KeyModifiers::NONE,
        )));
        assert!(terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Char('g'),
            KeyModifiers::CONTROL,
        )));
        assert!(!terminal_returns_to_control(&KeyEvent::new(
            KeyCode::Char('r'),
            KeyModifiers::CONTROL,
        )));
    }

    #[test]
    fn terminal_single_tab_only_alternates_panels_and_double_tab_expands() {
        let mut app = App::new(Preferences::default());
        app.mode = Mode::Terminal;
        app.focus = Focus::Detail;

        assert!(!session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::List);
        assert!(!app.expanded);

        assert!(session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::Detail);
        assert!(!app.expanded);

        assert!(session_tab(&mut app, true, true));
        assert_eq!(app.focus, Focus::Detail);
        assert!(app.expanded);

        assert!(!session_tab(&mut app, true, false));
        assert_eq!(app.focus, Focus::List);
        assert!(!app.expanded);
    }

    #[test]
    fn session_preview_focus_requests_immediate_provider_input() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("live", true)],
            ..RegistrySnapshot::default()
        });
        app.focus = Focus::List;

        assert!(session_tab(&mut app, true, false));
        assert!(enter_selected_terminal(&mut app));
        assert_eq!(app.focus, Focus::Detail);
        assert_eq!(app.mode, Mode::Terminal);
    }

    #[test]
    fn clicking_the_session_pane_activates_input_without_a_nav_focus_stop() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("live", true)],
            ..RegistrySnapshot::default()
        });
        let size = ratatui::layout::Size::new(90, 24);

        let pane = handle_mouse(
            &mut app,
            MouseEvent {
                kind: MouseEventKind::Down(MouseButton::Left),
                column: 50,
                row: 10,
                modifiers: KeyModifiers::NONE,
            },
            size,
        );
        assert_eq!(app.focus, Focus::Detail);
        assert!(pane.activate_session);

        app.focus = Focus::List;
        let nav = handle_mouse(
            &mut app,
            MouseEvent {
                kind: MouseEventKind::Down(MouseButton::Left),
                column: 2,
                row: 1,
                modifiers: KeyModifiers::NONE,
            },
            size,
        );
        assert_eq!(app.focus, Focus::List);
        assert!(!nav.activate_session);
    }

    #[test]
    fn only_two_rapid_consecutive_tabs_form_a_double_tab() {
        let started = Instant::now();
        let mut previous = None;
        assert!(!register_tab(&mut previous, started));
        assert!(register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME.saturating_sub(Duration::from_millis(1))
        ));
        assert!(previous.is_none());
        assert!(!register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME + Duration::from_millis(10)
        ));
        assert!(!register_tab(
            &mut previous,
            started + DOUBLE_TAB_TIME.saturating_mul(3)
        ));
    }

    #[test]
    fn terminal_sidebar_selects_a_session_then_returns_to_direct_input() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("one", true), runtime("two", true)],
            ..RegistrySnapshot::default()
        });
        app.focus = Focus::List;

        assert!(terminal_sidebar_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
        ));
        assert_eq!(app.selected_session_name(), Some("two"));
        assert!(terminal_sidebar_key(
            &mut app,
            &KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE)
        ));
        assert_eq!(app.focus, Focus::Detail);
        assert!(!app.expanded);
    }

    #[test]
    fn terminal_sidebar_routes_session_actions_out_of_provider_input() {
        for character in ['n', 'x', 'r', 'q'] {
            assert!(terminal_sidebar_control_key(&KeyEvent::new(
                KeyCode::Char(character),
                KeyModifiers::NONE,
            )));
        }
        assert!(terminal_sidebar_control_key(&KeyEvent::new(
            KeyCode::Char('r'),
            KeyModifiers::CONTROL,
        )));
        assert!(!terminal_sidebar_control_key(&KeyEvent::new(
            KeyCode::Char('a'),
            KeyModifiers::NONE,
        )));
    }

    #[test]
    fn terminal_sidebar_arrows_move_the_global_top_menu_without_a_middle_step() {
        let mut app = App::new(Preferences::default());
        app.mode = Mode::Terminal;
        app.view = View::Sessions;
        app.focus = Focus::List;

        assert!(terminal_top_nav_key(
            &mut app,
            &KeyEvent::new(KeyCode::Right, KeyModifiers::NONE)
        ));
        assert_eq!(app.mode, Mode::Control);
        assert_eq!(app.view, View::Projects);
        assert_eq!(app.focus, Focus::List);

        app.mode = Mode::Terminal;
        assert!(terminal_top_nav_key(
            &mut app,
            &KeyEvent::new(KeyCode::Left, KeyModifiers::NONE)
        ));
        assert_eq!(app.view, View::Sessions);
        assert_eq!(app.mode, Mode::Control);
    }

    #[test]
    fn terminal_history_keys_move_the_local_mirror_not_the_provider() {
        let mut app = App::new(Preferences::default());
        app.preview_height = 20;
        assert!(terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE)
        ));
        assert_eq!(app.preview_scroll, 20);
        assert!(terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::ALT)
        ));
        assert_eq!(app.preview_scroll, 17);
        assert!(!terminal_scroll_key(
            &mut app,
            &KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
        ));
    }

    #[test]
    fn pending_creation_waits_for_a_live_runtime_then_selects_it_for_direct_open() {
        let mut app = App::new(Preferences::default());
        let started_at = Instant::now();
        let pending = PendingSession {
            name: "fresh-hermes".into(),
            started_at,
            enter_terminal: true,
        };

        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at),
            PendingResolution::Waiting
        );
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("fresh-hermes", false)],
            ..RegistrySnapshot::default()
        });
        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + Duration::from_secs(1)),
            PendingResolution::Waiting
        );
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("fresh-hermes", true)],
            ..RegistrySnapshot::default()
        });
        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + Duration::from_secs(2)),
            PendingResolution::Ready {
                name: "fresh-hermes".into(),
                enter_terminal: true,
            }
        );
        assert_eq!(app.selected_session_name(), Some("fresh-hermes"));
    }

    #[test]
    fn pending_creation_reports_a_provider_that_exits_during_startup() {
        let mut app = App::new(Preferences::default());
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("dead-provider", false)],
            ..RegistrySnapshot::default()
        });
        let started_at = Instant::now();
        let pending = PendingSession {
            name: "dead-provider".into(),
            started_at,
            enter_terminal: true,
        };

        assert_eq!(
            resolve_pending_session(&mut app, &pending, started_at + SESSION_START_TIMEOUT),
            PendingResolution::TimedOut {
                name: "dead-provider".into(),
                registered: true,
            }
        );
    }

    #[test]
    fn media_and_lock_keys_are_ignored_safely() {
        assert_eq!(
            rmux_key_token(KeyEvent::new(KeyCode::CapsLock, KeyModifiers::NONE)),
            None
        );
    }

    #[test]
    fn current_session_resolution_uses_the_stable_rmux_pane_identity() {
        let mut queried = Vec::new();
        let resolved = resolve_current_rmux_session_with(
            |name| {
                queried.push(name.to_owned());
                match name {
                    "RMUX_PANE" => Some(" %42 ".into()),
                    "RMUX_SESSION" => Some("fallback".into()),
                    _ => None,
                }
            },
            |pane| {
                assert_eq!(pane, "%42");
                Some("operator-control\n".into())
            },
        );
        assert_eq!(resolved.as_deref(), Some("operator-control"));
        assert_eq!(queried, vec!["RMUX_PANE"]);
    }

    #[test]
    fn oversized_live_snapshot_keeps_the_tail_and_cursor() {
        let cells = ['a', 'b', 'c', 'd']
            .into_iter()
            .flat_map(|character| {
                [
                    PaneCell::new(PaneGlyph::new(character.to_string(), 1)),
                    PaneCell::blank(),
                ]
            })
            .collect();
        let snapshot = PaneSnapshot::new(2, 4, cells, PaneCursor::new(3, 1, true, 2))
            .unwrap()
            .with_revision(17);

        let cropped = crop_snapshot_to_height(snapshot, 2);

        assert_eq!((cropped.cols, cropped.rows), (2, 2));
        assert_eq!(cropped.cell(0, 0).map(PaneCell::text), Some("c"));
        assert_eq!(cropped.cell(1, 0).map(PaneCell::text), Some("d"));
        assert_eq!(cropped.cursor, PaneCursor::new(1, 1, true, 2));
        assert_eq!(cropped.revision, 17);
    }

    fn mouse(kind: MouseEventKind, column: u16, row: u16) -> MouseEvent {
        MouseEvent {
            kind,
            column,
            row,
            modifiers: KeyModifiers::NONE,
        }
    }

    fn selectable_app() -> App {
        let mut app = App::new(Preferences::default());
        let rect = ratatui::layout::Rect::new(10, 2, 12, 2);
        app.preview_rect = Some(rect);
        app.preview_grid = Some(selection::PreviewGrid {
            rect,
            rows: ["cargo test  ", "all green   "]
                .iter()
                .map(|line| line.chars().map(String::from).collect())
                .collect(),
        });
        app
    }

    #[test]
    fn a_session_opened_from_a_project_starts_inside_it() {
        let origin = SessionOrigin {
            project: "AGK-TUI".into(),
            cwd: "/home/a/projects/AGK-TUI".into(),
        };
        assert_eq!(
            create_session_arguments("claude", "fix-copy", Some(&origin)),
            [
                "new",
                "claude",
                "fix-copy",
                "--cwd",
                "/home/a/projects/AGK-TUI",
                "--project",
                "AGK-TUI"
            ]
        );
        assert_eq!(
            create_session_arguments("hermes", "anywhere", None),
            ["new", "hermes", "anywhere"]
        );

        // The name field starts with a free name derived from the project.
        let mut app = App::new(Preferences::default());
        assert_eq!(app.suggested_session_name(), "");
        app.session_origin = Some(origin);
        assert_eq!(app.suggested_session_name(), "agk-tui");
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("agk-tui", true), runtime("agk-tui-2", false)],
            ..RegistrySnapshot::default()
        });
        assert_eq!(app.suggested_session_name(), "agk-tui-3");
    }

    #[test]
    fn a_session_restarted_under_the_same_name_gets_a_fresh_pane_handle() {
        let mut cache = PreviewCache::default();
        cache.select("work");
        cache.target = Some("%1".into());
        cache.follow_session(Some(100.0));
        assert_eq!(cache.target.as_deref(), Some("%1"));
        // Unknown facts or an unchanged session keep the handle.
        cache.follow_session(None);
        cache.follow_session(Some(100.0));
        assert_eq!(cache.target.as_deref(), Some("%1"));
        cache.follow_session(Some(250.0));
        assert_eq!(cache.target, None);
        assert_eq!(cache.created, Some(250.0));
    }

    #[test]
    fn the_wheel_belongs_to_a_full_screen_program_and_to_history_otherwise() {
        let mut app = selectable_app();
        app.set_snapshot(RegistrySnapshot {
            runtimes: vec![runtime("tui", true)],
            ..RegistrySnapshot::default()
        });
        let up = mouse(MouseEventKind::ScrollUp, 12, 3);
        let down = mouse(MouseEventKind::ScrollDown, 12, 3);
        let facts = |alternate, mouse, mouse_sgr| data::PaneFacts {
            alternate,
            mouse,
            mouse_sgr,
            command: "node".into(),
            ..data::PaneFacts::default()
        };

        // An inline agent keeps RMUX scrollback: AGK scrolls its history.
        app.pane_facts
            .insert("tui".into(), facts(false, true, true));
        assert_eq!(program_wheel(&app, &up), None);
        assert!(!program_owns_screen(&app));

        // A pager on the alternate screen receives arrow keys.
        app.pane_facts
            .insert("tui".into(), facts(true, false, false));
        assert!(program_owns_screen(&app));
        assert_eq!(program_wheel(&app, &up), Some(WheelInput::Keys("Up")));
        assert_eq!(program_wheel(&app, &down), Some(WheelInput::Keys("Down")));

        // A mouse-aware TUI receives a real report at pane-relative cells.
        app.pane_facts.insert("tui".into(), facts(true, true, true));
        assert_eq!(
            program_wheel(&app, &up),
            Some(WheelInput::Report("\x1b[<64;3;2M".into()))
        );
        app.pane_facts
            .insert("tui".into(), facts(true, true, false));
        assert_eq!(
            program_wheel(&app, &down),
            Some(WheelInput::Report("\x1b[Ma#\"".into()))
        );

        // Outside the pane, on other gestures or under a dialog it is AGK's.
        assert_eq!(
            program_wheel(&app, &mouse(MouseEventKind::ScrollUp, 1, 1)),
            None
        );
        assert_eq!(
            program_wheel(&app, &mouse(MouseEventKind::Down(MouseButton::Left), 12, 3)),
            None
        );
        app.overlay = Overlay::ConfirmQuit;
        assert_eq!(program_wheel(&app, &up), None);
    }

    #[test]
    fn dragging_in_the_pane_selects_then_copies_on_release() {
        let mut app = selectable_app();
        let mut click = None;
        let now = Instant::now();
        let left = MouseButton::Left;

        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Down(left), 16, 2),
                &mut click,
                now
            ),
            SelectionOutcome::Started
        );
        assert!(app.selecting());
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Drag(left), 12, 3),
                &mut click,
                now
            ),
            SelectionOutcome::Consumed
        );
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Up(left), 12, 3),
                &mut click,
                now
            ),
            SelectionOutcome::Copy("test\nall".into())
        );
        assert!(!app.selecting());
    }

    #[test]
    fn a_plain_click_still_focuses_and_a_double_click_copies_the_word() {
        let mut app = selectable_app();
        let mut click = None;
        let now = Instant::now();
        let left = MouseButton::Left;

        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Down(left), 11, 2),
                &mut click,
                now
            ),
            SelectionOutcome::Started
        );
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Up(left), 11, 2),
                &mut click,
                now
            ),
            SelectionOutcome::Ignored
        );
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Down(left), 11, 2),
                &mut click,
                now + Duration::from_millis(150),
            ),
            SelectionOutcome::Copy("cargo".into())
        );

        // Outside the pane, or with a dialog open, the mouse is not a selection.
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Down(left), 1, 1),
                &mut click,
                now
            ),
            SelectionOutcome::Ignored
        );
        app.overlay = Overlay::ConfirmQuit;
        assert_eq!(
            select_with_mouse(
                &mut app,
                &mouse(MouseEventKind::Down(left), 11, 2),
                &mut click,
                now
            ),
            SelectionOutcome::Ignored
        );
    }

    #[test]
    fn kitty_protocol_control_space_and_malformed_snapshots_are_handled() {
        assert_eq!(
            rmux_key_token(KeyEvent::new(KeyCode::Char(' '), KeyModifiers::CONTROL)).as_deref(),
            Some("C-Space")
        );
        let mut snapshot = PaneSnapshot::new(
            2,
            2,
            vec![PaneCell::blank(); 4],
            PaneCursor::new(0, 0, true, 0),
        )
        .unwrap();
        snapshot.rows = 9;
        let cropped = crop_snapshot_to_height(snapshot, 2);
        assert_eq!(cropped.cells.len(), 4);
    }
}
