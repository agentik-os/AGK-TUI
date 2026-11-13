//! AGK-owned visual themes and durable TUI preferences.
//!
//! The file format is intentionally small and forwards-compatible: one
//! `key=value` pair per line, with unknown keys and malformed values ignored.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use ratatui::style::Color;

/// Semantic colors used by AGK widgets.
///
/// Keeping widgets on semantic roles instead of theme-specific colors makes a
/// theme change take effect immediately and keeps status colors consistent
/// across every view.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Palette {
    pub background: Color,
    pub surface: Color,
    pub surface_alt: Color,
    pub text: Color,
    pub text_muted: Color,
    pub accent: Color,
    pub accent_alt: Color,
    pub selection_bg: Color,
    pub selection_text: Color,
    pub border: Color,
    pub border_focused: Color,
    pub success: Color,
    pub warning: Color,
    pub error: Color,
    pub info: Color,
}

/// Serializable RGB value used by the in-app custom theme editor.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RgbColor(pub u8, pub u8, pub u8);

impl RgbColor {
    pub const fn color(self) -> Color {
        Color::Rgb(self.0, self.1, self.2)
    }

    pub fn from_hex(value: &str) -> Option<Self> {
        let hex = value.trim().strip_prefix('#').unwrap_or(value.trim());
        if hex.len() != 6 || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return None;
        }
        Some(Self(
            u8::from_str_radix(&hex[0..2], 16).ok()?,
            u8::from_str_radix(&hex[2..4], 16).ok()?,
            u8::from_str_radix(&hex[4..6], 16).ok()?,
        ))
    }

    pub fn hex(self) -> String {
        format!("#{:02X}{:02X}{:02X}", self.0, self.1, self.2)
    }
}

/// Ten editable anchors are expanded into the complete semantic palette, so
/// custom themes remain easy to tune without losing readable selections and
/// focused borders.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CustomColors {
    pub background: RgbColor,
    pub surface: RgbColor,
    pub text: RgbColor,
    pub muted: RgbColor,
    pub accent: RgbColor,
    pub border: RgbColor,
    pub success: RgbColor,
    pub warning: RgbColor,
    pub error: RgbColor,
    pub info: RgbColor,
}

impl Default for CustomColors {
    fn default() -> Self {
        Self {
            background: RgbColor(12, 14, 18),
            surface: RgbColor(23, 27, 34),
            text: RgbColor(239, 242, 247),
            muted: RgbColor(145, 154, 170),
            accent: RgbColor(139, 124, 246),
            border: RgbColor(70, 78, 94),
            success: RgbColor(68, 190, 133),
            warning: RgbColor(226, 175, 88),
            error: RgbColor(231, 96, 112),
            info: RgbColor(91, 169, 244),
        }
    }
}

impl CustomColors {
    pub const LEN: usize = 10;

    pub const fn label(index: usize) -> &'static str {
        match index {
            0 => "Background",
            1 => "Surface",
            2 => "Text",
            3 => "Muted text",
            4 => "Accent",
            5 => "Border",
            6 => "Success",
            7 => "Warning",
            8 => "Error",
            9 => "Info",
            _ => "Color",
        }
    }

    pub const fn config_key(index: usize) -> &'static str {
        match index {
            0 => "custom_background",
            1 => "custom_surface",
            2 => "custom_text",
            3 => "custom_muted",
            4 => "custom_accent",
            5 => "custom_border",
            6 => "custom_success",
            7 => "custom_warning",
            8 => "custom_error",
            9 => "custom_info",
            _ => "custom_color",
        }
    }

    pub const fn get(self, index: usize) -> RgbColor {
        match index {
            0 => self.background,
            1 => self.surface,
            2 => self.text,
            3 => self.muted,
            4 => self.accent,
            5 => self.border,
            6 => self.success,
            7 => self.warning,
            8 => self.error,
            9 => self.info,
            _ => self.accent,
        }
    }

    pub fn set(&mut self, index: usize, value: RgbColor) {
        match index {
            0 => self.background = value,
            1 => self.surface = value,
            2 => self.text = value,
            3 => self.muted = value,
            4 => self.accent = value,
            5 => self.border = value,
            6 => self.success = value,
            7 => self.warning = value,
            8 => self.error = value,
            9 => self.info = value,
            _ => {}
        }
    }

    pub fn palette(self) -> Palette {
        let selection_bg = blend(self.background, self.accent, 38);
        Palette {
            background: self.background.color(),
            surface: self.surface.color(),
            surface_alt: blend(self.surface, self.text, 12).color(),
            text: self.text.color(),
            text_muted: self.muted.color(),
            accent: self.accent.color(),
            accent_alt: blend(self.accent, self.text, 24).color(),
            selection_bg: selection_bg.color(),
            selection_text: contrast_text(selection_bg).color(),
            border: self.border.color(),
            border_focused: self.accent.color(),
            success: self.success.color(),
            warning: self.warning.color(),
            error: self.error.color(),
            info: self.info.color(),
        }
    }
}

fn blend(left: RgbColor, right: RgbColor, right_percent: u16) -> RgbColor {
    let left_percent = 100u16.saturating_sub(right_percent);
    let channel = |left: u8, right: u8| {
        ((u16::from(left) * left_percent + u16::from(right) * right_percent) / 100) as u8
    };
    RgbColor(
        channel(left.0, right.0),
        channel(left.1, right.1),
        channel(left.2, right.2),
    )
}

fn contrast_text(color: RgbColor) -> RgbColor {
    let luminance = u32::from(color.0) * 299 + u32::from(color.1) * 587 + u32::from(color.2) * 114;
    if luminance >= 150_000 {
        RgbColor(12, 14, 18)
    } else {
        RgbColor(250, 250, 250)
    }
}

/// Built-in AGK themes. Variant order is the stable order shown in Settings.
#[derive(Clone, Copy, Debug, Default, Eq, Hash, PartialEq)]
pub enum Theme {
    /// Follows the real colors reported by the host terminal.
    #[default]
    Auto,
    ClassicDark,
    ClassicLight,
    HermesDark,
    HermesLight,
    ClaudeDark,
    ClaudeLight,
    CodexDark,
    CodexLight,
    PureBlack,
    PureWhite,
    Midnight,
    Graphite,
    TerminalAmber,
    TerminalGreen,
    Custom,
}

impl Theme {
    pub const ALL: [Self; 16] = [
        Self::Auto,
        Self::ClassicDark,
        Self::ClassicLight,
        Self::HermesDark,
        Self::HermesLight,
        Self::ClaudeDark,
        Self::ClaudeLight,
        Self::CodexDark,
        Self::CodexLight,
        Self::PureBlack,
        Self::PureWhite,
        Self::Midnight,
        Self::Graphite,
        Self::TerminalAmber,
        Self::TerminalGreen,
        Self::Custom,
    ];

