import base64
import json
import os
import re
import sys
from copy import deepcopy
from html import escape
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


# ============================================================
# GitHub configuration
# ============================================================

ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(
    dotenv_path=ENV_PATH,
    override=True,
)

OWNER = os.getenv("GH_REPO_OWNER", "").strip()
REPOSITORY = os.getenv("GH_REPO_NAME", "").strip()
GITHUB_TOKEN = os.getenv("GH_API_KEY", "").strip()

BRANCH = "main"
MANIFEST_PATH = "notecards/noteManifest.json"


# ============================================================
# New-notecard dialog
# ============================================================

class NewNotecardDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Create New Notecard")
        self.setMinimumWidth(450)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Delta Complex")

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText(
            "ADC, Delta Complex, Complex"
        )

        form_layout = QFormLayout()
        form_layout.addRow("Title:", self.title_input)
        form_layout.addRow("Tags:", self.tags_input)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.buttons.accepted.connect(
            self.validate_and_accept
        )

        self.buttons.rejected.connect(
            self.reject
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(self.buttons)

    def validate_and_accept(self) -> None:
        if not self.title():
            QMessageBox.warning(
                self,
                "Missing Title",
                "Enter a title for the new notecard.",
            )
            return

        if not self.tags():
            QMessageBox.warning(
                self,
                "Missing Tags",
                "Enter at least one tag.",
            )
            return

        self.accept()

    def title(self) -> str:
        return self.title_input.text().strip()

    def tags(self) -> list[str]:
        tags = [
            tag.strip()
            for tag in self.tags_input.text().split(",")
            if tag.strip()
        ]

        # Remove duplicate tags while preserving their order.
        return list(dict.fromkeys(tags))


# ============================================================
# Main editor
# ============================================================

class LatexEditor(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "GitHub LaTeX Notecard Editor"
        )

        self.resize(1200, 750)

        self.current_file_path: str | None = None
        self.current_file_sha: str | None = None

        self.manifest_data: list | dict | None = None
        self.manifest_sha: str | None = None

        # ----------------------------------------------------
        # Dropdown and buttons
        # ----------------------------------------------------

        self.note_selector = QComboBox()
        self.note_selector.setMinimumWidth(350)

        self.note_selector.currentIndexChanged.connect(
            self.on_note_selected
        )

        self.refresh_button = QPushButton(
            "Refresh Manifest"
        )

        self.refresh_button.clicked.connect(
            self.load_manifest
        )

        self.new_note_button = QPushButton(
            "New Notecard"
        )

        self.new_note_button.clicked.connect(
            self.open_new_notecard_dialog
        )

        self.save_button = QPushButton(
            "Save to GitHub"
        )

        self.save_button.clicked.connect(
            self.save_current_note
        )

        self.save_button.setEnabled(False)

        self.delete_button = QPushButton(
            "Delete Notecard"
        )

        self.delete_button.clicked.connect(
            self.delete_current_note
        )

        self.delete_button.setEnabled(False)

        self.delete_button.setStyleSheet(
            """
            QPushButton:enabled {
                color: #a00000;
                font-weight: bold;
            }
            """
        )

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Notecard:"))
        selector_row.addWidget(
            self.note_selector,
            1,
        )
        selector_row.addWidget(
            self.refresh_button
        )
        selector_row.addWidget(
            self.new_note_button
        )
        selector_row.addWidget(
            self.save_button
        )
        selector_row.addWidget(
            self.delete_button
        )

        # ----------------------------------------------------
        # Editor and preview
        # ----------------------------------------------------

        self.editor = QPlainTextEdit()

        self.editor.setPlaceholderText(
            "Select a notecard from the dropdown "
            "or create a new one."
        )

        self.preview = QWebEngineView()

        self.editor.setStyleSheet(
            """
            QPlainTextEdit {
                border: 1px solid #a0a0a0;
                padding: 12px;
                margin: 0;
                background: white;
                font-family: Consolas, monospace;
                font-size: 15px;
            }
            """
        )

        self.preview.setStyleSheet(
            """
            QWebEngineView {
                border: 1px solid #a0a0a0;
                margin: 0;
                padding: 0;
                background: white;
            }
            """
        )

        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(250)

        self.update_timer.timeout.connect(
            self.update_preview
        )

        self.editor.textChanged.connect(
            self.schedule_preview_update
        )

        left_panel = self.create_panel(
            "LaTeX Source",
            self.editor,
        )

        right_panel = self.create_panel(
            "Compiled Preview",
            self.preview,
        )

        splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        splitter.setSizes([600, 600])
        splitter.setChildrenCollapsible(False)

        container = QWidget()

        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addLayout(selector_row)
        layout.addWidget(splitter, 1)

        self.setCentralWidget(container)

        self.update_preview()
        self.load_manifest()

    # ========================================================
    # Configuration validation
    # ========================================================

    def validate_configuration(self) -> None:
        missing_values = []

        if not OWNER:
            missing_values.append("GH_REPO_OWNER")

        if not REPOSITORY:
            missing_values.append("GH_REPO_NAME")

        if not GITHUB_TOKEN:
            missing_values.append("GH_API_KEY")

        if missing_values:
            missing_text = ", ".join(
                missing_values
            )

            raise RuntimeError(
                "The following values are missing from "
                f"{ENV_PATH}:\n\n{missing_text}"
            )

    # ========================================================
    # UI helpers
    # ========================================================

    @staticmethod
    def create_panel(
        title: str,
        widget: QWidget,
    ) -> QWidget:
        panel = QWidget()

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(title)
        label.setFixedHeight(40)

        label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter
        )

        label.setStyleSheet(
            """
            QLabel {
                font-size: 16px;
                font-weight: bold;
                padding: 0 8px;
                margin: 0;
                border: none;
            }
            """
        )

        layout.addWidget(label)
        layout.addWidget(widget, 1)

        return panel

    def set_file_action_buttons(
        self,
        enabled: bool,
    ) -> None:
        self.save_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def clear_current_note(self) -> None:
        self.current_file_path = None
        self.current_file_sha = None

        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)

        self.update_preview()
        self.set_file_action_buttons(False)

    # ========================================================
    # GitHub helpers
    # ========================================================

    def github_headers(self) -> dict[str, str]:
        self.validate_configuration()

        return {
            "Accept": "application/vnd.github+json",
            "Authorization": (
                f"Bearer {GITHUB_TOKEN}"
            ),
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def clean_repository_path(
        repository_path: str,
    ) -> str:
        return (
            repository_path
            .removeprefix("./")
            .strip("/")
        )

    def github_contents_url(
        self,
        repository_path: str,
    ) -> str:
        clean_path = self.clean_repository_path(
            repository_path
        )

        encoded_path = quote(
            clean_path,
            safe="/",
        )

        return (
            f"https://api.github.com/repos/"
            f"{OWNER}/{REPOSITORY}/contents/"
            f"{encoded_path}"
        )

    def get_github_file(
        self,
        repository_path: str,
    ) -> dict:
        url = self.github_contents_url(
            repository_path
        )

        response = requests.get(
            url,
            headers=self.github_headers(),
            params={"ref": BRANCH},
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, list):
            raise ValueError(
                f"{repository_path} refers to a "
                "directory, not a file."
            )

        if data.get("type") != "file":
            raise ValueError(
                f"{repository_path} is not a file."
            )

        encoded_content = (
            data["content"].replace("\n", "")
        )

        decoded_content = base64.b64decode(
            encoded_content
        ).decode("utf-8")

        return {
            "name": data["name"],
            "path": data["path"],
            "sha": data["sha"],
            "content": decoded_content,
        }

    def put_github_file(
        self,
        repository_path: str,
        content: str,
        commit_message: str,
        sha: str | None = None,
    ) -> dict:
        url = self.github_contents_url(
            repository_path
        )

        payload = {
            "message": commit_message,
            "content": base64.b64encode(
                content.encode("utf-8")
            ).decode("ascii"),
            "branch": BRANCH,
        }

        if sha is not None:
            payload["sha"] = sha

        response = requests.put(
            url,
            headers=self.github_headers(),
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        return response.json()

    def delete_github_file(
        self,
        repository_path: str,
        sha: str,
        commit_message: str,
    ) -> dict:
        url = self.github_contents_url(
            repository_path
        )

        payload = {
            "message": commit_message,
            "sha": sha,
            "branch": BRANCH,
        }

        response = requests.delete(
            url,
            headers=self.github_headers(),
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        return response.json()

    def show_request_error(
        self,
        title: str,
        error: requests.HTTPError,
    ) -> None:
        response = error.response

        if response is None:
            details = str(error)

        else:
            try:
                response_data = response.json()

                message = response_data.get(
                    "message",
                    response.text,
                )

                documentation_url = (
                    response_data.get(
                        "documentation_url",
                        "",
                    )
                )

            except ValueError:
                message = response.text
                documentation_url = ""

            details = (
                f"HTTP {response.status_code}: "
                f"{message}"
            )

            if documentation_url:
                details += (
                    "\n\nDocumentation:\n"
                    f"{documentation_url}"
                )

        QMessageBox.critical(
            self,
            title,
            details,
        )

    # ========================================================
    # Manifest helpers
    # ========================================================

    def read_fresh_manifest(self) -> tuple[
        list | dict,
        str,
    ]:
        manifest_file = self.get_github_file(
            MANIFEST_PATH
        )

        manifest = json.loads(
            manifest_file["content"]
        )

        if isinstance(manifest, dict):
            notes = manifest.get("notes", [])

            if not isinstance(notes, list):
                raise ValueError(
                    "The manifest's 'notes' property "
                    "must be a list."
                )

        elif not isinstance(manifest, list):
            raise ValueError(
                "Manifest must be a JSON list or "
                "contain a 'notes' list."
            )

        return manifest, manifest_file["sha"]

    @staticmethod
    def notes_from_manifest(
        manifest: list | dict,
    ) -> list:
        if isinstance(manifest, list):
            return manifest

        if isinstance(manifest, dict):
            notes = manifest.setdefault(
                "notes",
                [],
            )

            if not isinstance(notes, list):
                raise ValueError(
                    "The manifest's 'notes' property "
                    "must be a list."
                )

            return notes

        raise ValueError(
            "Manifest must be a JSON list or object."
        )

    @staticmethod
    def format_manifest(
        manifest: list | dict,
    ) -> str:
        return json.dumps(
            manifest,
            indent=4,
            ensure_ascii=False,
        ) + "\n"

    def load_manifest(
        self,
        select_path: str | None = None,
    ) -> None:
        self.note_selector.blockSignals(True)
        self.note_selector.clear()

        self.note_selector.addItem(
            "Select a notecard...",
            None,
        )

        try:
            manifest, manifest_sha = (
                self.read_fresh_manifest()
            )

            self.manifest_data = manifest
            self.manifest_sha = manifest_sha

            notes = self.notes_from_manifest(
                manifest
            )

            selected_index = 0

            for note in notes:
                if not isinstance(note, dict):
                    continue

                repository_path = (
                    note.get("file")
                    or note.get("path")
                )

                if not repository_path:
                    continue

                repository_path = (
                    self.clean_repository_path(
                        str(repository_path)
                    )
                )

                title = (
                    note.get("title")
                    or note.get("name")
                    or Path(
                        repository_path
                    ).stem
                )

                dropdown_data = {
                    "title": str(title),
                    "slug": str(
                        note.get("slug", "")
                    ),
                    "path": repository_path,
                    "tags": note.get(
                        "tags",
                        [],
                    ),
                }

                self.note_selector.addItem(
                    str(title),
                    dropdown_data,
                )

                if (
                    select_path
                    and repository_path
                    == self.clean_repository_path(
                        select_path
                    )
                ):
                    selected_index = (
                        self.note_selector.count()
                        - 1
                    )

            self.note_selector.blockSignals(False)

            if selected_index > 0:
                self.note_selector.setCurrentIndex(
                    selected_index
                )
            else:
                self.clear_current_note()

            self.statusBar().showMessage(
                "Manifest loaded.",
                4000,
            )

        except requests.HTTPError as error:
            self.note_selector.blockSignals(False)

            self.show_request_error(
                "Could Not Load Manifest",
                error,
            )

        except (
            RuntimeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            self.note_selector.blockSignals(False)

            QMessageBox.critical(
                self,
                "Manifest Error",
                str(error),
            )

    def get_manifest_notes(self) -> list:
        if self.manifest_data is None:
            raise ValueError(
                "The manifest has not been loaded."
            )

        return self.notes_from_manifest(
            self.manifest_data
        )

    def manifest_contains_slug(
        self,
        slug: str,
    ) -> bool:
        for note in self.get_manifest_notes():
            if (
                isinstance(note, dict)
                and note.get("slug") == slug
            ):
                return True

        return False

    def manifest_contains_file(
        self,
        repository_path: str,
    ) -> bool:
        clean_path = self.clean_repository_path(
            repository_path
        )

        for note in self.get_manifest_notes():
            if not isinstance(note, dict):
                continue

            existing_path = (
                note.get("file")
                or note.get("path")
                or ""
            )

            existing_path = (
                self.clean_repository_path(
                    str(existing_path)
                )
            )

            if existing_path == clean_path:
                return True

        return False

    @staticmethod
    def remove_manifest_entry(
        manifest: list | dict,
        repository_path: str,
    ) -> dict | None:
        clean_path = (
            repository_path
            .removeprefix("./")
            .strip("/")
        )

        notes = LatexEditor.notes_from_manifest(
            manifest
        )

        for index, note in enumerate(notes):
            if not isinstance(note, dict):
                continue

            note_path = (
                note.get("file")
                or note.get("path")
                or ""
            )

            note_path = (
                str(note_path)
                .removeprefix("./")
                .strip("/")
            )

            if note_path == clean_path:
                return notes.pop(index)

        return None

    # ========================================================
    # Existing-notecard loading
    # ========================================================

    def on_note_selected(
        self,
        index: int,
    ) -> None:
        note_data = self.note_selector.itemData(
            index
        )

        if not note_data:
            self.clear_current_note()
            return

        repository_path = note_data["path"]

        try:
            note_file = self.get_github_file(
                repository_path
            )

            self.current_file_path = (
                note_file["path"]
            )

            self.current_file_sha = (
                note_file["sha"]
            )

            self.editor.blockSignals(True)

            self.editor.setPlainText(
                note_file["content"]
            )

            self.editor.blockSignals(False)

            self.update_preview()
            self.set_file_action_buttons(True)

            self.statusBar().showMessage(
                f"Loaded {self.current_file_path}",
                5000,
            )

        except requests.HTTPError as error:
            self.clear_current_note()

            self.show_request_error(
                f"Could Not Load "
                f"{repository_path}",
                error,
            )

        except (
            RuntimeError,
            ValueError,
            KeyError,
            UnicodeDecodeError,
        ) as error:
            self.clear_current_note()

            QMessageBox.critical(
                self,
                "Notecard Error",
                str(error),
            )

    # ========================================================
    # Existing-notecard saving
    # ========================================================

    def save_current_note(self) -> None:
        if (
            not self.current_file_path
            or not self.current_file_sha
        ):
            QMessageBox.warning(
                self,
                "No Notecard Selected",
                "Select a notecard before saving.",
            )
            return

        self.set_file_action_buttons(False)

        try:
            result = self.put_github_file(
                repository_path=(
                    self.current_file_path
                ),
                content=self.editor.toPlainText(),
                commit_message=(
                    f"Update "
                    f"{self.current_file_path}"
                ),
                sha=self.current_file_sha,
            )

            self.current_file_sha = (
                result["content"]["sha"]
            )

            self.statusBar().showMessage(
                f"Saved "
                f"{self.current_file_path}",
                5000,
            )

            QMessageBox.information(
                self,
                "Notecard Saved",
                (
                    f"{self.current_file_path} "
                    "was updated on GitHub."
                ),
            )

        except requests.HTTPError as error:
            if (
                error.response is not None
                and error.response.status_code
                in {409, 422}
            ):
                QMessageBox.warning(
                    self,
                    "File Changed",
                    (
                        "The file may have changed "
                        "on GitHub. Refresh the "
                        "manifest and reload the "
                        "notecard before saving."
                    ),
                )

            else:
                self.show_request_error(
                    "Could Not Save Notecard",
                    error,
                )

        except RuntimeError as error:
            QMessageBox.critical(
                self,
                "Configuration Error",
                str(error),
            )

        except KeyError:
            QMessageBox.critical(
                self,
                "Unexpected Response",
                (
                    "GitHub did not return the "
                    "updated file SHA."
                ),
            )

        finally:
            if self.current_file_path:
                self.set_file_action_buttons(
                    True
                )

    # ========================================================
    # Notecard deletion
    # ========================================================

    def delete_current_note(self) -> None:
        note_data = self.note_selector.currentData()

        if (
            not note_data
            or not self.current_file_path
            or not self.current_file_sha
        ):
            QMessageBox.warning(
                self,
                "No Notecard Selected",
                "Select a notecard before deleting.",
            )
            return

        title = note_data.get(
            "title",
            Path(self.current_file_path).stem,
        )

        tags = note_data.get("tags", [])

        if isinstance(tags, list):
            tags_text = ", ".join(
                str(tag)
                for tag in tags
            )
        else:
            tags_text = str(tags)

        confirmation = QMessageBox.warning(
            self,
            "Delete Notecard",
            (
                "This will permanently delete the "
                "notecard file from GitHub and remove "
                "its entry from the manifest.\n\n"
                f"Title: {title}\n"
                f"File: {self.current_file_path}\n"
                f"Tags: {tags_text or 'None'}\n\n"
                "This action creates GitHub commits "
                "and cannot be undone from this app."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if (
            confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        second_confirmation = QMessageBox.question(
            self,
            "Confirm Permanent Deletion",
            (
                f'Permanently delete "{title}"?'
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if (
            second_confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        self.refresh_button.setEnabled(False)
        self.new_note_button.setEnabled(False)
        self.set_file_action_buttons(False)

        deleted_file = False
        rollback_succeeded = False

        original_file_content = ""
        original_file_path = (
            self.current_file_path
        )

        try:
            # Retrieve fresh versions so the deletion does not
            # use stale file or manifest SHAs.
            fresh_file = self.get_github_file(
                original_file_path
            )

            fresh_manifest, fresh_manifest_sha = (
                self.read_fresh_manifest()
            )

            original_file_content = (
                fresh_file["content"]
            )

            updated_manifest = deepcopy(
                fresh_manifest
            )

            removed_entry = (
                self.remove_manifest_entry(
                    updated_manifest,
                    original_file_path,
                )
            )

            if removed_entry is None:
                raise ValueError(
                    "The selected notecard was not "
                    "found in the current manifest. "
                    "No files were deleted."
                )

            # First commit: delete the notecard file.
            self.delete_github_file(
                repository_path=original_file_path,
                sha=fresh_file["sha"],
                commit_message=(
                    f"Delete notecard: {title}"
                ),
            )

            deleted_file = True

            # Second commit: remove its manifest entry.
            manifest_result = self.put_github_file(
                repository_path=MANIFEST_PATH,
                content=self.format_manifest(
                    updated_manifest
                ),
                commit_message=(
                    f"Remove {title} from "
                    "notecard manifest"
                ),
                sha=fresh_manifest_sha,
            )

            self.manifest_data = updated_manifest
            self.manifest_sha = (
                manifest_result["content"]["sha"]
            )

            self.clear_current_note()
            self.load_manifest()

            self.statusBar().showMessage(
                f"Deleted {original_file_path}",
                5000,
            )

            QMessageBox.information(
                self,
                "Notecard Deleted",
                (
                    f'"{title}" was deleted from '
                    "GitHub and removed from the "
                    "manifest."
                ),
            )

        except requests.HTTPError as error:
            # If the file deletion succeeded but the manifest
            # update failed, attempt to recreate the file.
            if (
                deleted_file
                and original_file_content
            ):
                try:
                    self.put_github_file(
                        repository_path=(
                            original_file_path
                        ),
                        content=(
                            original_file_content
                        ),
                        commit_message=(
                            "Restore notecard after "
                            "manifest update failure: "
                            f"{title}"
                        ),
                    )

                    rollback_succeeded = True

                except (
                    requests.HTTPError,
                    RuntimeError,
                ):
                    rollback_succeeded = False

            self.load_manifest(
                select_path=original_file_path
            )

            if deleted_file:
                if rollback_succeeded:
                    QMessageBox.warning(
                        self,
                        "Deletion Rolled Back",
                        (
                            "The notecard file was "
                            "temporarily deleted, but "
                            "the manifest update failed.\n\n"
                            "The app successfully restored "
                            "the notecard file. The manifest "
                            "was not changed."
                        ),
                    )

                else:
                    QMessageBox.critical(
                        self,
                        "Partial Deletion",
                        (
                            "The notecard file was deleted, "
                            "but updating the manifest failed, "
                            "and the app could not restore the "
                            "file.\n\n"
                            "The manifest may still contain "
                            "an entry for a missing file."
                        ),
                    )

            else:
                self.show_request_error(
                    "Could Not Delete Notecard",
                    error,
                )

        except (
            RuntimeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            self.load_manifest(
                select_path=original_file_path
            )

            QMessageBox.critical(
                self,
                "Deletion Error",
                str(error),
            )

        finally:
            self.refresh_button.setEnabled(True)
            self.new_note_button.setEnabled(True)

            if self.current_file_path:
                self.set_file_action_buttons(
                    True
                )

    # ========================================================
    # New-notecard creation
    # ========================================================

    @staticmethod
    def make_slug(title: str) -> str:
        normalized = title.strip().lower()

        normalized = re.sub(
            r"[^a-z0-9]+",
            "_",
            normalized,
        )

        return normalized.strip("_")

    @staticmethod
    def make_filename(title: str) -> str:
        normalized = title.strip().lower()

        filename = re.sub(
            r"[^a-z0-9]+",
            "",
            normalized,
        )

        return f"{filename}.html"

    def open_new_notecard_dialog(self) -> None:
        if (
            self.manifest_data is None
            or self.manifest_sha is None
        ):
            QMessageBox.warning(
                self,
                "Manifest Not Loaded",
                (
                    "Load the manifest before "
                    "creating a notecard."
                ),
            )
            return

        dialog = NewNotecardDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        title = dialog.title()
        tags = dialog.tags()

        slug = self.make_slug(title)
        filename = self.make_filename(title)

        if not slug or filename == ".html":
            QMessageBox.warning(
                self,
                "Invalid Title",
                (
                    "The title must contain "
                    "letters or numbers."
                ),
            )
            return

        repository_path = (
            f"notecards/{filename}"
        )

        manifest_file_path = (
            f"./{repository_path}"
        )

        try:
            # Refresh before testing for duplicates.
            fresh_manifest, fresh_manifest_sha = (
                self.read_fresh_manifest()
            )

            self.manifest_data = fresh_manifest
            self.manifest_sha = fresh_manifest_sha

            if self.manifest_contains_slug(slug):
                QMessageBox.warning(
                    self,
                    "Duplicate Slug",
                    (
                        "A notecard already uses "
                        f'the slug "{slug}".'
                    ),
                )
                return

            if self.manifest_contains_file(
                repository_path
            ):
                QMessageBox.warning(
                    self,
                    "Duplicate File",
                    (
                        f"{repository_path} already "
                        "appears in the manifest."
                    ),
                )
                return

        except (
            requests.HTTPError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            if isinstance(
                error,
                requests.HTTPError,
            ):
                self.show_request_error(
                    "Could Not Refresh Manifest",
                    error,
                )
            else:
                QMessageBox.critical(
                    self,
                    "Manifest Error",
                    str(error),
                )

            return

        new_entry = {
            "title": title,
            "slug": slug,
            "file": manifest_file_path,
            "tags": tags,
        }

        default_content = (
            self.create_default_notecard_html(
                title=title,
                tags=tags,
            )
        )

        confirmation = QMessageBox.question(
            self,
            "Create Notecard",
            (
                "Create the following notecard?\n\n"
                f"Title: {title}\n"
                f"Slug: {slug}\n"
                f"File: {manifest_file_path}\n"
                f"Tags: {', '.join(tags)}"
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )

        if (
            confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        self.create_notecard_and_update_manifest(
            entry=new_entry,
            repository_path=repository_path,
            initial_content=default_content,
        )

    @staticmethod
    def create_default_notecard_html(
        title: str,
        tags: list[str],
    ) -> str:
        escaped_title = escape(title)

        escaped_tags = ", ".join(
            escape(tag)
            for tag in tags
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>{escaped_title}</title>

    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [
                    ['\\\\(', '\\\\)'],
                    ['$', '$']
                ],
                displayMath: [
                    ['\\\\[', '\\\\]'],
                    ['$$', '$$']
                ],
                processEscapes: true
            }}
        }};
    </script>

    <script
        defer
        src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"
    ></script>
</head>

<body>
    <article class="notecard">
        <h1>{escaped_title}</h1>

        <p class="tags">
            {escaped_tags}
        </p>

        <div class="notecard-content">
            <p>Enter the notecard content here.</p>

            \\[
                E = mc^2
            \\]
        </div>
    </article>
</body>
</html>
"""

    def create_notecard_and_update_manifest(
        self,
        entry: dict,
        repository_path: str,
        initial_content: str,
    ) -> None:
        self.refresh_button.setEnabled(False)
        self.new_note_button.setEnabled(False)
        self.set_file_action_buttons(False)

        card_created = False
        rollback_succeeded = False

        try:
            fresh_manifest, fresh_manifest_sha = (
                self.read_fresh_manifest()
            )

            updated_manifest = deepcopy(
                fresh_manifest
            )

            notes = self.notes_from_manifest(
                updated_manifest
            )

            notes.append(entry)

            # First commit: create the new notecard.
            self.put_github_file(
                repository_path=repository_path,
                content=initial_content,
                commit_message=(
                    f"Create notecard: "
                    f"{entry['title']}"
                ),
            )

            card_created = True

            # Second commit: add it to the manifest.
            manifest_result = self.put_github_file(
                repository_path=MANIFEST_PATH,
                content=self.format_manifest(
                    updated_manifest
                ),
                commit_message=(
                    f"Add {entry['title']} "
                    "to notecard manifest"
                ),
                sha=fresh_manifest_sha,
            )

            self.manifest_data = updated_manifest
            self.manifest_sha = (
                manifest_result["content"]["sha"]
            )

            self.statusBar().showMessage(
                f"Created {repository_path}",
                5000,
            )

            QMessageBox.information(
                self,
                "Notecard Created",
                (
                    f"{entry['title']} was created "
                    "successfully.\n\n"
                    f"File: {repository_path}\n"
                    f"Manifest: {MANIFEST_PATH}"
                ),
            )

            self.load_manifest(
                select_path=repository_path
            )

        except requests.HTTPError as error:
            # If the card was created but the manifest update
            # failed, attempt to delete the newly-created card.
            if card_created:
                try:
                    created_file = (
                        self.get_github_file(
                            repository_path
                        )
                    )

                    self.delete_github_file(
                        repository_path=(
                            repository_path
                        ),
                        sha=created_file["sha"],
                        commit_message=(
                            "Remove incomplete "
                            "notecard creation: "
                            f"{entry['title']}"
                        ),
                    )

                    rollback_succeeded = True

                except (
                    requests.HTTPError,
                    RuntimeError,
                    ValueError,
                    KeyError,
                ):
                    rollback_succeeded = False

            self.load_manifest()

            if card_created:
                if rollback_succeeded:
                    QMessageBox.warning(
                        self,
                        "Creation Rolled Back",
                        (
                            "The notecard file was "
                            "created, but the manifest "
                            "update failed.\n\n"
                            "The app successfully deleted "
                            "the incomplete notecard file."
                        ),
                    )

                else:
                    QMessageBox.critical(
                        self,
                        "Partial Creation",
                        (
                            "The notecard file was created, "
                            "but the manifest update failed, "
                            "and the app could not delete the "
                            "new file.\n\n"
                            "The repository may contain an "
                            "unlisted notecard."
                        ),
                    )

            else:
                self.show_request_error(
                    "Could Not Create Notecard",
                    error,
                )

        except (
            RuntimeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            self.load_manifest()

            QMessageBox.critical(
                self,
                "Creation Error",
                str(error),
            )

        finally:
            self.refresh_button.setEnabled(True)
            self.new_note_button.setEnabled(True)

            if self.current_file_path:
                self.set_file_action_buttons(
                    True
                )

    # ========================================================
    # Live preview
    # ========================================================

    def schedule_preview_update(self) -> None:
        self.update_timer.start()

    def update_preview(self) -> None:
        latex_source = self.editor.toPlainText()
        safe_source = escape(latex_source)

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">

    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [
                    ['\\\\(', '\\\\)'],
                    ['$', '$']
                ],
                displayMath: [
                    ['\\\\[', '\\\\]'],
                    ['$$', '$$']
                ],
                processEscapes: true,
                packages: {{
                    '[+]': ['ams']
                }}
            }},
            loader: {{
                load: ['[tex]/ams']
            }}
        }};
    </script>

    <script
        defer
        src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"
    ></script>

    <style>
        html,
        body {{
            margin: 0;
            padding: 0;
            width: 100%;
            min-height: 100%;
            background: white;
            color: #202020;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px;
            line-height: 1.6;
        }}

        #content {{
            box-sizing: border-box;
            margin: 0;
            padding: 12px;
            width: 100%;
            min-height: 100vh;
        }}

        h1,
        h2,
        h3 {{
            margin-top: 1.2em;
            margin-bottom: 0.5em;
        }}

        ul,
        ol {{
            margin-left: 1.5em;
        }}

        mjx-container[display="true"] {{
            overflow-x: auto;
            overflow-y: hidden;
            padding: 8px 0;
        }}
    </style>
</head>

<body>
    <div id="content"></div>

    <script>
        const source = `{self.javascript_string(safe_source)}`;

        function convertBasicLatex(text) {{
            let output = text;

            output = output.replace(
                /\\\\section\\*?\\{{(.*?)\\}}/g,
                "<h1>$1</h1>"
            );

            output = output.replace(
                /\\\\subsection\\*?\\{{(.*?)\\}}/g,
                "<h2>$1</h2>"
            );

            output = output.replace(
                /\\\\subsubsection\\*?\\{{(.*?)\\}}/g,
                "<h3>$1</h3>"
            );

            output = output.replace(
                /\\\\textbf\\{{(.*?)\\}}/g,
                "<strong>$1</strong>"
            );

            output = output.replace(
                /\\\\textit\\{{(.*?)\\}}/g,
                "<em>$1</em>"
            );

            output = output.replace(
                /\\\\begin\\{{itemize\\}}([\\s\\S]*?)\\\\end\\{{itemize\\}}/g,
                function(match, body) {{
                    const items = body
                        .split(/\\\\item/)
                        .slice(1)
                        .map(
                            item =>
                                "<li>" +
                                item.trim() +
                                "</li>"
                        )
                        .join("");

                    return "<ul>" + items + "</ul>";
                }}
            );

            output = output.replace(
                /\\\\begin\\{{enumerate\\}}([\\s\\S]*?)\\\\end\\{{enumerate\\}}/g,
                function(match, body) {{
                    const items = body
                        .split(/\\\\item/)
                        .slice(1)
                        .map(
                            item =>
                                "<li>" +
                                item.trim() +
                                "</li>"
                        )
                        .join("");

                    return "<ol>" + items + "</ol>";
                }}
            );

            const protectedBlocks = [];

            output = output.replace(
                /(\\\\\\[[\\s\\S]*?\\\\\\]|\\$\\$[\\s\\S]*?\\$\\$)/g,
                function(block) {{
                    const index =
                        protectedBlocks.length;

                    protectedBlocks.push(block);

                    return (
                        "MATHBLOCK_" +
                        index +
                        "_PLACEHOLDER"
                    );
                }}
            );

            output = output
                .split(/\\n\\s*\\n/)
                .map(block => {{
                    const trimmed = block.trim();

                    if (
                        trimmed.startsWith("<h") ||
                        trimmed.startsWith("<ul") ||
                        trimmed.startsWith("<ol") ||
                        trimmed.startsWith(
                            "MATHBLOCK_"
                        )
                    ) {{
                        return trimmed;
                    }}

                    if (!trimmed) {{
                        return "";
                    }}

                    return (
                        "<p>" +
                        trimmed.replace(
                            /\\n/g,
                            "<br>"
                        ) +
                        "</p>"
                    );
                }})
                .join("\\n");

            protectedBlocks.forEach(
                function(block, index) {{
                    output = output.replace(
                        "MATHBLOCK_" +
                        index +
                        "_PLACEHOLDER",
                        block
                    );
                }}
            );

            return output;
        }}

        document.getElementById(
            "content"
        ).innerHTML = convertBasicLatex(source);
    </script>
</body>
</html>
"""

        self.preview.setHtml(html)

    @staticmethod
    def javascript_string(
        value: str,
    ) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("\r", "")
            .replace("\n", "\\n")
        )


# ============================================================
# Start application
# ============================================================

def main() -> None:
    app = QApplication(sys.argv)

    window = LatexEditor()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()