# Theme System for Stupidex

## Summary

Implement a runtime-switchable theme system for Stupidex with three predefined themes: Default, Windows XP, and Green Terminal. Themes will be applied via Textual CSS and can be switched through a `/theme` command.

---

## Problem Frame

Stupidex currently has a single static theme defined in `src/stupidex/main.tcss` and inline CSS in widgets like `Sidebar`. Users want visual variety and personalization. The goal is to create a theme system that allows switching between distinct visual styles at runtime without restarting the app.

---

## Requirements

- R1. Support at least three themes: Default, Windows XP, and Green Terminal
- R2. Themes can be switched at runtime without app restart
- R3. Theme switching is accessible via a command (e.g., `/theme`)
- R4. Current theme persists across sessions (saved in config)
- R5. Each theme defines colors for: background, text, borders, highlights, message widgets, sidebar

---

## Scope Boundaries

- Custom user-created themes are NOT in scope (only predefined)
- No theme preview/management UI beyond the command
- No per-component theme overrides

---

## Context & Research

### Relevant Code and Patterns

- `src/stupidex/main.tcss` - Main Textual CSS file (127 lines)
- `src/stupidex/app.py` - Main app class with `CSS_PATH` pointing to main.tcss
- `src/stupidex/widgets/sidebar.py` - Has inline `DEFAULT_CSS` (lines 49-142)
- `src/stupidex/config.py` - ConfigManager pattern for persisting settings
- `src/stupidex/commands/session_commands.py` - Command provider pattern using `/new`, `/switch`, etc.

### Textual Theme Capabilities

Textual supports:
- `app.theme` property to switch built-in themes at runtime
- CSS variables (`$primary`, `$secondary`, etc.) that change with themes
- Custom CSS injection via `app.stylesheet`
- Persistent CSS via `CSS_PATH`

---

## Key Technical Decisions

1. **Theme Storage**: Store theme as a string identifier in `Config` dataclass
2. **Theme Application**: Use Textual's `app.theme` for base theme, then apply custom CSS overrides
3. **Theme Data Structure**: Define themes as dictionaries with CSS variable values
4. **Switching Mechanism**: `/theme` command opens a picker screen similar to `/model`

---

## Implementation Units

### U1. Theme Data Model and Registry

**Goal:** Create theme definitions and a registry to manage them

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `src/stupidex/themes/__init__.py`
- Create: `src/stupidex/themes/registry.py`

**Approach:**
- Define a `Theme` dataclass with fields for all customizable properties
- Create three theme instances: Default, Windows XP, Green Terminal
- Build a `ThemeRegistry` class that maps theme names to Theme objects
- Export a `get_theme_registry()` function following existing registry patterns

**Patterns to follow:**
- `src/stupidex/agents/__init__.py` registry pattern
- `src/stupidex/tools/__init__.py` registry pattern

**Test scenarios:**
- ThemeRegistry contains exactly 3 themes by default
- `get_theme("default")` returns the default theme
- All themes have required color properties defined

**Verification:**
- Import and instantiate ThemeRegistry without errors
- All three themes are accessible by name

---

### U2. Config Integration for Theme Persistence

**Goal:** Add theme field to Config and persist it

**Requirements:** R4

**Dependencies:** U1

**Files:**
- Modify: `src/stupidex/config.py`

**Approach:**
- Add `theme: str = "default"` field to Config dataclass
- Theme is saved to `~/.stupidex/config.json` automatically via existing ConfigManager
- Add `STUPIDEX_THEME` to `_ENV_MAP` for environment variable override

**Patterns to follow:**
- Existing Config fields like `default_model`

**Test scenarios:**
- Config loads with `theme="default"` when not set
- Config persists theme change to config.json
- Environment variable `STUPIDEX_THEME` overrides config file

**Verification:**
- Config field exists and defaults correctly
- JSON serialization includes theme field

---

### U3. Theme Application Logic

**Goal:** Create mechanism to apply themes at runtime

**Requirements:** R2

**Dependencies:** U1, U2

**Files:**
- Create: `src/stupidex/themes/applier.py`

**Approach:**
- Define CSS variable mappings for each theme as dictionaries
- Create an `apply_theme(app, theme_name)` function that:
  1. Loads theme from registry
  2. Generates CSS variable overrides string
  3. Injects CSS into app's stylesheet
- Map theme properties to Textual CSS variables ($primary, $secondary, $background, etc.)

**Theme Mappings:**

**Default Theme (Current):**
- Uses Textual's default dark theme
- No CSS overrides needed

