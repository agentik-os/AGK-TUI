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

/// Built-in AGK themes. Variant order is the stable order shown in Settings.
#[derive(Clone, Copy, Debug, Default, Eq, Hash, PartialEq)]
pub enum Theme {
    #[default]
    ClassicDark,
    ClassicLight,
    HermesDark,
    HermesLight,
    ClaudeDark,
    ClaudeLight,
    CodexDark,
    CodexLight,
}

impl Theme {
    pub const ALL: [Self; 8] = [
        Self::ClassicDark,
        Self::ClassicLight,
        Self::HermesDark,
        Self::HermesLight,
        Self::ClaudeDark,
        Self::ClaudeLight,
        Self::CodexDark,
        Self::CodexLight,
    ];

    /// Stable identifier used in `tui.conf`.
    pub const fn slug(self) -> &'static str {
        match self {
            Self::ClassicDark => "classic-dark",
            Self::ClassicLight => "classic-light",
            Self::HermesDark => "hermes-dark",
            Self::HermesLight => "hermes-light",
            Self::ClaudeDark => "claude-dark",
            Self::ClaudeLight => "claude-light",
            Self::CodexDark => "codex-dark",
            Self::CodexLight => "codex-light",
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Self::ClassicDark => "Classic Dark",
            Self::ClassicLight => "Classic Light",
            Self::HermesDark => "Hermes Dark",
            Self::HermesLight => "Hermes Light",
            Self::ClaudeDark => "Claude Dark",
            Self::ClaudeLight => "Claude Light",
            Self::CodexDark => "Codex Dark",
            Self::CodexLight => "Codex Light",
        }
    }

    pub const fn description(self) -> &'static str {
        match self {
            Self::ClassicDark => "Neutral graphite, crisp white type and a restrained blue accent.",
            Self::ClassicLight => "Clean paper white, charcoal type and quiet professional blue.",
            Self::HermesDark => "Official Hermes gold and bronze on deep navy-black.",
            Self::HermesLight => "Hermes amber inks tuned for a clean light terminal.",
            Self::ClaudeDark => "Claude terracotta with warm, editorial dark neutrals.",
            Self::ClaudeLight => "Claude terracotta on a calm parchment workspace.",
            Self::CodexDark => "Codex green and cyan on a precise graphite shell.",
            Self::CodexLight => "Codex green with crisp, low-noise daylight contrast.",
        }
    }

    pub const fn next(self) -> Self {
        match self {
            Self::ClassicDark => Self::ClassicLight,
            Self::ClassicLight => Self::HermesDark,
            Self::HermesDark => Self::HermesLight,
            Self::HermesLight => Self::ClaudeDark,
            Self::ClaudeDark => Self::ClaudeLight,
            Self::ClaudeLight => Self::CodexDark,
            Self::CodexDark => Self::CodexLight,
            Self::CodexLight => Self::ClassicDark,
        }
    }

    pub const fn previous(self) -> Self {
        match self {
            Self::ClassicDark => Self::CodexLight,
            Self::ClassicLight => Self::ClassicDark,
            Self::HermesDark => Self::ClassicLight,
            Self::HermesLight => Self::HermesDark,
            Self::ClaudeDark => Self::HermesLight,
            Self::ClaudeLight => Self::ClaudeDark,
            Self::CodexDark => Self::ClaudeLight,
            Self::CodexLight => Self::CodexDark,
        }
    }

    pub fn from_slug(slug: &str) -> Option<Self> {
        let slug = slug.trim();
        // Preserve preferences written by the pre-provider AGK themes.
        match slug.to_ascii_lowercase().as_str() {
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
    pub const fn swatches(self) -> [Color; 5] {
        let palette = self.palette();
        [
            palette.background,
            palette.surface_alt,
            palette.accent,
            palette.info,
            palette.text,
        ]
    }

    pub const fn palette(self) -> Palette {
        match self {
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
        }
    }
}

pub const DEFAULT_REFRESH_MS: u64 = 1_000;

/// Preferences persisted outside the Agentik registries because they only
/// affect this local presentation surface.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Preferences {
    pub theme: Theme,
    pub split_preview: bool,
    pub refresh_ms: u64,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            theme: Theme::default(),
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
        let contents = format!(
            "# AGK native TUI preferences\ntheme={}\nsplit_preview={}\nrefresh_ms={}\n",
            self.theme.slug(),
            self.split_preview,
            refresh_ms
        );
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
                _ => {}
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
        };

        expected.save_to(&path).expect("save preferences");

        assert_eq!(Preferences::load_from(path).unwrap(), expected);
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
        assert_eq!(Theme::CodexLight.next(), Theme::ClassicDark);
        assert_eq!(Theme::ClassicDark.previous(), Theme::CodexLight);
    }

    #[test]
    fn every_theme_has_a_distinct_semantic_palette() {
        for (index, theme) in Theme::ALL.into_iter().enumerate() {
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
            for other in Theme::ALL.into_iter().skip(index + 1) {
                assert_ne!(palette, other.palette(), "duplicate palette: {theme:?}");
            }
        }
    }
}