    /// Stable identifier used in `tui.conf`.
    pub const fn slug(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::ClassicDark => "classic-dark",
            Self::ClassicLight => "classic-light",
            Self::HermesDark => "hermes-dark",
            Self::HermesLight => "hermes-light",
            Self::ClaudeDark => "claude-dark",
            Self::ClaudeLight => "claude-light",
            Self::CodexDark => "codex-dark",
            Self::CodexLight => "codex-light",
            Self::PureBlack => "pure-black",
            Self::PureWhite => "pure-white",
            Self::Midnight => "midnight",
            Self::Graphite => "graphite",
            Self::TerminalAmber => "terminal-amber",
            Self::TerminalGreen => "terminal-green",
            Self::Custom => "custom",
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Self::Auto => "Auto",
            Self::ClassicDark => "Classic Dark",
            Self::ClassicLight => "Classic Light",
            Self::HermesDark => "Hermes Dark",
            Self::HermesLight => "Hermes Light",
            Self::ClaudeDark => "Claude Dark",
            Self::ClaudeLight => "Claude Light",
            Self::CodexDark => "Codex Dark",
            Self::CodexLight => "Codex Light",
            Self::PureBlack => "Pure Black",
            Self::PureWhite => "Pure White",
            Self::Midnight => "Midnight",
            Self::Graphite => "Graphite",
            Self::TerminalAmber => "Terminal Amber",
            Self::TerminalGreen => "Terminal Green",
            Self::Custom => "Custom",
        }
    }

    pub const fn description(self) -> &'static str {
        match self {
            Self::Auto => "Follows your terminal: its real background, text and light/dark mode.",
            Self::ClassicDark => "Neutral graphite, crisp white type and a restrained blue accent.",
            Self::ClassicLight => "Clean paper white, charcoal type and quiet professional blue.",
            Self::HermesDark => "Official Hermes gold and bronze on deep navy-black.",
            Self::HermesLight => "Hermes amber inks tuned for a clean light terminal.",
            Self::ClaudeDark => "Claude terracotta with warm, editorial dark neutrals.",
            Self::ClaudeLight => "Claude terracotta on a calm parchment workspace.",
            Self::CodexDark => "Codex green and cyan on a precise graphite shell.",
            Self::CodexLight => "Codex green with crisp, low-noise daylight contrast.",
            Self::PureBlack => "True-black high contrast for OLED screens and dark terminals.",
            Self::PureWhite => "Full white daylight canvas with sharp black typography.",
            Self::Midnight => "Deep blue control room with cool electric highlights.",
            Self::Graphite => "Low-noise monochrome charcoal for long focused sessions.",
            Self::TerminalAmber => "Classic amber phosphor, rebuilt with modern contrast.",
            Self::TerminalGreen => "Classic green phosphor with restrained status colors.",
            Self::Custom => "Your own live-editable RGB palette, persisted per user.",
        }
    }

    pub fn next(self) -> Self {
        let index = Self::ALL
            .iter()
            .position(|theme| *theme == self)
            .unwrap_or(0);
        Self::ALL[(index + 1) % Self::ALL.len()]
    }

    pub fn previous(self) -> Self {
        let index = Self::ALL
            .iter()
            .position(|theme| *theme == self)
            .unwrap_or(0);
        Self::ALL[(index + Self::ALL.len() - 1) % Self::ALL.len()]
    }

    pub fn from_slug(slug: &str) -> Option<Self> {
        let slug = slug.trim();
        // Preserve preferences written by the pre-provider AGK themes.
        match slug.to_ascii_lowercase().as_str() {
            "terminal" | "system" | "default" => return Some(Self::Auto),
            "gold" | "ares" => return Some(Self::HermesDark),
            "ocean" | "nord" => return Some(Self::CodexDark),
            "mono" | "matrix" => return Some(Self::CodexLight),
            _ => {}
        }
        Self::ALL
            .into_iter()
            .find(|theme| theme.slug().eq_ignore_ascii_case(slug))
    }

    /// Representative colors for the Settings theme picker.
    #[cfg(test)]
    pub fn swatches(self) -> [Color; 5] {
        let palette = self.palette();
        [
            palette.background,
            palette.surface_alt,
            palette.accent,
            palette.info,
            palette.text,
        ]
    }

    pub const fn paints_background(self) -> bool {
        matches!(self, Self::PureBlack | Self::PureWhite | Self::Custom)
    }

    pub fn palette_with_custom(self, custom: CustomColors) -> Palette {
        if self == Self::Custom {
            custom.palette()
        } else {
            self.palette()
        }
    }

    pub fn palette(self) -> Palette {
        match self {
            Self::Auto => ansi_native_palette(),
            Self::ClassicDark => Palette {
                background: Color::Rgb(15, 17, 21),
                surface: Color::Rgb(22, 25, 30),
                surface_alt: Color::Rgb(31, 36, 43),
                text: Color::Rgb(235, 238, 243),
                text_muted: Color::Rgb(145, 153, 166),
                accent: Color::Rgb(104, 166, 255),
                accent_alt: Color::Rgb(126, 199, 255),
                selection_bg: Color::Rgb(45, 66, 94),
                selection_text: Color::Rgb(248, 250, 252),
                border: Color::Rgb(62, 70, 82),
                border_focused: Color::Rgb(104, 166, 255),
                success: Color::Rgb(92, 190, 128),
                warning: Color::Rgb(224, 173, 82),
                error: Color::Rgb(224, 99, 105),
                info: Color::Rgb(104, 166, 255),
            },
            Self::ClassicLight => Palette {
                background: Color::Rgb(250, 250, 249),
                surface: Color::Rgb(246, 247, 248),
                surface_alt: Color::Rgb(233, 236, 240),
                text: Color::Rgb(34, 38, 44),
                text_muted: Color::Rgb(100, 108, 120),
                accent: Color::Rgb(37, 99, 180),
                accent_alt: Color::Rgb(28, 119, 166),
                selection_bg: Color::Rgb(214, 227, 244),
                selection_text: Color::Rgb(22, 45, 75),
                border: Color::Rgb(185, 192, 202),
                border_focused: Color::Rgb(37, 99, 180),
                success: Color::Rgb(45, 130, 82),
                warning: Color::Rgb(153, 103, 29),
                error: Color::Rgb(180, 58, 66),
                info: Color::Rgb(37, 99, 180),
            },
            Self::HermesDark => Palette {
                background: Color::Rgb(16, 16, 20),
                surface: Color::Rgb(26, 26, 46),
                surface_alt: Color::Rgb(51, 51, 85),
                text: Color::Rgb(255, 248, 220),
                text_muted: Color::Rgb(204, 155, 31),
                accent: Color::Rgb(255, 191, 0),
                accent_alt: Color::Rgb(255, 215, 0),
                selection_bg: Color::Rgb(58, 58, 85),
                selection_text: Color::Rgb(255, 248, 220),
                border: Color::Rgb(205, 127, 50),
                border_focused: Color::Rgb(255, 215, 0),
                success: Color::Rgb(143, 188, 143),
                warning: Color::Rgb(255, 167, 38),
                error: Color::Rgb(239, 83, 80),
                info: Color::Rgb(77, 171, 247),
            },
            Self::HermesLight => Palette {
                background: Color::Rgb(255, 255, 255),
                surface: Color::Rgb(250, 248, 242),
                surface_alt: Color::Rgb(240, 232, 216),
                text: Color::Rgb(61, 47, 19),
                text_muted: Color::Rgb(128, 99, 30),
                accent: Color::Rgb(149, 110, 0),
                accent_alt: Color::Rgb(134, 112, 0),
                selection_bg: Color::Rgb(224, 209, 191),
                selection_text: Color::Rgb(43, 32, 20),
                border: Color::Rgb(165, 102, 40),
                border_focused: Color::Rgb(134, 112, 0),
                success: Color::Rgb(54, 126, 57),
                warning: Color::Rgb(149, 97, 21),
                error: Color::Rgb(193, 66, 64),
                info: Color::Rgb(55, 123, 179),
            },
            Self::ClaudeDark => Palette {
                background: Color::Rgb(24, 22, 20),
                surface: Color::Rgb(34, 31, 28),
                surface_alt: Color::Rgb(50, 44, 39),
                text: Color::Rgb(242, 237, 229),
                text_muted: Color::Rgb(170, 157, 143),
                accent: Color::Rgb(217, 119, 87),
                accent_alt: Color::Rgb(238, 155, 121),
                selection_bg: Color::Rgb(91, 53, 41),
                selection_text: Color::Rgb(255, 243, 235),
                border: Color::Rgb(111, 81, 68),
                border_focused: Color::Rgb(217, 119, 87),
                success: Color::Rgb(117, 173, 121),
                warning: Color::Rgb(224, 167, 88),
                error: Color::Rgb(222, 94, 91),
                info: Color::Rgb(117, 155, 194),
            },
            Self::ClaudeLight => Palette {
                background: Color::Rgb(250, 249, 246),
                surface: Color::Rgb(246, 242, 236),
                surface_alt: Color::Rgb(234, 226, 215),
                text: Color::Rgb(45, 40, 35),
                text_muted: Color::Rgb(112, 98, 86),
                accent: Color::Rgb(181, 83, 55),
                accent_alt: Color::Rgb(142, 65, 46),
                selection_bg: Color::Rgb(241, 213, 198),
                selection_text: Color::Rgb(56, 34, 27),
                border: Color::Rgb(190, 148, 128),
                border_focused: Color::Rgb(181, 83, 55),
                success: Color::Rgb(65, 125, 70),
                warning: Color::Rgb(151, 99, 30),
                error: Color::Rgb(178, 55, 55),
                info: Color::Rgb(58, 105, 151),
            },
            Self::CodexDark => Palette {
                background: Color::Rgb(13, 17, 18),
                surface: Color::Rgb(20, 27, 28),
                surface_alt: Color::Rgb(30, 42, 42),
                text: Color::Rgb(229, 239, 236),
                text_muted: Color::Rgb(133, 157, 150),
                accent: Color::Rgb(16, 163, 127),
                accent_alt: Color::Rgb(61, 214, 174),
                selection_bg: Color::Rgb(20, 82, 68),
                selection_text: Color::Rgb(229, 255, 247),
                border: Color::Rgb(53, 104, 92),
                border_focused: Color::Rgb(61, 214, 174),
                success: Color::Rgb(70, 190, 143),
                warning: Color::Rgb(221, 171, 83),
                error: Color::Rgb(231, 103, 103),
                info: Color::Rgb(84, 166, 222),
            },
            Self::CodexLight => Palette {
                background: Color::Rgb(248, 250, 249),
                surface: Color::Rgb(240, 246, 243),
                surface_alt: Color::Rgb(222, 237, 231),
                text: Color::Rgb(26, 42, 37),
                text_muted: Color::Rgb(78, 109, 99),
                accent: Color::Rgb(0, 122, 92),
                accent_alt: Color::Rgb(0, 94, 73),
                selection_bg: Color::Rgb(195, 230, 217),
                selection_text: Color::Rgb(14, 54, 43),
                border: Color::Rgb(104, 151, 137),
                border_focused: Color::Rgb(0, 122, 92),
                success: Color::Rgb(43, 132, 85),
                warning: Color::Rgb(151, 102, 25),
                error: Color::Rgb(183, 58, 58),
                info: Color::Rgb(43, 104, 163),
            },
            Self::PureBlack => Palette {
                background: Color::Rgb(0, 0, 0),
                surface: Color::Rgb(5, 5, 5),
                surface_alt: Color::Rgb(15, 15, 15),
                text: Color::Rgb(255, 255, 255),
                text_muted: Color::Rgb(166, 166, 166),
                accent: Color::Rgb(255, 255, 255),
                accent_alt: Color::Rgb(210, 210, 210),
                selection_bg: Color::Rgb(45, 45, 45),
                selection_text: Color::Rgb(255, 255, 255),
                border: Color::Rgb(78, 78, 78),
                border_focused: Color::Rgb(255, 255, 255),
                success: Color::Rgb(112, 214, 151),
                warning: Color::Rgb(242, 194, 105),
                error: Color::Rgb(244, 112, 124),
                info: Color::Rgb(126, 184, 255),
            },
            Self::PureWhite => Palette {
                background: Color::Rgb(255, 255, 255),
                surface: Color::Rgb(250, 250, 250),
                surface_alt: Color::Rgb(238, 238, 238),
                text: Color::Rgb(0, 0, 0),
                text_muted: Color::Rgb(88, 88, 88),
                accent: Color::Rgb(0, 0, 0),
                accent_alt: Color::Rgb(55, 55, 55),
                selection_bg: Color::Rgb(218, 218, 218),
                selection_text: Color::Rgb(0, 0, 0),
                border: Color::Rgb(170, 170, 170),
                border_focused: Color::Rgb(0, 0, 0),
                success: Color::Rgb(17, 112, 61),
                warning: Color::Rgb(137, 86, 0),
                error: Color::Rgb(170, 36, 47),
                info: Color::Rgb(17, 75, 145),
            },
            Self::Midnight => Palette {
                background: Color::Rgb(5, 10, 24),
                surface: Color::Rgb(10, 19, 39),
                surface_alt: Color::Rgb(18, 32, 59),
                text: Color::Rgb(229, 238, 255),
                text_muted: Color::Rgb(127, 148, 184),
                accent: Color::Rgb(102, 153, 255),
                accent_alt: Color::Rgb(93, 214, 255),
                selection_bg: Color::Rgb(29, 61, 112),
                selection_text: Color::Rgb(244, 248, 255),
                border: Color::Rgb(48, 76, 122),
                border_focused: Color::Rgb(102, 153, 255),
                success: Color::Rgb(78, 201, 151),
                warning: Color::Rgb(235, 184, 92),
                error: Color::Rgb(241, 106, 126),
                info: Color::Rgb(93, 214, 255),
            },
            Self::Graphite => Palette {
                background: Color::Rgb(18, 18, 19),
                surface: Color::Rgb(27, 28, 30),
                surface_alt: Color::Rgb(39, 40, 43),
                text: Color::Rgb(232, 232, 230),
                text_muted: Color::Rgb(151, 151, 146),
                accent: Color::Rgb(202, 202, 196),
                accent_alt: Color::Rgb(245, 245, 239),
                selection_bg: Color::Rgb(66, 67, 69),
                selection_text: Color::Rgb(255, 255, 251),
                border: Color::Rgb(78, 79, 82),
                border_focused: Color::Rgb(202, 202, 196),
                success: Color::Rgb(119, 182, 133),
                warning: Color::Rgb(211, 170, 96),
                error: Color::Rgb(215, 105, 109),
                info: Color::Rgb(127, 166, 204),
            },
            Self::TerminalAmber => Palette {
                background: Color::Rgb(18, 11, 2),
                surface: Color::Rgb(29, 19, 5),
                surface_alt: Color::Rgb(48, 31, 7),
                text: Color::Rgb(255, 220, 145),
                text_muted: Color::Rgb(184, 132, 55),
                accent: Color::Rgb(255, 176, 46),
                accent_alt: Color::Rgb(255, 213, 119),
                selection_bg: Color::Rgb(91, 55, 8),
                selection_text: Color::Rgb(255, 238, 198),
                border: Color::Rgb(128, 78, 15),
                border_focused: Color::Rgb(255, 176, 46),
                success: Color::Rgb(154, 199, 103),
                warning: Color::Rgb(255, 176, 46),
                error: Color::Rgb(236, 94, 74),
                info: Color::Rgb(106, 171, 210),
            },
            Self::TerminalGreen => Palette {
                background: Color::Rgb(2, 15, 8),
                surface: Color::Rgb(6, 27, 14),
                surface_alt: Color::Rgb(10, 46, 23),
                text: Color::Rgb(191, 255, 208),
                text_muted: Color::Rgb(92, 176, 116),
                accent: Color::Rgb(73, 255, 125),
                accent_alt: Color::Rgb(157, 255, 185),
                selection_bg: Color::Rgb(18, 89, 42),
                selection_text: Color::Rgb(225, 255, 233),
                border: Color::Rgb(31, 122, 59),
                border_focused: Color::Rgb(73, 255, 125),
                success: Color::Rgb(73, 255, 125),
                warning: Color::Rgb(231, 190, 83),
                error: Color::Rgb(235, 93, 103),
                info: Color::Rgb(87, 190, 225),
            },
            Self::Custom => CustomColors::default().palette(),
        }
    }
}

