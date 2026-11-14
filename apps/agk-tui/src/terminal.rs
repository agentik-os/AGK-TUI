//! Host-terminal integration: color detection, clipboard, paste and title.
//!
//! AGK mirrors provider panes instead of attaching an RMUX client, so the
//! host terminal (Ghostty, iTerm, an SSH client…) never sees what a provider
//! copies and cannot select text inside the mirrored pane on its own. This
//! module owns every escape sequence that closes that gap.

use std::{
    io::{self, Read, Write},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

use crate::theme::{ColorDepth, RgbColor, TerminalProfile};

/// OSC 52 payloads above this size are rejected by several terminals.
const OSC52_MAX_BYTES: usize = 750_000;
const PROBE_TIMEOUT: Duration = Duration::from_millis(250);

/// Which path delivered a copy to the user's clipboard.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CopyRoute {
    /// A local clipboard program (`pbcopy`, `wl-copy`, `xclip`).
    Native,
    /// The OSC 52 escape, which also reaches the local machine over SSH.
    Osc52,
}

/// Detects color depth from the environment without touching the terminal.
pub fn detect_depth(env: impl Fn(&str) -> Option<String>) -> ColorDepth {
    let value = |name: &str| env(name).unwrap_or_default().to_ascii_lowercase();
    if env("NO_COLOR").is_some_and(|value| !value.is_empty()) {
        return ColorDepth::Ansi16;
    }
    let colorterm = value("COLORTERM");
    if colorterm.contains("truecolor") || colorterm.contains("24bit") {
        return ColorDepth::TrueColor;
    }
    let term = value("TERM");
    let program = value("TERM_PROGRAM");
    const TRUECOLOR_TERMS: [&str; 9] = [
        "ghostty",
        "kitty",
        "wezterm",
        "alacritty",
        "foot",
        "contour",
        "direct",
        "iterm",
        "rio",
    ];
    if TRUECOLOR_TERMS
        .iter()
        .any(|name| term.contains(name) || program.contains(name))
        || program.contains("vscode")
    {
        return ColorDepth::TrueColor;
    }
    if program == "apple_terminal" {
        // Terminal.app only gained 24-bit color recently and never sets
        // COLORTERM on older releases; 256 colors are correct on all of them.
        return ColorDepth::Ansi256;
    }
    if term.contains("256color") || term.starts_with("tmux") || term.starts_with("rmux") {
        // The usual SSH case: COLORTERM is not forwarded, but every modern
        // client advertising 256 colors also renders 24-bit sequences.
        return ColorDepth::TrueColor;
    }
    match term.as_str() {
        "" | "dumb" | "linux" | "vt100" | "vt220" | "ansi" => ColorDepth::Ansi16,
        _ => ColorDepth::Ansi256,
    }
}

/// Asks the terminal for its real default colors.
///
/// Must run in raw mode and before the event reader starts, so replies are
/// not echoed or mistaken for key presses. A trailing Device Attributes
/// request is answered by every terminal, which bounds the wait even when
/// the color queries are unsupported.
pub fn probe() -> TerminalProfile {
    let depth = detect_depth(|name| std::env::var(name).ok());
    let mut profile = TerminalProfile {
        depth,
        ..TerminalProfile::default()
    };
    if std::env::var_os("AGK_NO_TERMINAL_PROBE").is_some() {
        return profile;
    }
    if let Some(reply) = query_terminal("\x1b]11;?\x1b\\\x1b]10;?\x1b\\\x1b[c") {
        profile.background = parse_osc_color(&reply, 11);
        profile.foreground = parse_osc_color(&reply, 10);
    }
    profile
}

#[cfg(unix)]
fn query_terminal(query: &str) -> Option<String> {
    use std::os::fd::AsRawFd;

    let mut tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")
        .ok()?;
    tty.write_all(query.as_bytes()).ok()?;
    tty.flush().ok()?;

    let deadline = Instant::now() + PROBE_TIMEOUT;
    let mut reply = Vec::new();
    let mut buffer = [0u8; 256];
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            break;
        }
        let mut descriptor = libc::pollfd {
            fd: tty.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: `descriptor` is a valid, exclusively borrowed pollfd for
        // the duration of the call and the count matches.
        let ready = unsafe { libc::poll(&mut descriptor, 1, remaining.as_millis() as libc::c_int) };
        if ready <= 0 {
            break;
        }
        match tty.read(&mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(count) => reply.extend_from_slice(&buffer[..count]),
        }
        if device_attributes_received(&reply) || reply.len() > 4096 {
            break;
        }
    }
    (!reply.is_empty()).then(|| String::from_utf8_lossy(&reply).into_owned())
}

#[cfg(not(unix))]
fn query_terminal(_query: &str) -> Option<String> {
    None
}

