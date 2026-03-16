"""Inline CSS for the TUI app."""

APP_CSS = """
Screen {
    background: $surface;
}

Input {
    background: $surface-lighten-2;
    height: 1;
    border: none;
    padding: 0 1;
}

Input:focus {
    background: $surface-lighten-3;
    border: none;
}

#install-status {
    dock: bottom;
    margin-top: 1;
    color: $text-muted;
}

#main-layout {
    height: 1fr;
}

#menu-panel {
    width: 14;
    height: 1fr;
    margin: 0 1 0 2;
}

.menu-section-label {
    color: $text-muted;
    margin-top: 1;
}

.menu-btn {
    width: 1fr;
    margin: 0;
    height: 1;
    background: $surface-lighten-1;
    color: $text;
    padding: 0 1;
    text-align: left;
}

.menu-btn:hover {
    background: $primary-darken-1;
}

.menu-btn:focus {
    background: $primary-darken-2;
    text-style: bold;
}

#status-panel {
    height: 1fr;
    margin: 0 2 0 1;
}

#status-panel DataTable {
    height: 1fr;
    border: solid $primary;
}

AddMountScreen VerticalScroll {
    height: 1fr;
    margin: 0 2;
    padding: 0 8 1 8;
}

SettingsScreen VerticalScroll {
    height: 1fr;
    margin: 0 2;
    padding: 0 8 1 8;
}

.field-label {
    margin-top: 1;
    margin-bottom: 0;
    color: $text-muted;
}

.healthcheck-group {
    height: auto;
    padding-left: 2;
    border-left: solid $primary-darken-2;
    margin-top: 1;
}

.buttons {
    height: 1;
    align: center middle;
    margin-top: 1;
}

.buttons Button {
    margin: 0 1;
    height: 1;
    border: none;
    min-width: 0;
}

Switch {
    height: 1;
    margin: 0;
    border: none;
    background: transparent;
}

MountSelectorScreen > Vertical {
    border: solid $primary;
    margin: 2 4;
    height: auto;
    max-height: 80%;
    padding: 1 2;
    background: $surface;
}

MountSelectorScreen DataTable {
    height: auto;
    max-height: 20;
}

#selector-hint {
    color: $text-muted;
    margin-top: 1;
}

RemoveConfirmScreen > Vertical {
    border: solid $error;
    margin: 4 8;
    height: auto;
    padding: 2;
    background: $surface;
}



.clone-banner {
    background: $primary-darken-2;
    padding: 0 1;
    margin: 0 0 1 0;
}

.ssh-test-result {
    height: 1;
    margin: 0 2;
}

.inline-buttons {
    height: 1;
    margin-top: 1;
}

.inline-buttons Button {
    margin: 0 1 0 0;
    height: 1;
    border: none;
    min-width: 0;
}

InstallScreen #install-header {
    margin: 0 2 1 2;
}

InstallScreen .install-path-label {
    margin: 0 2;
}

InstallScreen Input {
    margin: 0 2;
}

InstallScreen Log {
    height: 1fr;
    margin: 1 2 0 2;
    border: solid $primary;
}

LogViewerScreen #log-title {
    margin: 0 2;
    color: $text-muted;
}

LogViewerScreen Log {
    height: 1fr;
    margin: 0 2;
    border: solid $primary;
}

RemotePathBrowserScreen > Vertical {
    border: solid $primary;
    margin: 2 4;
    height: 80%;
    padding: 1 2;
    background: $surface;
}

RemotePathBrowserScreen DataTable {
    height: 1fr;
}

#browser-path {
    margin-bottom: 1;
}

#browser-status {
    color: $text-muted;
    margin-top: 1;
}
"""
