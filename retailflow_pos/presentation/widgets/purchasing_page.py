"""
RetailFlow POS - Purchasing & Purchase Orders Workstation Page
Manages purchase orders, tracks vendor shipments, and processes stock inventory intake.
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

from application.dto.purchasing_dto import PurchaseOrderFilterDTO, PurchaseOrderResponseDTO
from application.dto.supplier_dto import SupplierFilterDTO
from application.services.product_service import ProductService
from application.services.purchasing_service import PurchasingService
from application.services.supplier_service import SupplierService
from infrastructure.database.models.auth import User
from presentation.dialogs.po_details_dialog import PODetailsDialog
from presentation.dialogs.purchase_order_dialog import PurchaseOrderDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class PurchasingPage(QWidget):
    """Purchasing and purchase orders management workstation."""

    def __init__(
        self,
        current_user: User,
        purchasing_service: PurchasingService,
        supplier_service: SupplierService,
        product_service: ProductService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._purchasing_service = purchasing_service
        self._supplier_service = supplier_service
        self._product_service = product_service
        self._pos_list: list[PurchaseOrderResponseDTO] = []
        self._page = 1
        self._page_size = 20
        self._total = 0
        self._active_chip = "all"

        self._init_ui()
        self.load_orders()

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

        title_lbl = QLabel("Purchasing & Purchase Orders")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Create purchase orders, track wholesale vendor shipments, and receive stock inventory.")
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
        btn_refresh.clicked.connect(self.load_orders)
        hdr_row.addWidget(btn_refresh)

        self.btn_new_po = QPushButton(" + New Purchase Order")
        self.btn_new_po.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=14))
        self.btn_new_po.setFixedHeight(36)
        self.btn_new_po.setCursor(Qt.PointingHandCursor)
        self.btn_new_po.setStyleSheet("""
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
        self.btn_new_po.clicked.connect(self._open_new_po_dialog)
        hdr_row.addWidget(self.btn_new_po)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL PURCHASE ORDERS",
            icon_name="purchasing",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_pending = MetricCardWidget(
            title="PENDING / IN-TRANSIT",
            icon_name="clock",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_received = MetricCardWidget(
            title="RECEIVED ORDERS",
            icon_name="check",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_spent = MetricCardWidget(
            title="TOTAL PURCHASES (₱)",
            icon_name="sales",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )

        for card in [self.card_total, self.card_pending, self.card_received, self.card_spent]:
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
        self.txt_search.setPlaceholderText("Search PO by number, supplier name, or item name...")
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

        self.cmb_supplier = QComboBox()
        self.cmb_supplier.addItem("All Suppliers", None)
        self.cmb_supplier.setFixedHeight(36)
        self.cmb_supplier.setStyleSheet("""
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
        self.cmb_supplier.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_supplier, stretch=2)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", None)
        self.cmb_status.addItem("Ordered / In-Transit", "ORDERED")
        self.cmb_status.addItem("Received", "RECEIVED")
        self.cmb_status.addItem("Draft", "DRAFT")
        self.cmb_status.addItem("Cancelled", "CANCELLED")
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

        self.chip_all = QPushButton("All Orders")
        self.chip_ordered = QPushButton("Ordered / In-Transit")
        self.chip_received = QPushButton("Received Stock")
        self.chip_draft = QPushButton("Drafts")
        self.chip_cancelled = QPushButton("Cancelled")

        self.po_chips = [
            (self.chip_all, "all", None),
            (self.chip_ordered, "ordered", "ORDERED"),
            (self.chip_received, "received", "RECEIVED"),
            (self.chip_draft, "draft", "DRAFT"),
            (self.chip_cancelled, "cancelled", "CANCELLED"),
        ]

        for chip_btn, mode, st_val in self.po_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, s=st_val: self._on_chip_clicked(m, s))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # ── 4. Purchase Orders Table Feed ──
        self.tbl_pos = QTableWidget()
        self.tbl_pos.setColumnCount(7)
        self.tbl_pos.setHorizontalHeaderLabels([
            "PO NUMBER",
            "SUPPLIER & CODE",
            "ORDER / DELIVERY DATE",
            "ITEMS & QTY",
            "STATUS",
            "TOTAL AMOUNT",
            "ACTIONS",
        ])

        self.tbl_pos.verticalHeader().setVisible(False)
        self.tbl_pos.setAlternatingRowColors(True)
        self.tbl_pos.setShowGrid(False)
        self.tbl_pos.setStyleSheet("""
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

        header = self.tbl_pos.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_pos.setColumnWidth(6, 150)

        self.tbl_pos.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_pos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_pos.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_pos, stretch=1)

        # ── 5. Pagination Footer ──
        footer_layout = QHBoxLayout()
        self.lbl_page_info = QLabel("Showing 0–0 of 0 purchase orders")
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

        self._populate_suppliers_filter()

    def _populate_suppliers_filter(self):
        try:
            res = self._supplier_service.search(SupplierFilterDTO(is_active=True, page_size=100))
            self.cmb_supplier.blockSignals(True)
            self.cmb_supplier.clear()
            self.cmb_supplier.addItem("All Suppliers", None)
            for s in res.items:
                self.cmb_supplier.addItem(f"{s.name} ({s.code})", s.id)
            self.cmb_supplier.blockSignals(False)
        except Exception:
            pass

    def _on_search_changed(self):
        self._page = 1
        self.load_orders()

    def _on_filter_changed(self):
        self._page = 1
        self.load_orders()

    def _on_chip_clicked(self, mode: str, status_val: Optional[str]):
        self._active_chip = mode
        self._update_chip_styles()

        self.cmb_status.blockSignals(True)
        if status_val:
            idx = self.cmb_status.findData(status_val)
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
        else:
            self.cmb_status.setCurrentIndex(0)
        self.cmb_status.blockSignals(False)

        self._page = 1
        self.load_orders()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.po_chips:
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
            self.load_orders()

    def _next_page(self):
        if self._page * self._page_size < self._total:
            self._page += 1
            self.load_orders()

    def load_orders(self):
        """Fetch purchase orders matching filters and populate table."""
        try:
            keyword = self.txt_search.text().strip() or None
            supplier_id = self.cmb_supplier.currentData()
            status = self.cmb_status.currentData()

            filters = PurchaseOrderFilterDTO(
                keyword=keyword,
                supplier_id=supplier_id,
                status=status,
                page=self._page,
                page_size=self._page_size,
            )

            result = self._purchasing_service.search(filters, self._user)
            self._pos_list = result.items
            self._total = result.total

            # Update Metrics
            metrics = self._purchasing_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_pos))
            self.card_total.set_caption("● Lifetime PO records")

            self.card_pending.update_value(str(metrics.pending_orders))
            self.card_pending.set_caption("● Awaiting vendor delivery")

            self.card_received.update_value(str(metrics.received_orders))
            self.card_received.set_caption("● Stock intake completed")

            self.card_spent.update_value(f"₱{metrics.total_purchases_spent:,.2f}")
            self.card_spent.set_caption("● Total purchase volume")

            # Render Table
            self.tbl_pos.setRowCount(len(result.items))
            dark_color = QColor("#0f172a")

            for row, po in enumerate(result.items):
                self.tbl_pos.setRowHeight(row, 48)

                # Col 0: PO Number
                po_item = QTableWidgetItem(po.po_number)
                po_item.setFont(QFont("Consolas", 10, QFont.Bold))
                po_item.setForeground(QColor("#2563eb"))
                po_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_pos.setItem(row, 0, po_item)

                # Col 1: Supplier & Code
                sup_w = QWidget()
                sup_l = QVBoxLayout(sup_w)
                sup_l.setContentsMargins(4, 2, 4, 2)
                sup_l.setSpacing(1)
                sname_lbl = QLabel(po.supplier_name)
                sname_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
                scode_lbl = QLabel(f"Code: {po.supplier_code} · {po.payment_terms.replace('_', ' ')}")
                scode_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #64748b;")
                sup_l.addWidget(sname_lbl)
                sup_l.addWidget(scode_lbl)
                self.tbl_pos.setCellWidget(row, 1, sup_w)

                # Col 2: Order / Delivery Date
                date_w = QWidget()
                date_l = QVBoxLayout(date_w)
                date_l.setContentsMargins(4, 2, 4, 2)
                date_l.setSpacing(1)
                ord_lbl = QLabel(f"Ordered: {po.order_date}")
                ord_lbl.setStyleSheet("font-size: 11px; color: #0f172a; font-weight: 600;")
                due_lbl = QLabel(f"Due: {po.expected_delivery}" if po.expected_delivery else "No due date")
                due_lbl.setStyleSheet("font-size: 10px; color: #64748b;")
                date_l.addWidget(ord_lbl)
                date_l.addWidget(due_lbl)
                self.tbl_pos.setCellWidget(row, 2, date_w)

                # Col 3: Items & Qty
                items_item = QTableWidgetItem(f"{po.items_count} items ({po.total_units} pcs)")
                items_item.setFont(QFont("Segoe UI", 10))
                items_item.setForeground(QColor("#475569"))
                items_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_pos.setItem(row, 3, items_item)

                # Col 4: Status Badge
                st_lbl = QLabel(po.status.upper())
                st_lbl.setAlignment(Qt.AlignCenter)
                st_lower = po.status.lower()
                if "receive" in st_lower:
                    st_style = "color: #059669; background-color: #ecfdf5; border: 1px solid #a7f3d0;"
                elif "order" in st_lower:
                    st_style = "color: #2563eb; background-color: #eff6ff; border: 1px solid #bfdbfe;"
                elif "draft" in st_lower:
                    st_style = "color: #475569; background-color: #f1f5f9; border: 1px solid #cbd5e1;"
                else:
                    st_style = "color: #dc2626; background-color: #fef2f2; border: 1px solid #fecaca;"
                st_lbl.setStyleSheet(f"{st_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_pos.setCellWidget(row, 4, st_lbl)

                # Col 5: Total Amount
                tot_item = QTableWidgetItem(f"₱{po.total_amount:,.2f}")
                tot_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                tot_item.setForeground(dark_color)
                tot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_pos.setItem(row, 5, tot_item)

                # Col 6: Actions (Receive & View)
                act_w = QWidget()
                act_l = QHBoxLayout(act_w)
                act_l.setContentsMargins(4, 0, 4, 0)
                act_l.setSpacing(4)

                btn_view = QPushButton(" View")
                btn_view.setIcon(IconManager.get_pixmap("search", color="#475569", size=11))
                btn_view.setFixedHeight(28)
                btn_view.setCursor(Qt.PointingHandCursor)
                btn_view.setStyleSheet("""
                    QPushButton {
                        background-color: #f8fafc;
                        color: #475569;
                        border: 1px solid #cbd5e1;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 8px;
                    }
                    QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
                """)
                btn_view.clicked.connect(lambda chk, p=po: self._open_details_dialog(p))
                act_l.addWidget(btn_view)

                if po.status in ("ORDERED", "DRAFT"):
                    btn_rec = QPushButton(" Receive")
                    btn_rec.setIcon(IconManager.get_pixmap("check", color="#059669", size=11))
                    btn_rec.setFixedHeight(28)
                    btn_rec.setCursor(Qt.PointingHandCursor)
                    btn_rec.setStyleSheet("""
                        QPushButton {
                            background-color: #ecfdf5;
                            color: #059669;
                            border: 1px solid #a7f3d0;
                            border-radius: 6px;
                            font-size: 11px;
                            font-weight: 700;
                            padding: 0 8px;
                        }
                        QPushButton:hover {
                            background-color: #059669;
                            color: #ffffff;
                        }
                    """)
                    btn_rec.clicked.connect(lambda chk, p=po: self._receive_po(p))
                    act_l.addWidget(btn_rec)

                self.tbl_pos.setCellWidget(row, 6, act_w)

            # Update Pagination Footer
            start_num = (result.page - 1) * result.page_size + 1 if result.total > 0 else 0
            end_num = min(result.page * result.page_size, result.total)
            self.lbl_page_info.setText(f"Showing {start_num}–{end_num} of {result.total} purchase orders")
            self.btn_prev.setEnabled(result.has_previous)
            self.btn_next.setEnabled(result.has_next)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.purchasing").exception("Failed to load purchase orders", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._pos_list):
            self._open_details_dialog(self._pos_list[row])

    def _open_new_po_dialog(self):
        dlg = PurchaseOrderDialog(
            self._purchasing_service,
            self._supplier_service,
            self._product_service,
            self._user,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast("Purchase order created successfully!")
            self.load_orders()

    def _open_details_dialog(self, po_dto: PurchaseOrderResponseDTO):
        dlg = PODetailsDialog(self._purchasing_service, po_dto, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Purchase order {po_dto.po_number} updated!")
            self.load_orders()

    def _receive_po(self, po_dto: PurchaseOrderResponseDTO):
        try:
            self._purchasing_service.receive_stock(po_dto.id, actor=self._user)
            self._toast.show_toast(f"Stock received for {po_dto.po_number}! Inventory updated.")
            self.load_orders()
        except Exception as e:
            pass