/// The DA1 reply is `ESC [ ? … c`; its arrival means no more replies follow.
fn device_attributes_received(reply: &[u8]) -> bool {
    reply
        .windows(3)
        .rposition(|window| window == b"\x1b[?")
        .is_some_and(|start| reply[start..].contains(&b'c'))
}

/// Parses `ESC ] <code> ; rgb:RRRR/GGGG/BBBB` with 1–4 hex digits a channel.
fn parse_osc_color(reply: &str, code: u8) -> Option<RgbColor> {
    let marker = format!("\x1b]{code};");
    let body = &reply[reply.find(&marker)? + marker.len()..];
    let end = body.find(['\x07', '\x1b']).unwrap_or(body.len());
    let body = &body[..end];
    let channels = body
        .strip_prefix("rgb:")
        .or_else(|| body.strip_prefix("rgba:"))?;
    let mut values = channels.split('/').map(|channel| {
        let digits = channel.len();
        if digits == 0 || digits > 4 {
            return None;
        }
        let value = u32::from_str_radix(channel, 16).ok()?;
        let max = (1u32 << (4 * digits as u32)) - 1;
        Some(((value * 255 + max / 2) / max) as u8)
    });
    Some(RgbColor(values.next()??, values.next()??, values.next()??))
}

/// Copies text to the user's clipboard by every route that can reach it.
///
/// A local clipboard program is the most reliable route on the machine that
/// owns the screen. OSC 52 is always emitted as well because it is the only
/// route that crosses SSH back to the user's own computer.
pub fn copy(text: &str) -> io::Result<CopyRoute> {
    let remote = ["SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT"]
        .iter()
        .any(|name| std::env::var_os(name).is_some());
    let native = !remote && copy_native(text);
    let osc = copy_osc52(text);
    match (native, osc) {
        (true, _) => Ok(CopyRoute::Native),
        (false, Ok(())) => Ok(CopyRoute::Osc52),
        (false, Err(error)) => Err(error),
    }
}

fn copy_native(text: &str) -> bool {
    let candidates: &[(&str, &[&str])] = if cfg!(target_os = "macos") {
        &[("pbcopy", &[])]
    } else if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        &[("wl-copy", &[])]
    } else if std::env::var_os("DISPLAY").is_some() {
        &[
            ("xclip", &["-selection", "clipboard"]),
            ("xsel", &["--clipboard", "--input"]),
        ]
    } else {
        &[]
    };
    candidates.iter().any(|(program, arguments)| {
        let Ok(mut child) = Command::new(program)
            .args(*arguments)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        else {
            return false;
        };
        let written = child
            .stdin
            .take()
            .is_some_and(|mut stdin| stdin.write_all(text.as_bytes()).is_ok());
        child.wait().is_ok_and(|status| status.success()) && written
    })
}

fn copy_osc52(text: &str) -> io::Result<()> {
    if text.len() > OSC52_MAX_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "selection is too large for the terminal clipboard",
        ));
    }
    let mut stdout = io::stdout().lock();
    write!(stdout, "{}", osc52_sequence(text))?;
    stdout.flush()
}

fn osc52_sequence(text: &str) -> String {
    format!("\x1b]52;c;{}\x07", base64(text.as_bytes()))
}

fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut encoded = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let block = u32::from(chunk[0]) << 16
            | u32::from(*chunk.get(1).unwrap_or(&0)) << 8
            | u32::from(*chunk.get(2).unwrap_or(&0));
        encoded.push(ALPHABET[(block >> 18) as usize & 63] as char);
        encoded.push(ALPHABET[(block >> 12) as usize & 63] as char);
        encoded.push(if chunk.len() > 1 {
            ALPHABET[(block >> 6) as usize & 63] as char
        } else {
            '='
        });
        encoded.push(if chunk.len() > 2 {
            ALPHABET[block as usize & 63] as char
        } else {
            '='
        });
    }
    encoded
}

/// Pastes through RMUX's own paste path.
///
/// RMUX knows whether the program in the pane enabled bracketed paste, so a
/// plain shell receives the text itself while an agent CLI receives one
/// atomic bracketed paste. Returns false when the caller should fall back.
pub fn paste_into_pane(target: &str, text: &str) -> bool {
    if text.is_empty() {
        return false;
    }
    let buffer = format!("agk-paste-{}", std::process::id());
    let Ok(mut loader) = Command::new("rmux")
        .args(["load-buffer", "-b", &buffer, "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    else {
        return false;
    };
    let written = loader
        .stdin
        .take()
        .is_some_and(|mut stdin| stdin.write_all(text.as_bytes()).is_ok());
    if !loader.wait().is_ok_and(|status| status.success()) || !written {
        return false;
    }
    Command::new("rmux")
        .args(["paste-buffer", "-p", "-d", "-b", &buffer, "-t", target])
        .output()
        .is_ok_and(|output| output.status.success())
}

/// Identity of the newest RMUX paste buffer, used to notice provider copies.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct BufferStamp {
    pub name: String,
    pub created: String,
    pub size: String,
}

