"""
RetailFlow POS - Application Entry Point
"""
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from app.bootstrap import bootstrap, shutdown
from app.config import settings
from presentation.windows.main_window import MainWindow
from presentation.dialogs.login_dialog import LoginDialog
from infrastructure.database.session import create_session
from infrastructure.database.models.auth import User


def main() -> int:
    """Application entry point with login flow."""
    # Bootstrap subsystems before creating QApplication
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName("RetailFlow POS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("RetailFlow")

    # Global application stylesheet
    _load_stylesheet(app)

    exit_code = 1

    try:
        # Show login dialog
        session = create_session()
        current_user = None
        session_token = ""

        try:
            login = LoginDialog(session)
            if login.exec() == LoginDialog.Accepted:
                current_user = login.get_user()
                session_token = login.get_token()
            else:
                # User cancelled login
                session.close()
                return 0
        finally:
            session.close()

        # Login successful - show main window
        window = MainWindow(current_user=current_user, session_token=session_token)
        window.show()
        exit_code = app.exec()

    except Exception as e:
        QMessageBox.critical(
            None,
            "Application Error",
            f"A critical error occurred:\n\n{str(e)}\n\n"
            "Please check the logs for details.",
        )
        traceback.print_exc()
        exit_code = 1
    finally:
        shutdown()

    return exit_code


def _load_stylesheet(app: QApplication) -> None:
    """Load the global QSS stylesheet."""
    from pathlib import Path
    style_path = Path(__file__).resolve().parent.parent / "presentation" / "styles" / "app.qss"
    if style_path.exists():
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


if __name__ == "__main__":
    sys.exit(main())