/// How many colors the host terminal can really display.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ColorDepth {
    #[default]
    TrueColor,
    Ansi256,
    Ansi16,
}

/// User override for color-depth detection, persisted as `colors=` in
/// `tui.conf`.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ColorMode {
    #[default]
    Auto,
    TrueColor,
    Ansi256,
    Ansi16,
}

impl ColorMode {
    pub const ALL: [Self; 4] = [Self::Auto, Self::TrueColor, Self::Ansi256, Self::Ansi16];

    pub const fn slug(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::TrueColor => "truecolor",
            Self::Ansi256 => "256",
            Self::Ansi16 => "16",
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Self::Auto => "Auto-detect",
            Self::TrueColor => "24-bit truecolor",
            Self::Ansi256 => "256 colors",
            Self::Ansi16 => "16 ANSI colors",
        }
    }

    pub fn from_slug(slug: &str) -> Option<Self> {
        match slug.trim().to_ascii_lowercase().as_str() {
            "auto" => Some(Self::Auto),
            "truecolor" | "24bit" | "rgb" => Some(Self::TrueColor),
            "256" | "ansi256" => Some(Self::Ansi256),
            "16" | "ansi" | "ansi16" => Some(Self::Ansi16),
            _ => None,
        }
    }

    pub fn next(self) -> Self {
        let index = Self::ALL.iter().position(|mode| *mode == self).unwrap_or(0);
        Self::ALL[(index + 1) % Self::ALL.len()]
    }

    pub const fn depth(self, detected: ColorDepth) -> ColorDepth {
        match self {
            Self::Auto => detected,
            Self::TrueColor => ColorDepth::TrueColor,
            Self::Ansi256 => ColorDepth::Ansi256,
            Self::Ansi16 => ColorDepth::Ansi16,
        }
    }
}