/// Returns the newest buffer that was not created by AGK's own paste path.
pub fn newest_buffer() -> Option<BufferStamp> {
    let output = Command::new("rmux")
        .args([
            "list-buffers",
            "-F",
            "#{buffer_name}\t#{buffer_created}\t#{buffer_size}",
        ])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    parse_newest_buffer(&String::from_utf8_lossy(&output.stdout))
}

fn parse_newest_buffer(listing: &str) -> Option<BufferStamp> {
    listing
        .lines()
        .filter_map(|line| {
            let mut fields = line.split('\t');
            let stamp = BufferStamp {
                name: fields.next()?.to_owned(),
                created: fields.next()?.to_owned(),
                size: fields.next()?.to_owned(),
            };
            (!stamp.name.is_empty() && !stamp.name.starts_with("agk-")).then_some(stamp)
        })
        .max_by_key(|stamp| stamp.created.parse::<u64>().unwrap_or(0))
}

pub fn buffer_text(name: &str) -> Option<String> {
    let output = Command::new("rmux")
        .args(["show-buffer", "-b", name])
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        .filter(|text| !text.is_empty())
}

/// Saves the terminal's own title so it can be restored on exit.
pub fn push_title() {
    emit("\x1b[22;0t");
}

pub fn pop_title() {
    emit("\x1b[23;0t");
}

/// Names the terminal tab/window after the work it is showing.
pub fn set_title(title: &str) {
    let clean = title
        .chars()
        .filter(|character| !character.is_control())
        .take(120)
        .collect::<String>();
    emit(&format!("\x1b]2;{clean}\x07"));
}

fn emit(sequence: &str) {
    let mut stdout = io::stdout().lock();
    let _ = stdout.write_all(sequence.as_bytes());
    let _ = stdout.flush();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn depth(pairs: &[(&str, &str)]) -> ColorDepth {
        detect_depth(|name| {
            pairs
                .iter()
                .find(|(key, _)| *key == name)
                .map(|(_, value)| (*value).to_owned())
        })
    }

    #[test]
    fn color_depth_follows_the_terminal_instead_of_assuming_truecolor() {
        assert_eq!(
            depth(&[("COLORTERM", "truecolor"), ("TERM", "xterm")]),
            ColorDepth::TrueColor
        );
        assert_eq!(depth(&[("TERM", "xterm-ghostty")]), ColorDepth::TrueColor);
        assert_eq!(
            depth(&[
                ("TERM", "xterm-256color"),
                ("TERM_PROGRAM", "Apple_Terminal")
            ]),
            ColorDepth::Ansi256
        );
        assert_eq!(depth(&[("TERM", "xterm-256color")]), ColorDepth::TrueColor);
        assert_eq!(depth(&[("TERM", "xterm")]), ColorDepth::Ansi256);
        assert_eq!(depth(&[("TERM", "linux")]), ColorDepth::Ansi16);
        assert_eq!(
            depth(&[("COLORTERM", "truecolor"), ("NO_COLOR", "1")]),
            ColorDepth::Ansi16
        );
    }

    #[test]
    fn terminal_color_replies_are_parsed_at_every_channel_width() {
        let reply = "\x1b]11;rgb:1e1e/2e2e/3e3e\x1b\\\x1b]10;rgb:ff/80/00\x07\x1b[?62;22c";
        assert_eq!(parse_osc_color(reply, 11), Some(RgbColor(0x1e, 0x2e, 0x3e)));
        assert_eq!(parse_osc_color(reply, 10), Some(RgbColor(0xff, 0x80, 0x00)));
        assert_eq!(
            parse_osc_color("\x1b]11;rgb:f/0/8\x07", 11),
            Some(RgbColor(255, 0, 136))
        );
        assert_eq!(parse_osc_color("\x1b[?62c", 11), None);
        assert_eq!(parse_osc_color("\x1b]11;rgb:zz/00/00\x07", 11), None);
        assert!(device_attributes_received(reply.as_bytes()));
        assert!(!device_attributes_received(b"\x1b]11;rgb:00/00/00\x07"));
    }

    #[test]
    fn clipboard_escape_is_standard_base64_for_any_utf8_text() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foobar"), "Zm9vYmFy");
        assert_eq!(osc52_sequence("é"), "\x1b]52;c;w6k=\x07");
    }

    #[test]
    fn provider_copy_detection_ignores_agk_paste_buffers() {
        let listing = "agk-paste-9\t300\t4\nbuffer1\t200\t12\nbuffer0\t100\t3\n";
        assert_eq!(
            parse_newest_buffer(listing),
            Some(BufferStamp {
                name: "buffer1".into(),
                created: "200".into(),
                size: "12".into(),
            })
        );
        assert_eq!(parse_newest_buffer("agk-paste-1\t5\t1\n"), None);
        assert_eq!(parse_newest_buffer(""), None);
    }
}
