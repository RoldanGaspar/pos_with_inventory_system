"""
RetailFlow POS - Store Settings Application Service
Coordinates store profile management, receipt preference configuration,
managed logo lifecycle, system diagnostic information, and atomic audit logging.
"""

import json
import logging
import os
import platform
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import PIL.Image
import PySide6
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import ReceiptWidth
from application.dto.settings_dto import (
    StoreSettingsDTO,
    SystemInfoDTO,
    UpdateReceiptPreferencesDTO,
    UpdateStoreProfileDTO,
)
from domain.exceptions import (
    AccountInactiveError,
    AuthorizationError,
    ConfigurationError,
    ValidationError,
)
from infrastructure.database.models.auth import User
from infrastructure.database.models.settings import StoreSettings
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.settings")

# Validation Constraints
MIN_STORE_NAME_LEN = 2
MAX_STORE_NAME_LEN = 100
MAX_STORE_ADDRESS_LEN = 255
MAX_CONTACT_NUMBER_LEN = 50
MAX_EMAIL_LEN = 100
MAX_TIN_LEN = 50
MAX_RECEIPT_HEADER_LEN = 255
MAX_RECEIPT_FOOTER_LEN = 500

DEFAULT_RECEIPT_HEADER = "Official Sales Invoice / Thermal Receipt"
DEFAULT_RECEIPT_FOOTER = "Thank you for shopping with us!"