/// Facts about the host terminal gathered once at startup.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct TerminalProfile {
    /// Real default background, when the terminal answered OSC 11.
    pub background: Option<RgbColor>,
    /// Real default foreground, when the terminal answered OSC 10.
    pub foreground: Option<RgbColor>,
    pub depth: ColorDepth,
}

/// A palette that is ready to draw on one specific terminal.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ResolvedPalette {
    pub palette: Palette,
    /// True when AGK fills the canvas instead of inheriting the terminal's.
    pub paints_background: bool,
    /// True when a light/dark mismatch forced the canvas to be painted.
    pub adapted: bool,
}

const DARK_INK: RgbColor = RgbColor(12, 14, 18);
const LIGHT_INK: RgbColor = RgbColor(250, 250, 250);

impl RgbColor {
    pub const fn from_color(color: Color) -> Option<Self> {
        match color {
            Color::Rgb(red, green, blue) => Some(Self(red, green, blue)),
            _ => None,
        }
    }

    /// WCAG relative luminance in `0.0..=1.0`.
    pub fn luminance(self) -> f32 {
        let channel = |value: u8| {
            let value = f32::from(value) / 255.0;
            if value <= 0.039_28 {
                value / 12.92
            } else {
                ((value + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * channel(self.0) + 0.7152 * channel(self.1) + 0.0722 * channel(self.2)
    }

    pub fn is_light(self) -> bool {
        self.luminance() > 0.35
    }

    /// WCAG contrast ratio in `1.0..=21.0`.
    pub fn contrast(self, other: Self) -> f32 {
        let (left, right) = (self.luminance(), other.luminance());
        (left.max(right) + 0.05) / (left.min(right) + 0.05)
    }

    /// Moves this color away from `background` until it is readable, keeping
    /// as much of its hue as the requested ratio allows.
    pub fn readable_on(self, background: Self, ratio: f32) -> Self {
        if self.contrast(background) >= ratio {
            return self;
        }
        let ink = if background.is_light() {
            RgbColor(0, 0, 0)
        } else {
            RgbColor(255, 255, 255)
        };
        for percent in (10..=100).step_by(10) {
            let candidate = blend(self, ink, percent);
            if candidate.contrast(background) >= ratio {
                return candidate;
            }
        }
        ink
    }
}

impl CustomColors {
    /// Seeds the custom editor from any RGB palette so "customize this
    /// theme" starts from what is on screen instead of a fixed default.
    pub fn from_palette(palette: Palette) -> Option<Self> {
        Some(Self {
            background: RgbColor::from_color(palette.background)?,
            surface: RgbColor::from_color(palette.surface)?,
            text: RgbColor::from_color(palette.text)?,
            muted: RgbColor::from_color(palette.text_muted)?,
            accent: RgbColor::from_color(palette.accent)?,
            border: RgbColor::from_color(palette.border)?,
            success: RgbColor::from_color(palette.success)?,
            warning: RgbColor::from_color(palette.warning)?,
            error: RgbColor::from_color(palette.error)?,
            info: RgbColor::from_color(palette.info)?,
        })
    }

    /// Derives a complete palette from the terminal's own background and
    /// foreground, so AGK looks native in any terminal theme.
    pub fn from_terminal(background: RgbColor, foreground: Option<RgbColor>) -> Self {
        let light = background.is_light();
        let text = foreground
            .filter(|foreground| foreground.contrast(background) >= 4.5)
            .unwrap_or(if light { DARK_INK } else { LIGHT_INK });
        let (accent, success, warning, error, info) = if light {
            (
                RgbColor(91, 70, 214),
                RgbColor(30, 125, 75),
                RgbColor(150, 98, 20),
                RgbColor(185, 50, 60),
                RgbColor(35, 100, 175),
            )
        } else {
            (
                RgbColor(139, 124, 246),
                RgbColor(68, 190, 133),
                RgbColor(226, 175, 88),
                RgbColor(231, 96, 112),
                RgbColor(91, 169, 244),
            )
        };
        Self {
            background,
            surface: blend(background, text, 5),
            text,
            muted: blend(text, background, 42),
            accent,
            border: blend(background, text, 26),
            success,
            warning,
            error,
            info,
        }
    }
}

/// Used by Auto when the terminal did not report its colors: only the
/// terminal's own ANSI palette is used, so text is readable on any theme.
fn ansi_native_palette() -> Palette {
    Palette {
        background: Color::Reset,
        surface: Color::Reset,
        surface_alt: Color::Reset,
        text: Color::Reset,
        text_muted: Color::DarkGray,
        accent: Color::Cyan,
        accent_alt: Color::LightCyan,
        selection_bg: Color::Blue,
        selection_text: Color::White,
        border: Color::DarkGray,
        border_focused: Color::Cyan,
        success: Color::Green,
        warning: Color::Yellow,
        error: Color::Red,
        info: Color::Blue,
    }
}

impl Palette {
    /// Guarantees readable text, accents and status colors on the canvas
    /// that will really be behind them.
    fn harmonized(mut self, canvas: RgbColor) -> Self {
        let fix = |color: &mut Color, ratio: f32| {
            if let Some(rgb) = RgbColor::from_color(*color) {
                *color = rgb.readable_on(canvas, ratio).color();
            }
        };
        fix(&mut self.text, 7.0);
        fix(&mut self.text_muted, 4.0);
        fix(&mut self.accent, 3.2);
        fix(&mut self.accent_alt, 3.2);
        fix(&mut self.border_focused, 3.0);
        fix(&mut self.border, 1.6);
        fix(&mut self.success, 3.2);
        fix(&mut self.warning, 3.2);
        fix(&mut self.error, 3.2);
        fix(&mut self.info, 3.2);
        if let (Some(selection), Some(text)) = (
            RgbColor::from_color(self.selection_bg),
            RgbColor::from_color(self.selection_text),
        ) {
            self.selection_text = text.readable_on(selection, 4.5).color();
        }
        self
    }

    fn mapped(mut self, map: impl Fn(Color) -> Color) -> Self {
        for color in [
            &mut self.background,
            &mut self.surface,
            &mut self.surface_alt,
            &mut self.text,
            &mut self.text_muted,
            &mut self.accent,
            &mut self.accent_alt,
            &mut self.selection_bg,
            &mut self.selection_text,
            &mut self.border,
            &mut self.border_focused,
            &mut self.success,
            &mut self.warning,
            &mut self.error,
            &mut self.info,
        ] {
            *color = map(*color);
        }
        self
    }
}

/// Reduces one color to what the terminal can display.
pub fn downgrade(color: Color, depth: ColorDepth) -> Color {
    let Some(RgbColor(red, green, blue)) = RgbColor::from_color(color) else {
        return color;
    };
    match depth {
        ColorDepth::TrueColor => color,
        ColorDepth::Ansi256 => Color::Indexed(nearest_256(red, green, blue)),
        ColorDepth::Ansi16 => nearest_ansi16(red, green, blue),
    }
}

fn nearest_256(red: u8, green: u8, blue: u8) -> u8 {
    const STEPS: [u8; 6] = [0, 95, 135, 175, 215, 255];
    let nearest_step = |value: u8| {
        (0..6usize)
            .min_by_key(|index| (i32::from(STEPS[*index]) - i32::from(value)).abs())
            .unwrap_or(0)
    };
    let distance = |r: u8, g: u8, b: u8| {
        let d = |a: u8, b: u8| (i32::from(a) - i32::from(b)).pow(2);
        d(r, red) + d(g, green) + d(b, blue)
    };
    let (ri, gi, bi) = (nearest_step(red), nearest_step(green), nearest_step(blue));
    let cube = (16 + 36 * ri + 6 * gi + bi) as u8;
    let cube_distance = distance(STEPS[ri], STEPS[gi], STEPS[bi]);
    let average = (u16::from(red) + u16::from(green) + u16::from(blue)) / 3;
    let gray_index = ((average.saturating_sub(8) + 5) / 10).min(23) as u8;
    let gray_level = 8 + 10 * gray_index;
    if distance(gray_level, gray_level, gray_level) < cube_distance {
        232 + gray_index
    } else {
        cube
    }
}

fn nearest_ansi16(red: u8, green: u8, blue: u8) -> Color {
    const TABLE: [(Color, (u8, u8, u8)); 16] = [
        (Color::Black, (0, 0, 0)),
        (Color::Red, (205, 49, 49)),
        (Color::Green, (13, 188, 121)),
        (Color::Yellow, (229, 229, 16)),
        (Color::Blue, (36, 114, 200)),
        (Color::Magenta, (188, 63, 188)),
        (Color::Cyan, (17, 168, 205)),
        (Color::Gray, (204, 204, 204)),
        (Color::DarkGray, (102, 102, 102)),
        (Color::LightRed, (241, 76, 76)),
        (Color::LightGreen, (35, 209, 139)),
        (Color::LightYellow, (245, 245, 67)),
        (Color::LightBlue, (59, 142, 234)),
        (Color::LightMagenta, (214, 112, 214)),
        (Color::LightCyan, (41, 184, 219)),
        (Color::White, (255, 255, 255)),
    ];
    TABLE
        .iter()
        .min_by_key(|(_, (r, g, b))| {
            let d = |a: u8, b: u8| (i32::from(a) - i32::from(b)).pow(2);
            d(*r, red) + d(*g, green) + d(*b, blue)
        })
        .map(|(color, _)| *color)
        .unwrap_or(Color::Reset)
}

impl Theme {
    /// The palette before terminal adaptation; Auto is derived from the
    /// terminal's reported colors when they are known.
    pub fn base_palette(self, custom: CustomColors, terminal: TerminalProfile) -> Palette {
        match (self, terminal.background) {
            (Self::Auto, Some(background)) => {
                CustomColors::from_terminal(background, terminal.foreground).palette()
            }
            _ => self.palette_with_custom(custom),
        }
    }

    /// Adapts this theme to the terminal it will be drawn on:
    ///
    /// * a light theme on a dark terminal (or the reverse) paints its own
    ///   canvas instead of leaving unreadable text on the wrong background;
    /// * every text, accent and status color is nudged to a readable contrast
    ///   against the canvas that is really behind it;
    /// * RGB colors are reduced for terminals without truecolor.
    pub fn resolve(
        self,
        custom: CustomColors,
        terminal: TerminalProfile,
        mode: ColorMode,
    ) -> ResolvedPalette {
        let mut palette = self.base_palette(custom, terminal);
        let own_canvas = RgbColor::from_color(palette.background);
        let mismatch = self != Self::Auto
            && !self.paints_background()
            && matches!(
                (own_canvas, terminal.background),
                (Some(own), Some(real)) if own.is_light() != real.is_light()
            );
        let paints_background = self.paints_background() || mismatch;
        let canvas = if paints_background {
            own_canvas
        } else {
            terminal.background.or(own_canvas)
        };
        if let Some(canvas) = canvas {
            palette = palette.harmonized(canvas);
        }
        if !paints_background {
            // AGK is an overlay on the user's terminal, not a second painted
            // desktop: large surfaces inherit the native background.
            palette.background = Color::Reset;
            palette.surface = Color::Reset;
            palette.surface_alt = Color::Reset;
        }
        let depth = mode.depth(terminal.depth);
        ResolvedPalette {
            palette: palette.mapped(|color| downgrade(color, depth)),
            paints_background,
            adapted: mismatch,
        }
    }
}

pub const DEFAULT_REFRESH_MS: u64 = 1_000;

/// Preferences persisted outside the Agentik registries because they only
/// affect this local presentation surface.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Preferences {
    pub theme: Theme,
    pub custom_colors: CustomColors,
    pub color_mode: ColorMode,
    pub split_preview: bool,
    pub refresh_ms: u64,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            theme: Theme::default(),
            custom_colors: CustomColors::default(),
            color_mode: ColorMode::default(),
            split_preview: true,
            refresh_ms: DEFAULT_REFRESH_MS,
        }
    }
}

impl Preferences {
    pub fn load() -> io::Result<Self> {
        Self::load_from(default_preferences_path()?)
    }