**Windows XP Theme:**
- Blue title bars, silver/gray backgrounds
- XP-style blue gradients and Luna theme colors
- Silver taskbar-inspired sidebar

**Green Terminal Theme:**
- Black background (#000000)
- Green text (#00FF00 or #33FF33)
- Minimal borders, monospace feel

**Patterns to follow:**
- Textual CSS variable system (`$primary`, `$surface`, etc.)

**Test scenarios:**
- `apply_theme(app, "windows_xp")` changes app appearance
- `apply_theme(app, "green_terminal")` applies green/black colors
- Invalid theme name raises ValueError

**Verification:**
- Visual inspection shows theme change
- No errors in console during theme switch

---

### U4. Theme Picker Screen

**Goal:** Create UI for selecting themes

**Requirements:** R3

**Dependencies:** U1

**Files:**
- Create: `src/stupidex/screens/theme_picker.py`

**Approach:**
- Create `ThemePicker(Screen[str])` similar to ModelPicker
- Display theme names as options
- Return selected theme name on dismiss

**Patterns to follow:**
- `src/stupidex/screens/model_picker.py` (17 lines)
- `src/stupidex/screens/session_picker.py` (17 lines)

**Test scenarios:**
- ThemePicker shows 3 options
- Selecting a theme returns its name
- Pressing Escape returns None

**Verification:**
- Screen can be pushed and dismissed
- Returns correct theme identifier

---

### U5. Theme Command Integration

**Goal:** Add `/theme` command to command palette

**Requirements:** R3

**Dependencies:** U2, U3, U4

**Files:**
- Modify: `src/stupidex/commands/session_commands.py`
- Modify: `src/stupidex/config.py` (for theme getter/setter)

**Approach:**
- Add `/theme` to SessionCommands.COMMANDS dict
- Implement handler that:
  1. Pushes ThemePicker screen
  2. On selection, calls apply_theme()
  3. Persists to config
- Add `get_current_theme()` and `set_current_theme()` helpers to ConfigManager

**Patterns to follow:**
- `/model` command implementation in session_commands.py

**Test scenarios:**
- `/theme` appears in command palette
- Selecting theme applies it immediately
- Theme persists after app restart

**Verification:**
- Command works end-to-end
- Theme survives app restart

---

### U6. Default Theme CSS Files

**Goal:** Create dedicated CSS files for each theme

**Requirements:** R1

**Dependencies:** U1

**Files:**
- Create: `src/stupidex/themes/default.tcss`
- Create: `src/stupidex/themes/windows_xp.tcss`
- Create: `src/stupidex/themes/green_terminal.tcss`

**Approach:**
- Extract current styles from `main.tcss` and sidebar DEFAULT_CSS into theme files
- Each theme file contains complete CSS for that visual style
- Theme applier loads and applies the appropriate .tcss file

**Patterns to follow:**
- Existing `main.tcss` structure
- Sidebar `DEFAULT_CSS` format

**Test scenarios:**
- Each theme file is valid Textual CSS
- Loading a theme file produces correct styles
- All widgets are styled in each theme

**Verification:**
- CSS files parse without errors
- Visual consistency within each theme

---

### U7. App Integration and Startup

**Goal:** Wire themes into app initialization

**Requirements:** R2, R4

**Dependencies:** U2, U3

**Files:**
- Modify: `src/stupidex/app.py`

**Approach:**
- On app mount, load saved theme from config
- Call apply_theme() to restore last used theme
- Store theme name in app state for runtime access

**Patterns to follow:**
- Existing `on_mount()` method in app.py

**Test scenarios:**
- App starts with last saved theme
- Theme applies before first render
- No delay on startup from theme loading

**Verification:**
- App boots correctly with themed appearance
- Saved preference is respected

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| CSS variable conflicts between themes | Use theme-specific CSS class prefixes |
| Runtime CSS injection performance | Cache compiled CSS, only update on theme change |
| Widget inline CSS overrides themes | Move widget CSS to theme files where possible |
| Textual version compatibility | Test with current Textual version in pyproject.toml |

---

## Open Questions

### Deferred to Implementation

- Exact color values for Windows XP and Green Terminal themes: Will determine during visual testing
- Whether to support theme-specific fonts: Defer based on Textual font support
- Theme preview before applying: Not in scope, but could be added later

---

## Next Steps

1. **Execute the plan** - Use `work` skill to implement units U1-U7 in order
2. **Review the plan** - Discuss specific sections or requirements
3. **Visual design** - Define exact color palettes for XP and Terminal themes
