//! Mouse text selection over the mirrored provider pane.
//!
//! AGK captures the mouse to route clicks and scrolling, which disables the
//! host terminal's own selection. This module restores select-to-copy for
//! the pane: the selection is tracked in screen cells and the text is read
//! back from the frame that was actually rendered, so live panes and plain
//! history are handled by the same code.

use ratatui::layout::Rect;

/// Characters rendered inside the preview rectangle, one symbol per cell.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct PreviewGrid {
    pub rect: Rect,
    pub rows: Vec<Vec<String>>,
}

/// A stream selection between two screen cells, as in a normal terminal.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Selection {
    pub anchor: (u16, u16),
    pub cursor: (u16, u16),
    /// False until the pointer leaves the cell it was pressed on.
    pub moved: bool,
}

impl Selection {
    pub const fn at(column: u16, row: u16) -> Self {
        Self {
            anchor: (column, row),
            cursor: (column, row),
            moved: false,
        }
    }

    /// Extends the selection, keeping the pointer inside the pane.
    pub fn drag_to(&mut self, column: u16, row: u16, rect: Rect) {
        if rect.width == 0 || rect.height == 0 {
            return;
        }
        let cursor = (
            column.clamp(rect.x, rect.x + rect.width - 1),
            row.clamp(rect.y, rect.y + rect.height - 1),
        );
        if cursor != self.cursor {
            self.cursor = cursor;
            self.moved = true;
        }
    }

    /// Start and end in reading order, as `(column, row)`.
    pub fn ordered(&self) -> ((u16, u16), (u16, u16)) {
        let key = |point: (u16, u16)| (point.1, point.0);
        if key(self.anchor) <= key(self.cursor) {
            (self.anchor, self.cursor)
        } else {
            (self.cursor, self.anchor)
        }
    }

    pub fn contains(&self, column: u16, row: u16) -> bool {
        let (start, end) = self.ordered();
        (start.1, start.0) <= (row, column) && (row, column) <= (end.1, end.0)
    }
}

pub fn inside(rect: Rect, column: u16, row: u16) -> bool {
    column >= rect.x
        && column < rect.x.saturating_add(rect.width)
        && row >= rect.y
        && row < rect.y.saturating_add(rect.height)
}

/// Text covered by the selection, with trailing padding removed per row.
pub fn extract(grid: &PreviewGrid, selection: &Selection) -> String {
    let (start, end) = selection.ordered();
    let mut lines = Vec::new();
    for row in start.1..=end.1 {
        let Some(cells) = row
            .checked_sub(grid.rect.y)
            .and_then(|index| grid.rows.get(usize::from(index)))
        else {
            continue;
        };
        let first = if row == start.1 { start.0 } else { grid.rect.x };
        let last = if row == end.1 {
            end.0
        } else {
            grid.rect.x + grid.rect.width.saturating_sub(1)
        };
        let from = usize::from(first.saturating_sub(grid.rect.x));
        let to = usize::from(last.saturating_sub(grid.rect.x)).min(cells.len().saturating_sub(1));
        let line = if cells.is_empty() || from > to {
            String::new()
        } else {
            cells[from..=to].concat()
        };
        lines.push(line.trim_end().to_owned());
    }
    while lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }
    lines.join("\n")
}

/// The word under a double click: a path, URL, identifier or number.
pub fn word_at(grid: &PreviewGrid, column: u16, row: u16) -> Option<Selection> {
    if !inside(grid.rect, column, row) {
        return None;
    }
    let cells = grid.rows.get(usize::from(row - grid.rect.y))?;
    let index = usize::from(column - grid.rect.x);
    let is_word = |cell: &String| {
        cell.chars().next().is_some_and(|character| {
            character.is_alphanumeric() || "_-./:~@%+#=?&".contains(character)
        })
    };
    if !cells.get(index).is_some_and(is_word) {
        return None;
    }
    let mut first = index;
    while first > 0 && is_word(&cells[first - 1]) {
        first -= 1;
    }
    let mut last = index;
    while last + 1 < cells.len() && is_word(&cells[last + 1]) {
        last += 1;
    }
    Some(Selection {
        anchor: (grid.rect.x + first as u16, row),
        cursor: (grid.rect.x + last as u16, row),
        moved: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grid(lines: &[&str]) -> PreviewGrid {
        let width = lines.iter().map(|line| line.chars().count()).max().unwrap();
        PreviewGrid {
            rect: Rect::new(10, 5, width as u16, lines.len() as u16),
            rows: lines
                .iter()
                .map(|line| {
                    let mut cells = line.chars().map(String::from).collect::<Vec<_>>();
                    cells.resize(width, " ".into());
                    cells
                })
                .collect(),
        }
    }

    #[test]
    fn stream_selection_copies_partial_first_and_last_rows_without_padding() {
        let grid = grid(&["alpha beta   ", "gamma        ", "delta epsilon"]);
        let mut selection = Selection::at(16, 5);
        selection.drag_to(14, 7, grid.rect);
        assert!(selection.moved);
        assert_eq!(extract(&grid, &selection), "beta\ngamma\ndelta");

        // Dragging upwards selects the same text.
        let mut reversed = Selection::at(14, 7);
        reversed.drag_to(16, 5, grid.rect);
        assert_eq!(extract(&grid, &reversed), "beta\ngamma\ndelta");
        assert!(reversed.contains(10, 6) && !reversed.contains(15, 7));
    }

    #[test]
    fn dragging_outside_the_pane_is_clamped_to_its_edges() {
        let grid = grid(&["one two", "three  "]);
        let mut selection = Selection::at(10, 5);
        selection.drag_to(200, 200, grid.rect);
        assert_eq!(selection.cursor, (16, 6));
        assert_eq!(extract(&grid, &selection), "one two\nthree");
        selection.drag_to(0, 0, grid.rect);
        assert_eq!(selection.cursor, (10, 5));
    }

    #[test]
    fn wide_glyph_continuation_cells_do_not_add_spaces() {
        let mut grid = grid(&["ab"]);
        grid.rows[0] = vec!["東".into(), String::new(), "京".into(), String::new()];
        grid.rect.width = 4;
        let mut selection = Selection::at(10, 5);
        selection.drag_to(13, 5, grid.rect);
        assert_eq!(extract(&grid, &selection), "東京");
    }

    #[test]
    fn double_click_selects_paths_and_urls_but_not_blank_cells() {
        let grid = grid(&[
            "open ~/projects/AGK-TUI/src now",
            "see https://agk.dev/x?y=1 ",
        ]);
        let word = word_at(&grid, 20, 5).unwrap();
        assert_eq!(extract(&grid, &word), "~/projects/AGK-TUI/src");
        let url = word_at(&grid, 16, 6).unwrap();
        assert_eq!(extract(&grid, &url), "https://agk.dev/x?y=1");
        assert_eq!(word_at(&grid, 14, 5), None);
        assert_eq!(word_at(&grid, 0, 0), None);
    }
}