    /// Loads preferences from an injectable path. A missing file is the same
    /// as first launch, and malformed or unknown values fall back field by
    /// field without making the TUI unusable.
    pub fn load_from(path: impl AsRef<Path>) -> io::Result<Self> {
        let bytes = match fs::read(path.as_ref()) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Self::default()),
            Err(error) => return Err(error),
        };
        Ok(Self::parse(&String::from_utf8_lossy(&bytes)))
    }

    pub fn save(&self) -> io::Result<()> {
        self.save_to(default_preferences_path()?)
    }

    /// Atomically replaces the preference file. On Unix, the temporary file
    /// is created with mode 0600 and renamed over the destination in the same
    /// directory, so readers observe either the old or the complete new file.
    pub fn save_to(&self, path: impl AsRef<Path>) -> io::Result<()> {
        let path = path.as_ref();
        let refresh_ms = if self.refresh_ms == 0 {
            DEFAULT_REFRESH_MS
        } else {
            self.refresh_ms
        };
        let mut contents = format!(
            "# AGK native TUI preferences\ntheme={}\ncolors={}\nsplit_preview={}\nrefresh_ms={}\n",
            self.theme.slug(),
            self.color_mode.slug(),
            self.split_preview,
            refresh_ms
        );
        for index in 0..CustomColors::LEN {
            contents.push_str(&format!(
                "{}={}\n",
                CustomColors::config_key(index),
                self.custom_colors.get(index).hex()
            ));
        }
        atomic_write(path, contents.as_bytes())
    }

    fn parse(contents: &str) -> Self {
        let mut preferences = Self::default();
        for line in contents.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let Some((key, value)) = line.split_once('=') else {
                continue;
            };
            let key = key.trim();
            let value = value.trim();
            match key {
                "theme" => {
                    if let Some(theme) = Theme::from_slug(value) {
                        preferences.theme = theme;
                    }
                }
                "colors" => {
                    if let Some(mode) = ColorMode::from_slug(value) {
                        preferences.color_mode = mode;
                    }
                }
                "split_preview" => match value.to_ascii_lowercase().as_str() {
                    "true" => preferences.split_preview = true,
                    "false" => preferences.split_preview = false,
                    _ => {}
                },
                "refresh_ms" => {
                    if let Ok(refresh_ms) = value.parse::<u64>()
                        && refresh_ms > 0
                    {
                        preferences.refresh_ms = refresh_ms;
                    }
                }
                _ => {
                    if let Some(index) =
                        (0..CustomColors::LEN).find(|index| CustomColors::config_key(*index) == key)
                        && let Some(color) = RgbColor::from_hex(value)
                    {
                        preferences.custom_colors.set(index, color);
                    }
                }
            }
        }
        preferences
    }
}

