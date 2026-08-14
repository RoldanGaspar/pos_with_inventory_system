"""
RetailFlow POS - Suppliers Directory & Vendor Management Page
Workstation for managing wholesale distributors, vendor contact persons, payment terms, and TIN.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.supplier_dto import SupplierFilterDTO, SupplierResponseDTO
from application.services.supplier_service import SupplierService
from infrastructure.database.models.auth import User
from presentation.dialogs.supplier_dialog import SupplierDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class SuppliersPage(QWidget):
    """Suppliers Directory and Vendor Management workstation."""

    def __init__(
        self,
        current_user: User,
        supplier_service: SupplierService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._supplier_service = supplier_service
        self._suppliers_list: list[SupplierResponseDTO] = []
        self._page = 1
        self._page_size = 20
        self._total = 0
        self._active_chip = "all"

        self._init_ui()
        self.load_suppliers()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Toast notification overlay
        self._toast = ToastNotification(self)

        # ── 1. Header Title & Top Actions ──
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("Suppliers Directory & Vendor Management")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Manage wholesale distributors, vendor contact persons, payment terms, and supply lines.")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)

        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh")
        btn_refresh.setIcon(IconManager.get_pixmap("clock", color="#475569", size=13))
        btn_refresh.setFixedHeight(36)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
                color: #2563eb;
            }
        """)
        btn_refresh.clicked.connect(self.load_suppliers)
        hdr_row.addWidget(btn_refresh)

        self.btn_add_supplier = QPushButton(" + Add Supplier")
        self.btn_add_supplier.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=14))
        self.btn_add_supplier.setFixedHeight(36)
        self.btn_add_supplier.setCursor(Qt.PointingHandCursor)
        self.btn_add_supplier.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
                padding: 0px 16px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_add_supplier.clicked.connect(self._open_add_dialog)
        hdr_row.addWidget(self.btn_add_supplier)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL SUPPLIERS",
            icon_name="suppliers",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_active = MetricCardWidget(
            title="ACTIVE VENDORS",
            icon_name="check",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_credit = MetricCardWidget(
            title="CREDIT TERMS (NET 30+)",
            icon_name="sales",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )
        self.card_cod = MetricCardWidget(
            title="CASH ON DELIVERY (COD)",
            icon_name="tag",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )

        for card in [self.card_total, self.card_active, self.card_credit, self.card_cod]:
            metrics_layout.addWidget(card)

        main_layout.addLayout(metrics_layout)

        # ── 3. Search & Filter Toolbar ──
        toolbar_card = QFrame()
        toolbar_card.setObjectName("filterToolbar")
        toolbar_card.setStyleSheet("""
            QFrame#filterToolbar {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        v_toolbar = QVBoxLayout(toolbar_card)
        v_toolbar.setContentsMargins(0, 0, 0, 0)
        v_toolbar.setSpacing(8)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self.txt_search.setPlaceholderText("Search supplier by company name, code, contact person, or phone...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        self.txt_search.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.txt_search, stretch=3)

        self.cmb_terms = QComboBox()
        self.cmb_terms.addItem("All Payment Terms", None)
        self.cmb_terms.addItem("Net 30 Days", "NET_30")
        self.cmb_terms.addItem("Net 15 Days", "NET_15")
        self.cmb_terms.addItem("Net 60 Days", "NET_60")
        self.cmb_terms.addItem("Cash on Delivery (COD)", "COD")
        self.cmb_terms.setFixedHeight(36)
        self.cmb_terms.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_terms.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_terms, stretch=1)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", None)
        self.cmb_status.addItem("Active", True)
        self.cmb_status.addItem("Inactive", False)
        self.cmb_status.setFixedHeight(36)
        self.cmb_status.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_status.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_status, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Fast Filter Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Suppliers")
        self.chip_active = QPushButton("Active Vendors")
        self.chip_credit = QPushButton("Net 30 / 60 Terms")
        self.chip_cod = QPushButton("COD Accounts")
        self.chip_net15 = QPushButton("Net 15 Days")

        self.supplier_chips = [
            (self.chip_all, "all", None, None),
            (self.chip_active, "active", None, True),
            (self.chip_credit, "credit", "NET_30", None),
            (self.chip_cod, "cod", "COD", None),
            (self.chip_net15, "net15", "NET_15", None),
        ]

        for chip_btn, mode, t_name, stat in self.supplier_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, tn=t_name, s=stat: self._on_chip_clicked(m, tn, s))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # ── 4. Suppliers Table Feed ──
        self.tbl_suppliers = QTableWidget()
        self.tbl_suppliers.setColumnCount(7)
        self.tbl_suppliers.setHorizontalHeaderLabels([
            "CODE",
            "COMPANY NAME",
            "CONTACT PERSON & PHONE",
            "EMAIL & ADDRESS",
            "PAYMENT TERMS",
            "TAX ID / TIN",
            "ACTIONS",
        ])

        self.tbl_suppliers.verticalHeader().setVisible(False)
        self.tbl_suppliers.setAlternatingRowColors(True)
        self.tbl_suppliers.setShowGrid(False)
        self.tbl_suppliers.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 8px 10px;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)

        header = self.tbl_suppliers.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_suppliers.setColumnWidth(6, 90)

        self.tbl_suppliers.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_suppliers.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_suppliers.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_suppliers, stretch=1)

        # ── 5. Pagination Footer ──
        footer_layout = QHBoxLayout()
        self.lbl_page_info = QLabel("Showing 0–0 of 0 suppliers")
        self.lbl_page_info.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        footer_layout.addWidget(self.lbl_page_info)
        footer_layout.addStretch()

        self.btn_prev = QPushButton("‹ Previous")
        self.btn_prev.setFixedHeight(30)
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        footer_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next ›")
        self.btn_next.setFixedHeight(30)
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        self.btn_next.clicked.connect(self._next_page)
        footer_layout.addWidget(self.btn_next)

        main_layout.addLayout(footer_layout)

    def _on_search_changed(self):
        self._page = 1
        self.load_suppliers()

    def _on_filter_changed(self):
        self._page = 1
        self.load_suppliers()

    def _on_chip_clicked(self, mode: str, terms_name: Optional[str], status: Optional[bool]):
        self._active_chip = mode
        self._update_chip_styles()

        self.cmb_terms.blockSignals(True)
        if terms_name:
            idx = self.cmb_terms.findData(terms_name)
            if idx >= 0:
                self.cmb_terms.setCurrentIndex(idx)
        else:
            self.cmb_terms.setCurrentIndex(0)
        self.cmb_terms.blockSignals(False)

        self.cmb_status.blockSignals(True)
        if status is not None:
            idx_s = self.cmb_status.findData(status)
            if idx_s >= 0:
                self.cmb_status.setCurrentIndex(idx_s)
        else:
            self.cmb_status.setCurrentIndex(0)
        self.cmb_status.blockSignals(False)

        self._page = 1
        self.load_suppliers()

    def _update_chip_styles(self):
        for chip_btn, mode, _, _ in self.supplier_chips:
            is_active = self._active_chip == mode
            if is_active:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 12px;
                    }
                """)
            else:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #475569;
                        border: 1px solid #e2e8f0;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 12px;
                    }
                    QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
                """)

    def _prev_page(self):
        if self._page > 1:
            self._page -= 1
            self.load_suppliers()

    def _next_page(self):
        if self._page * self._page_size < self._total:
            self._page += 1
            self.load_suppliers()

    def load_suppliers(self):
        """Fetch suppliers matching filters and populate table."""
        try:
            keyword = self.txt_search.text().strip() or None
            terms = self.cmb_terms.currentData()
            is_active = self.cmb_status.currentData()

            filters = SupplierFilterDTO(
                keyword=keyword,
                payment_terms=terms,
                is_active=is_active,
                page=self._page,
                page_size=self._page_size,
            )

            result = self._supplier_service.search(filters, self._user)
            self._suppliers_list = result.items
            self._total = result.total

            # Update Metrics
            metrics = self._supplier_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_suppliers))
            self.card_total.set_caption("● Registered distributors")

            self.card_active.update_value(str(metrics.active_suppliers))
            self.card_active.set_caption("● Verified active vendors")

            self.card_credit.update_value(str(metrics.credit_terms_count))
            self.card_credit.set_caption("● Net 30/60 invoice lines")

            self.card_cod.update_value(str(metrics.cod_count))
            self.card_cod.set_caption("● Cash on delivery accounts")

            # Render Table
            self.tbl_suppliers.setRowCount(len(result.items))
            dark_color = QColor("#0f172a")

            for row, s in enumerate(result.items):
                self.tbl_suppliers.setRowHeight(row, 48)

                # Col 0: Supplier Code
                code_item = QTableWidgetItem(s.code)
                code_item.setFont(QFont("Consolas", 10, QFont.Bold))
                code_item.setForeground(QColor("#2563eb"))
                code_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_suppliers.setItem(row, 0, code_item)

                # Col 1: Company Name
                name_w = QWidget()
                name_l = QVBoxLayout(name_w)
                name_l.setContentsMargins(4, 2, 4, 2)
                name_l.setSpacing(1)
                full_lbl = QLabel(s.name)
                full_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
                stat_str = "● Active Supplier" if s.is_active else "● Inactive"
                stat_col = "#059669" if s.is_active else "#94a3b8"
                sub_lbl = QLabel(stat_str)
                sub_lbl.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {stat_col};")
                name_l.addWidget(full_lbl)
                name_l.addWidget(sub_lbl)
                self.tbl_suppliers.setCellWidget(row, 1, name_w)

                # Col 2: Contact Person & Phone
                cont_w = QWidget()
                cont_l = QVBoxLayout(cont_w)
                cont_l.setContentsMargins(4, 2, 4, 2)
                cont_l.setSpacing(1)
                person_lbl = QLabel(s.contact_person or "General Distributor")
                person_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #0f172a;")
                phone_lbl = QLabel(s.phone)
                phone_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b; font-family: 'Consolas', monospace;")
                cont_l.addWidget(person_lbl)
                cont_l.addWidget(phone_lbl)
                self.tbl_suppliers.setCellWidget(row, 2, cont_w)

                # Col 3: Email & Address
                addr_w = QWidget()
                addr_l = QVBoxLayout(addr_w)
                addr_l.setContentsMargins(4, 2, 4, 2)
                addr_l.setSpacing(1)
                email_lbl = QLabel(s.email or "No email on file")
                email_lbl.setStyleSheet("font-size: 11px; color: #0f172a; font-weight: 500;")
                city_lbl = QLabel(s.address or "No address")
                city_lbl.setStyleSheet("font-size: 10px; color: #64748b;")
                addr_l.addWidget(email_lbl)
                addr_l.addWidget(city_lbl)
                self.tbl_suppliers.setCellWidget(row, 3, addr_w)

                # Col 4: Payment Terms Badge
                terms_lbl = QLabel(s.payment_terms.replace("_", " "))
                terms_lbl.setAlignment(Qt.AlignCenter)
                t_lower = s.payment_terms.lower()
                if "net_30" in t_lower:
                    t_style = "color: #2563eb; background-color: #eff6ff; border: 1px solid #bfdbfe;"
                elif "net_60" in t_lower:
                    t_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
                elif "net_15" in t_lower:
                    t_style = "color: #d97706; background-color: #fffbeb; border: 1px solid #fde68a;"
                else:
                    t_style = "color: #059669; background-color: #ecfdf5; border: 1px solid #a7f3d0;"
                terms_lbl.setStyleSheet(f"{t_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_suppliers.setCellWidget(row, 4, terms_lbl)

                # Col 5: Tax ID / TIN
                tin_item = QTableWidgetItem(s.tax_id or "N/A")
                tin_item.setFont(QFont("Consolas", 10))
                tin_item.setForeground(QColor("#64748b"))
                tin_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_suppliers.setItem(row, 5, tin_item)

                # Col 6: Action Button (Edit)
                act_w = QWidget()
                act_l = QHBoxLayout(act_w)
                act_l.setContentsMargins(4, 0, 4, 0)
                act_l.setAlignment(Qt.AlignCenter)

                btn_edit = QPushButton(" Edit")
                btn_edit.setIcon(IconManager.get_pixmap("edit", color="#2563eb", size=12))
                btn_edit.setFixedSize(68, 28)
                btn_edit.setCursor(Qt.PointingHandCursor)
                btn_edit.setStyleSheet("""
                    QPushButton {
                        background-color: #eff6ff;
                        color: #2563eb;
                        border: 1px solid #bfdbfe;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 8px;
                    }
                    QPushButton:hover {
                        background-color: #2563eb;
                        color: #ffffff;
                    }
                """)
                btn_edit.clicked.connect(lambda chk, supp=s: self._open_edit_dialog(supp))
                act_l.addWidget(btn_edit)

                self.tbl_suppliers.setCellWidget(row, 6, act_w)

            # Update Pagination Footer
            start_num = (result.page - 1) * result.page_size + 1 if result.total > 0 else 0
            end_num = min(result.page * result.page_size, result.total)
            self.lbl_page_info.setText(f"Showing {start_num}–{end_num} of {result.total} suppliers")
            self.btn_prev.setEnabled(result.has_previous)
            self.btn_next.setEnabled(result.has_next)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.suppliers").exception("Failed to load suppliers", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._suppliers_list):
            self._open_edit_dialog(self._suppliers_list[row])

    def _open_add_dialog(self):
        dlg = SupplierDialog(self._supplier_service, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast("Wholesale supplier registered successfully!")
            self.load_suppliers()

    def _open_edit_dialog(self, supplier: SupplierResponseDTO):
        dlg = SupplierDialog(self._supplier_service, self._user, supplier_data=supplier, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Updated profile for '{supplier.name}'")
            self.load_suppliers()