# Logo Constraints
MAX_LOGO_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
MIN_LOGO_DIMENSION_PX = 16
MAX_LOGO_DIMENSION_PX = 2048
MAX_LOGO_TOTAL_PIXELS = 2048 * 2048
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Regex
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SettingsService:
    """Application service for managing store profile, receipt templates, and diagnostics."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)
        self._assets_dir = settings.data_dir / "assets"

    # ─── 1. Read Operations ───

    def get_settings(self, actor: Optional[User] = None) -> StoreSettingsDTO:
        """
        Retrieve current store settings snapshot.
        Requires 'view_settings' permission.
        Read-only: raises ConfigurationError if canonical row (id=1) is missing without auto-creating.
        """
        self._check_actor_permission(actor, "view_settings")

        record = self._session.query(StoreSettings).filter_by(id=1).first()
        if record is None:
            raise ConfigurationError(
                "Store settings record (id=1) is missing from database. Bootstrap seeding required."
            )

        return self._to_dto(record)

    def get_system_info(self, actor: Optional[User] = None) -> SystemInfoDTO:
        """
        Retrieve sanitized runtime diagnostic and environment metadata.
        Requires 'view_settings' permission.
        Strictly redacts credentials, passwords, and sensitive keys.
        """
        self._check_actor_permission(actor, "view_settings")

        # Sanitize database location / connection info
        sanitized_db_location = self._sanitize_database_location()

        return SystemInfoDTO(
            app_name=settings.app_name,
            app_version=settings.app_version,
            app_env=settings.app_env,
            database_type=settings.database_type,
            database_location=sanitized_db_location,
            timezone="Asia/Manila (UTC+08:00)",
            currency="Philippine Peso (PHP · ₱)",
            python_version=platform.python_version(),
            pyside_version=PySide6.__version__,
            os_platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
            data_dir=self._display_path(settings.data_dir, is_dir=True),
            log_dir=self._display_path(settings.log_dir, is_dir=True),
            backup_dir=self._display_path(settings.backup_dir, is_dir=True),
            export_dir=self._display_path(settings.export_dir, is_dir=True),
        )

    # ─── 2. Store Profile Update ───

    def update_store_profile(
        self,
        dto: UpdateStoreProfileDTO,
        actor: Optional[User] = None,
    ) -> StoreSettingsDTO:
        """
        Update store profile information atomically.
        Requires 'edit_settings' permission.
        Enforces validation, no-op prevention, and structured AuditLog.
        """
        authenticated_actor = self._check_actor_permission(actor, "edit_settings")

        # Normalize and validate inputs
        norm_name = self._validate_and_normalize_store_name(dto.store_name)
        norm_address = self._validate_and_normalize_optional_text(
            dto.store_address, MAX_STORE_ADDRESS_LEN, "store_address"
        )
        norm_contact = self._validate_and_normalize_optional_text(
            dto.contact_number, MAX_CONTACT_NUMBER_LEN, "contact_number"
        )
        norm_email = self._validate_and_normalize_email(dto.email)
        norm_tin = self._validate_and_normalize_optional_text(dto.tin, MAX_TIN_LEN, "tin")

        record = self._session.query(StoreSettings).filter_by(id=1).first()
        if record is None:
            raise ConfigurationError("Store settings record (id=1) is missing from database.")

        # Check for No-op Save
        if (
            record.store_name == norm_name
            and record.store_address == norm_address
            and record.contact_number == norm_contact
            and record.email == norm_email
            and record.tin == norm_tin
        ):
            logger.info("Store profile update is a no-op; skipping SQL UPDATE and AuditLog.")
            return self._to_dto(record)

        # Capture old snapshot for audit trail
        old_snapshot = {
            "store_name": record.store_name,
            "store_address": record.store_address,
            "contact_number": record.contact_number,
            "email": record.email,
            "tin": record.tin,
        }

        # Apply mutations
        record.store_name = norm_name
        record.store_address = norm_address
        record.contact_number = norm_contact
        record.email = norm_email
        record.tin = norm_tin
        record.updated_by_id = authenticated_actor.id

        new_snapshot = {
            "store_name": norm_name,
            "store_address": norm_address,
            "contact_number": norm_contact,
            "email": norm_email,
            "tin": norm_tin,
        }

        try:
            # Audit log entry within same atomic transaction
            self._audit_repo.log_action(
                user_id=authenticated_actor.id,
                username=authenticated_actor.username,
                action="STORE_PROFILE_UPDATED",
                module="settings",
                record_type="store_settings",
                record_id=1,
                previous_value=json.dumps(old_snapshot),
                new_value=json.dumps(new_snapshot),
            )
            self._session.commit()
            self._session.refresh(record)
            logger.info(f"Store profile updated successfully by {authenticated_actor.username}.")
            return self._to_dto(record)

        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to update store profile: {e}")
            raise

    # ─── 3. Receipt Preferences Update ───

    def update_receipt_preferences(
        self,
        dto: UpdateReceiptPreferencesDTO,
        actor: Optional[User] = None,
    ) -> StoreSettingsDTO:
        """
        Update receipt formatting and display preferences atomically.
        Requires 'edit_settings' permission.
        Enforces validation, no-op prevention, and structured AuditLog.
        """
        authenticated_actor = self._check_actor_permission(actor, "edit_settings")

        # Normalize and validate inputs
        norm_header = self._validate_and_normalize_receipt_header(dto.receipt_header)
        norm_footer = self._validate_and_normalize_receipt_footer(dto.receipt_footer)
        norm_width = self._validate_and_normalize_paper_width(dto.paper_width)

        # Validate boolean strictness
        for flag_name, flag_val in [
            ("show_store_address", dto.show_store_address),
            ("show_contact", dto.show_contact),
            ("show_tin", dto.show_tin),
            ("show_tax_details", dto.show_tax_details),
        ]:
            if not isinstance(flag_val, bool):
                raise ValidationError(f"Preference '{flag_name}' must be a boolean (True/False).")

        record = self._session.query(StoreSettings).filter_by(id=1).first()
        if record is None:
            raise ConfigurationError("Store settings record (id=1) is missing from database.")

        # Check for No-op Save
        if (
            record.receipt_header == norm_header
            and record.receipt_footer == norm_footer
            and record.paper_width == norm_width
            and record.show_store_address == dto.show_store_address
            and record.show_contact == dto.show_contact
            and record.show_tin == dto.show_tin
            and record.show_tax_details == dto.show_tax_details
        ):
            logger.info("Receipt preferences update is a no-op; skipping SQL UPDATE and AuditLog.")
            return self._to_dto(record)

        old_snapshot = {
            "receipt_header": record.receipt_header,
            "receipt_footer": record.receipt_footer,
            "paper_width": record.paper_width,
            "show_store_address": record.show_store_address,
            "show_contact": record.show_contact,
            "show_tin": record.show_tin,
            "show_tax_details": record.show_tax_details,
        }

        # Apply mutations
        record.receipt_header = norm_header
        record.receipt_footer = norm_footer
        record.paper_width = norm_width
        record.show_store_address = dto.show_store_address
        record.show_contact = dto.show_contact
        record.show_tin = dto.show_tin
        record.show_tax_details = dto.show_tax_details
        record.updated_by_id = authenticated_actor.id

        new_snapshot = {
            "receipt_header": norm_header,
            "receipt_footer": norm_footer,
            "paper_width": norm_width,
            "show_store_address": dto.show_store_address,
            "show_contact": dto.show_contact,
            "show_tin": dto.show_tin,
            "show_tax_details": dto.show_tax_details,
        }

        try:
            self._audit_repo.log_action(
                user_id=authenticated_actor.id,
                username=authenticated_actor.username,
                action="RECEIPT_PREFERENCES_UPDATED",
                module="settings",
                record_type="store_settings",
                record_id=1,
                previous_value=json.dumps(old_snapshot),
                new_value=json.dumps(new_snapshot),
            )
            self._session.commit()
            self._session.refresh(record)
            logger.info(f"Receipt preferences updated successfully by {authenticated_actor.username}.")
            return self._to_dto(record)

        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to update receipt preferences: {e}")
            raise

    # ─── 4. Managed Logo Lifecycle ───

    def update_store_logo(
        self,
        source_path: str | Path,
        actor: Optional[User] = None,
    ) -> StoreSettingsDTO:
        """
        Upload, validate, normalize, and atomically assign a managed store logo.
        Requires 'edit_settings' permission.
        Validates PNG/JPEG, size <= 2MB, dimensions between 16x16 and 2048x2048.
        Persists a unique versioned relative path ('assets/store_logo_<uuid>.png').
        """
        authenticated_actor = self._check_actor_permission(actor, "edit_settings")

        src_path = Path(source_path).resolve()
        if not src_path.exists() or not src_path.is_file():
            raise ValidationError(f"Logo source file not found: {source_path}")

        # Check extension
        ext = src_path.suffix.lower()
        if ext not in ALLOWED_LOGO_EXTENSIONS:
            raise ValidationError(
                f"Unsupported logo format '{ext}'. Only PNG and JPEG images are supported."
            )

        # Check file size limit
        file_size = src_path.stat().st_size
        if file_size > MAX_LOGO_FILE_SIZE_BYTES:
            raise ValidationError(
                f"Logo file size ({file_size / (1024*1024):.2f} MB) exceeds maximum allowed size of 2 MB."
            )

        # Decode and validate image contents using Pillow
        try:
            with PIL.Image.open(src_path) as img:
                img_format = (img.format or "").upper()
                if img_format not in {"PNG", "JPEG"}:
                    raise ValidationError(
                        f"Image contents identified as '{img_format}'. Only PNG and JPEG images are supported."
                    )

                width, height = img.size
                if width < MIN_LOGO_DIMENSION_PX or height < MIN_LOGO_DIMENSION_PX:
                    raise ValidationError(
                        f"Logo dimensions ({width}x{height}px) are too small. Minimum is {MIN_LOGO_DIMENSION_PX}x{MIN_LOGO_DIMENSION_PX}px."
                    )
                if width > MAX_LOGO_DIMENSION_PX or height > MAX_LOGO_DIMENSION_PX:
                    raise ValidationError(
                        f"Logo dimensions ({width}x{height}px) exceed maximum limit of {MAX_LOGO_DIMENSION_PX}x{MAX_LOGO_DIMENSION_PX}px."
                    )
                if (width * height) > MAX_LOGO_TOTAL_PIXELS:
                    raise ValidationError("Decoded pixel count exceeds maximum allowable memory limit.")

                # Convert to RGBA for clean PNG rasterization
                normalized_img = img.convert("RGBA")

        except ValidationError:
            raise
        except Exception as e:
            logger.warning(f"Image decode failed for '{source_path}': {e}")
            raise ValidationError(f"Invalid or corrupted image file: {e}") from e

        # Ensure managed assets storage exists
        self._assets_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique versioned managed filename
        unique_token = uuid.uuid4().hex[:12]
        managed_filename = f"store_logo_{unique_token}.png"
        relative_managed_path = f"assets/{managed_filename}"
        final_managed_path = self._assets_dir / managed_filename
        tmp_staging_path = self._assets_dir / f"tmp_{managed_filename}"

        # Write normalized image to staging file
        try:
            normalized_img.save(tmp_staging_path, format="PNG", optimize=True)
            # Atomically promote staging file to final destination
            os.replace(tmp_staging_path, final_managed_path)
        except Exception as e:
            if tmp_staging_path.exists():
                tmp_staging_path.unlink(missing_ok=True)
            raise ValidationError(f"Failed to process and store managed logo: {e}") from e

        record = self._session.query(StoreSettings).filter_by(id=1).first()
        if record is None:
            final_managed_path.unlink(missing_ok=True)
            raise ConfigurationError("Store settings record (id=1) is missing from database.")

        old_logo_path = record.logo_path

        # Update database record
        record.logo_path = relative_managed_path
        record.updated_by_id = authenticated_actor.id

        try:
            self._audit_repo.log_action(
                user_id=authenticated_actor.id,
                username=authenticated_actor.username,
                action="STORE_PROFILE_UPDATED",
                module="settings",
                record_type="store_settings",
                record_id=1,
                previous_value=json.dumps({"logo_path": old_logo_path}),
                new_value=json.dumps({"logo_path": relative_managed_path}),
            )
            self._session.commit()
            self._session.refresh(record)
            logger.info(f"Store logo updated to '{relative_managed_path}' by {authenticated_actor.username}.")

            # Clean up old managed logo file best-effort after successful commit
            if old_logo_path:
                self._safe_delete_managed_asset(old_logo_path)

            return self._to_dto(record)

        except Exception as e:
            self._session.rollback()
            # Clean up new orphaned managed file best-effort if DB commit failed
            final_managed_path.unlink(missing_ok=True)
            logger.error(f"Failed to persist store logo update in database: {e}")
            raise

    def remove_store_logo(self, actor: Optional[User] = None) -> StoreSettingsDTO:
        """
        Remove the active store logo from settings and delete managed file.
        Requires 'edit_settings' permission.
        Idempotent: no-op if no logo is currently configured.
        """
        authenticated_actor = self._check_actor_permission(actor, "edit_settings")

        record = self._session.query(StoreSettings).filter_by(id=1).first()
        if record is None:
            raise ConfigurationError("Store settings record (id=1) is missing from database.")

        if record.logo_path is None:
            logger.info("No store logo currently configured; remove_store_logo is a no-op.")
            return self._to_dto(record)

        old_logo_path = record.logo_path

        # Clear database path
        record.logo_path = None
        record.updated_by_id = authenticated_actor.id

        try:
            self._audit_repo.log_action(
                user_id=authenticated_actor.id,
                username=authenticated_actor.username,
                action="STORE_PROFILE_UPDATED",
                module="settings",
                record_type="store_settings",
                record_id=1,
                previous_value=json.dumps({"logo_path": old_logo_path}),
                new_value=json.dumps({"logo_path": None}),
            )
            self._session.commit()
            self._session.refresh(record)
            logger.info(f"Store logo removed successfully by {authenticated_actor.username}.")

            # Clean up physical file best-effort after commit
            self._safe_delete_managed_asset(old_logo_path)

            return self._to_dto(record)

        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to remove store logo: {e}")
            raise

    # ─── 5. Helper & Security Methods ───

    def _check_actor_permission(self, actor: Optional[User], permission: str) -> User:
        """Enforce active authentication and role permission."""
        if actor is None:
            raise AuthorizationError("Authentication required to access settings.")
        if not actor.is_active:
            raise AccountInactiveError("User account has been deactivated.")
        if not (actor.is_admin() or actor.has_permission(permission)):
            raise AuthorizationError(
                f"User '{actor.username}' does not have permission '{permission}'."
            )
        return actor

    def _validate_and_normalize_store_name(self, name: str) -> str:
        if not name or not isinstance(name, str):
            raise ValidationError("Store name is required.")
        trimmed = name.strip()
        if len(trimmed) < MIN_STORE_NAME_LEN or len(trimmed) > MAX_STORE_NAME_LEN:
            raise ValidationError(
                f"Store name must be between {MIN_STORE_NAME_LEN} and {MAX_STORE_NAME_LEN} characters."
            )
        return trimmed

    def _validate_and_normalize_optional_text(
        self, text: Optional[str], max_len: int, field_name: str
    ) -> Optional[str]:
        if text is None:
            return None
        trimmed = text.strip()
        if not trimmed:
            return None
        if len(trimmed) > max_len:
            raise ValidationError(
                f"{field_name.replace('_', ' ').title()} cannot exceed {max_len} characters."
            )
        return trimmed

    def _validate_and_normalize_email(self, email: Optional[str]) -> Optional[str]:
        if email is None:
            return None
        trimmed = email.strip()
        if not trimmed:
            return None
        if len(trimmed) > MAX_EMAIL_LEN:
            raise ValidationError(f"Email cannot exceed {MAX_EMAIL_LEN} characters.")
        if not EMAIL_REGEX.match(trimmed):
            raise ValidationError(f"Invalid email address format: '{trimmed}'.")
        return trimmed

    def _validate_and_normalize_receipt_header(self, header: Optional[str]) -> Optional[str]:
        if header is None:
            return DEFAULT_RECEIPT_HEADER
        trimmed = header.strip()
        if not trimmed:
            return DEFAULT_RECEIPT_HEADER
        if len(trimmed) > MAX_RECEIPT_HEADER_LEN:
            raise ValidationError(
                f"Receipt header cannot exceed {MAX_RECEIPT_HEADER_LEN} characters."
            )
        return trimmed

    def _validate_and_normalize_receipt_footer(self, footer: Optional[str]) -> Optional[str]:
        if footer is None:
            return DEFAULT_RECEIPT_FOOTER
        trimmed = footer.strip()
        if not trimmed:
            return DEFAULT_RECEIPT_FOOTER
        if len(trimmed) > MAX_RECEIPT_FOOTER_LEN:
            raise ValidationError(
                f"Receipt footer cannot exceed {MAX_RECEIPT_FOOTER_LEN} characters."
            )
        return trimmed

    def _validate_and_normalize_paper_width(self, width: str) -> str:
        if not width or not isinstance(width, str):
            raise ValidationError("Paper width is required.")
        norm_width = width.strip().lower()
        if norm_width not in {ReceiptWidth.MM_58.value, ReceiptWidth.MM_80.value}:
            raise ValidationError(
                f"Invalid paper width '{width}'. Must be '{ReceiptWidth.MM_58.value}' or '{ReceiptWidth.MM_80.value}'."
            )
        return norm_width

    def _safe_delete_managed_asset(self, relative_path: str) -> None:
        """Safely delete a managed asset without allowing directory traversal escape."""
        try:
            target_path = (settings.data_dir / relative_path).resolve()
            assets_root = self._assets_dir.resolve()
            # Path Security Guard: target must reside strictly inside data/assets
            if target_path.is_relative_to(assets_root) and target_path != assets_root and target_path.is_file():
                target_path.unlink(missing_ok=True)
                logger.info(f"Cleaned up managed asset: {target_path}")
        except Exception as e:
            logger.warning(f"Non-critical cleanup failure for asset '{relative_path}': {e}")

    def _display_path(self, abs_path: Path, *, is_dir: bool = False) -> str:
        """Render a privacy-safe display path for diagnostics.

        The application keeps using absolute paths internally, but anything
        shown to humans or exported (clipboard, support reports) is either
        project-relative (e.g. ``data\\retailflow.db``, ``logs\\``) or, when
        the configured path lives outside the project root, reduced to its
        final component so the local folder structure stays private.
        """
        try:
            display = str(abs_path.resolve().relative_to(settings.base_dir.resolve()))
        except ValueError:
            display = f"...{os.sep}{abs_path.name}"
        if is_dir and display and not display.endswith(os.sep):
            display += os.sep
        return display

    def _sanitize_database_location(self) -> str:
        """Extract sanitized, credential-free database location string."""
        if settings.database_type == "sqlite":
            return self._display_path(settings.data_dir / "retailflow.db")

        # For PostgreSQL or other URI connections: redact username and password
        try:
            parsed = urlparse(settings.database_url)
            host = parsed.hostname or "localhost"
            port = f":{parsed.port}" if parsed.port else ""
            dbname = parsed.path.lstrip("/") or "retailflow"
            return f"postgresql://{host}{port}/{dbname}"
        except Exception:
            return "postgresql://[redacted]"

    def _to_dto(self, record: StoreSettings) -> StoreSettingsDTO:
        """Convert ORM model to frozen DTO with graceful disk check for logo file."""
        projected_logo_path: Optional[str] = None
        if record.logo_path:
            physical_file = settings.data_dir / record.logo_path
            if physical_file.exists() and physical_file.is_file():
                projected_logo_path = record.logo_path
            else:
                # Read-only fallback projection if physical file was deleted externally
                projected_logo_path = None

        return StoreSettingsDTO(
            id=record.id,
            store_name=record.store_name,
            store_address=record.store_address,
            contact_number=record.contact_number,
            email=record.email,
            tin=record.tin,
            logo_path=projected_logo_path,
            receipt_header=record.receipt_header,
            receipt_footer=record.receipt_footer,
            paper_width=record.paper_width,
            show_store_address=record.show_store_address,
            show_contact=record.show_contact,
            show_tin=record.show_tin,
            show_tax_details=record.show_tax_details,
            updated_by_id=record.updated_by_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