/// The canonical per-user preferences path.
pub fn default_preferences_path() -> io::Result<PathBuf> {
    let home = std::env::var_os("HOME").filter(|value| !value.is_empty());
    home.map(PathBuf::from)
        .map(|path| path.join(".config/agk/tui.conf"))
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "HOME is not set"))
}

fn atomic_write(path: &Path, contents: &[u8]) -> io::Result<()> {
    let file_name = path
        .file_name()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "missing file name"))?;
    let parent = path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;

    static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);
    let mut temporary = None;
    let mut file = None;
    for _ in 0..128 {
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let temp_name = format!(
            ".{}.tmp.{}.{}",
            file_name.to_string_lossy(),
            std::process::id(),
            sequence
        );
        let temp_path = parent.join(temp_name);
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&temp_path) {
            Ok(opened) => {
                temporary = Some(temp_path);
                file = Some(opened);
                break;
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }

    let temporary = temporary.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::AlreadyExists,
            "could not allocate an AGK preference temporary file",
        )
    })?;
    let mut file = file.expect("temporary path and file are allocated together");

    let write_result = (|| {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(fs::Permissions::from_mode(0o600))?;
        }
        file.write_all(contents)?;
        file.sync_all()?;
        drop(file);

        #[cfg(unix)]
        fs::rename(&temporary, path)?;

        #[cfg(not(unix))]
        {
            if path.exists() {
                fs::remove_file(path)?;
            }
            fs::rename(&temporary, path)?;
        }

        #[cfg(unix)]
        File::open(parent)?.sync_all()?;

        Ok(())
    })();

    if write_result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    write_result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;
    use std::sync::atomic::{AtomicU64, Ordering};

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);
            let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir()
                .join(format!("agk-theme-test-{}-{sequence}", std::process::id()));
            fs::create_dir(&path).expect("create isolated test directory");
            Self(path)
        }

        fn config(&self) -> PathBuf {
            self.0.join("nested/tui.conf")
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn preferences_round_trip_through_the_real_file_format() {
        let directory = TestDirectory::new();
        let path = directory.config();
        let expected = Preferences {
            theme: Theme::ClaudeLight,
            split_preview: false,
            refresh_ms: 2_500,
            ..Preferences::default()
        };

        expected.save_to(&path).expect("save preferences");

        assert_eq!(Preferences::load_from(path).unwrap(), expected);
    }

    #[test]
    fn custom_colors_accept_hex_and_round_trip_with_the_selected_theme() {
        let directory = TestDirectory::new();
        let path = directory.config();
        let mut expected = Preferences {
            theme: Theme::Custom,
            ..Preferences::default()
        };
        expected.custom_colors.background = RgbColor(255, 0, 170);
        expected.custom_colors.accent = RgbColor(12, 34, 56);

        expected.save_to(&path).unwrap();
        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("theme=custom"));
        assert!(contents.contains("custom_background=#FF00AA"));
        assert!(contents.contains("custom_accent=#0C2238"));
        assert_eq!(Preferences::load_from(path).unwrap(), expected);
    }

    #[test]
    fn malformed_custom_colors_are_ignored_field_by_field() {
        let directory = TestDirectory::new();
        let path = directory.config();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(
            &path,
            "theme=custom\ncustom_background=#123456\ncustom_accent=broken\n",
        )
        .unwrap();

        let loaded = Preferences::load_from(path).unwrap();
        assert_eq!(loaded.theme, Theme::Custom);
        assert_eq!(loaded.custom_colors.background, RgbColor(0x12, 0x34, 0x56));
        assert_eq!(loaded.custom_colors.accent, CustomColors::default().accent);
    }

    #[test]
    fn corrupt_and_unknown_values_fall_back_without_losing_valid_values() {
        let directory = TestDirectory::new();
        let path = directory.config();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(
            &path,
            b"theme=not-a-theme\nsplit_preview=perhaps\nrefresh_ms=0\nfuture_key=yes\n\xff\n",
        )
        .unwrap();

        assert_eq!(
            Preferences::load_from(&path).unwrap(),
            Preferences::default()
        );

        fs::write(
            &path,
            b"theme=matrix\nsplit_preview=broken\nrefresh_ms=275\n",
        )
        .unwrap();
        assert_eq!(
            Preferences::load_from(path).unwrap(),
            Preferences {
                theme: Theme::CodexLight,
                split_preview: true,
                refresh_ms: 275,
                ..Preferences::default()
            }
        );
    }

    #[test]
    fn save_atomically_replaces_existing_file_without_temporary_debris() {
        let directory = TestDirectory::new();
        let path = directory.config();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, "incomplete old contents").unwrap();

        #[cfg(unix)]
        let old_inode = {
            use std::os::unix::fs::MetadataExt;
            fs::metadata(&path).unwrap().ino()
        };

        let expected = Preferences {
            theme: Theme::ClaudeDark,
            split_preview: false,
            refresh_ms: 750,
            ..Preferences::default()
        };
        expected.save_to(&path).unwrap();

        assert_eq!(Preferences::load_from(&path).unwrap(), expected);
        let entries = fs::read_dir(path.parent().unwrap())
            .unwrap()
            .map(|entry| entry.unwrap().file_name())
            .collect::<Vec<_>>();
        assert_eq!(entries, vec![path.file_name().unwrap()]);

        #[cfg(unix)]
        {
            use std::os::unix::fs::{MetadataExt, PermissionsExt};
            let metadata = fs::metadata(&path).unwrap();
            assert_ne!(metadata.ino(), old_inode);
            assert_eq!(metadata.permissions().mode() & 0o777, 0o600);
        }
    }

    #[test]
    fn theme_navigation_wraps_and_slugs_are_stable_and_unique() {
        let mut seen = HashSet::new();
        for (index, theme) in Theme::ALL.into_iter().enumerate() {
            assert!(seen.insert(theme.slug()));
            assert_eq!(Theme::from_slug(theme.slug()), Some(theme));
            assert_eq!(
                Theme::from_slug(&theme.slug().to_ascii_uppercase()),
                Some(theme)
            );
            assert_eq!(theme.next().previous(), theme);
            assert_eq!(theme.previous().next(), theme);
            assert_eq!(theme.next(), Theme::ALL[(index + 1) % Theme::ALL.len()]);
        }
        assert_eq!(Theme::Custom.next(), Theme::Auto);
        assert_eq!(Theme::Auto.previous(), Theme::Custom);
    }

    #[test]
    fn every_theme_has_a_distinct_semantic_palette() {
        // Auto is terminal-derived; its static fallback is ANSI-only.
        let fixed = Theme::ALL.into_iter().filter(|theme| *theme != Theme::Auto);
        for (index, theme) in fixed.clone().enumerate() {
            let palette = theme.palette();
            assert_ne!(
                palette.background,
                palette.text,
                "{} contrast",
                theme.slug()
            );
            assert_ne!(
                palette.background,
                palette.accent,
                "{} accent",
                theme.slug()
            );
            assert_ne!(
                palette.surface,
                palette.surface_alt,
                "{} surfaces",
                theme.slug()
            );
            assert_ne!(
                palette.success,
                palette.warning,
                "{} statuses",
                theme.slug()
            );
            assert_ne!(palette.warning, palette.error, "{} statuses", theme.slug());
            assert_ne!(palette.error, palette.info, "{} statuses", theme.slug());
            assert_eq!(
                theme.swatches(),
                [
                    palette.background,
                    palette.surface_alt,
                    palette.accent,
                    palette.info,
                    palette.text,
                ]
            );
            for other in fixed.clone().skip(index + 1) {
                assert_ne!(palette, other.palette(), "duplicate palette: {theme:?}");
            }
        }
    }

    fn terminal(background: (u8, u8, u8)) -> TerminalProfile {
        TerminalProfile {
            background: Some(RgbColor(background.0, background.1, background.2)),
            foreground: None,
            depth: ColorDepth::TrueColor,
        }
    }

    fn rgb(color: Color) -> RgbColor {
        RgbColor::from_color(color).expect("truecolor palette entry")
    }

    #[test]
    fn auto_theme_follows_dark_and_light_terminals_without_painting() {
        for background in [(13, 17, 23), (253, 246, 227), (40, 44, 52), (255, 255, 255)] {
            let profile = terminal(background);
            let resolved = Theme::Auto.resolve(CustomColors::default(), profile, ColorMode::Auto);
            let canvas = profile.background.unwrap();
            assert!(!resolved.paints_background);
            assert_eq!(resolved.palette.background, Color::Reset);
            assert!(rgb(resolved.palette.text).contrast(canvas) >= 7.0);
            assert!(rgb(resolved.palette.text_muted).contrast(canvas) >= 4.0);
            assert!(rgb(resolved.palette.accent).contrast(canvas) >= 3.2);
            assert!(rgb(resolved.palette.error).contrast(canvas) >= 3.2);
        }
    }

    #[test]
    fn auto_theme_without_terminal_colors_uses_only_the_native_ansi_palette() {
        let resolved = Theme::Auto.resolve(
            CustomColors::default(),
            TerminalProfile::default(),
            ColorMode::Auto,
        );
        assert!(!resolved.paints_background);
        assert_eq!(resolved.palette.text, Color::Reset);
        assert_eq!(resolved.palette.accent, Color::Cyan);
    }

    #[test]
    fn mismatched_light_and_dark_themes_paint_their_own_canvas() {
        let dark_terminal = terminal((16, 16, 20));
        let light =
            Theme::ClaudeLight.resolve(CustomColors::default(), dark_terminal, ColorMode::Auto);
        assert!(light.paints_background && light.adapted);
        assert_eq!(
            light.palette.background,
            Theme::ClaudeLight.palette().background
        );

        let dark =
            Theme::ClaudeDark.resolve(CustomColors::default(), dark_terminal, ColorMode::Auto);
        assert!(!dark.paints_background && !dark.adapted);
        assert_eq!(dark.palette.background, Color::Reset);

        let on_light = Theme::HermesDark.resolve(
            CustomColors::default(),
            terminal((250, 250, 250)),
            ColorMode::Auto,
        );
        assert!(on_light.paints_background);
    }

    #[test]
    fn every_theme_is_readable_on_every_terminal_background() {
        for background in [
            (0, 0, 0),
            (30, 30, 46),
            (60, 60, 60),
            (253, 246, 227),
            (255, 255, 255),
        ] {
            let profile = terminal(background);
            for theme in Theme::ALL {
                let resolved = theme.resolve(CustomColors::default(), profile, ColorMode::Auto);
                let canvas = if resolved.paints_background {
                    rgb(resolved.palette.background)
                } else {
                    profile.background.unwrap()
                };
                for (label, color, ratio) in [
                    ("text", resolved.palette.text, 7.0),
                    ("muted", resolved.palette.text_muted, 4.0),
                    ("accent", resolved.palette.accent, 3.2),
                    ("success", resolved.palette.success, 3.2),
                    ("warning", resolved.palette.warning, 3.2),
                    ("error", resolved.palette.error, 3.2),
                ] {
                    assert!(
                        rgb(color).contrast(canvas) >= ratio - 0.01,
                        "{} {label} on {background:?}",
                        theme.slug()
                    );
                }
                assert!(
                    rgb(resolved.palette.selection_text)
                        .contrast(rgb(resolved.palette.selection_bg))
                        >= 4.49,
                    "{} selection",
                    theme.slug()
                );
            }
        }
    }

    #[test]
    fn limited_terminals_never_receive_truecolor_escapes() {
        let mut profile = terminal((16, 16, 20));
        profile.depth = ColorDepth::Ansi256;
        let palette = Theme::Midnight
            .resolve(CustomColors::default(), profile, ColorMode::Auto)
            .palette;
        assert!(matches!(palette.accent, Color::Indexed(_)));
        assert!(matches!(palette.text, Color::Indexed(_)));

        let forced = Theme::Midnight
            .resolve(CustomColors::default(), profile, ColorMode::Ansi16)
            .palette;
        assert!(!matches!(forced.accent, Color::Rgb(..) | Color::Indexed(_)));
        let truecolor = Theme::Midnight
            .resolve(CustomColors::default(), profile, ColorMode::TrueColor)
            .palette;
        assert!(matches!(truecolor.accent, Color::Rgb(..)));

        assert_eq!(
            downgrade(Color::Rgb(255, 255, 255), ColorDepth::Ansi256),
            Color::Indexed(231)
        );
        assert_eq!(
            downgrade(Color::Rgb(128, 128, 128), ColorDepth::Ansi256),
            Color::Indexed(244)
        );
        assert_eq!(
            downgrade(Color::Rgb(0, 0, 0), ColorDepth::Ansi16),
            Color::Black
        );
    }

    #[test]
    fn custom_colors_can_be_seeded_from_any_rgb_theme_and_color_mode_round_trips() {
        let seeded = CustomColors::from_palette(Theme::ClaudeDark.palette()).unwrap();
        assert_eq!(seeded.accent.color(), Theme::ClaudeDark.palette().accent);
        assert!(CustomColors::from_palette(Theme::Auto.palette()).is_none());

        let directory = TestDirectory::new();
        let path = directory.config();
        let expected = Preferences {
            color_mode: ColorMode::Ansi256,
            ..Preferences::default()
        };
        expected.save_to(&path).unwrap();
        assert!(fs::read_to_string(&path).unwrap().contains("colors=256"));
        assert_eq!(Preferences::load_from(path).unwrap(), expected);
        for mode in ColorMode::ALL {
            assert_eq!(ColorMode::from_slug(mode.slug()), Some(mode));
        }
    }
}
