# DESIGN.md — RetailFlow POS UI/UX Design System & Specification

This document defines the UI/UX design standards, layout architecture, typography, interaction rules, and accessibility considerations for **RetailFlow POS**, with specific reference to the **Products Module**.

---

## 1. System Layout & Architecture

RetailFlow POS uses a **Fixed-Fluid Hybrid Grid** designed specifically for high-stakes, fast-paced retail desktop environments.

### Core Structure
- **Persistent Navigation Sidebar:** 240px fixed width (collapsible to 64px icon-only mode on smaller screens).
- **Header Bar:** 64px fixed height with breadcrumbs/page title and global user session info.
- **Main Canvas:** Fluid container (`#F7F9FB` background) with 24px container padding.

```
+---------------------------------------------------------------------------------------------------+
| persistent sidebar (240px) | Header Bar (64px)                                                    |
|                            +----------------------------------------------------------------------+
| - Dashboard                | Page Title: Product Catalog                     [+ Add Product]      |
| - POS / Checkout           +----------------------------------------------------------------------+
| - Products (Active)        | Metrics Summary Cards (4 Columns)                                    |
| - Inventory                | [ Total: 1,248 ] [ Low Stock: 12 ] [ Out of Stock: 5 ] [ Categories: 24]|
| - Sales History            +----------------------------------------------------------------------+
| - Purchasing               | Filter & Search Toolbar (#F1F5F9)                                   |
| - Settings                 | [🔍 Search Barcode/SKU/Name...] [Category ▾] [Status Pills] [Reset]  |
|                            +----------------------------------------------------------------------+
|                            | Products Data Table (High-Density QTableView)                        |
|                            | Barcode | Product Name & SKU | Category | Cost | Price | Stock | Actions|
|                            +----------------------------------------------------------------------+
|                            | Footer Pagination & Rows Per Page                                    |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Component Hierarchy

```
MainWindow (QMainWindow)
└── MainContainer (QWidget)
    ├── SidebarNavigation (QFrame #sidebar)
    └── ContentStackedWidget (QStackedWidget)
        └── ProductsPage (QWidget #productsPage)
            ├── PageHeaderWidget (QHBoxLayout)
            │   ├── TitleLabelGroup (QVBoxLayout)
            │   │   ├── TitleLabel (QLabel.title-sm)
            │   │   └── SubtitleLabel (QLabel.body-sm)
            │   └── PrimaryActionButton (QPushButton #primaryButton)
            ├── MetricsSummaryWidget (QHBoxLayout)
            │   ├── TotalProductsCard (MetricCardWidget)
            │   ├── LowStockCard (MetricCardWidget - Warning Style)
            │   ├── OutOfStockCard (MetricCardWidget - Error Style)
            │   └── CategoriesCard (MetricCardWidget)
            ├── FilterToolbarWidget (QFrame #filterToolbar)
            │   ├── SearchLineEdit (QLineEdit #searchInput)
            │   ├── CategoryComboBox (QComboBox #categoryFilter)
            │   ├── StatusButtonGroup (QFrame #statusFilterGroup)
            │   └── ResetFiltersButton (QPushButton #resetButton)
            ├── ProductsTableContainer (QFrame #tableContainer)
            │   ├── StateOverlayContainer (QStackedWidget)
            │   │   ├── LoadingSkeletonView (QWidget)
            │   │   ├── ErrorAlertBanner (QFrame #errorBanner)
            │   │   ├── EmptyStateView (QWidget #emptyState)
            │   │   └── MainTableView (QTableView #productsTable)
            │   │       ├── StatusBadgeDelegate (QStyledItemDelegate)
            │   │       └── ActionButtonsDelegate (QStyledItemDelegate)
            │   └── PaginationFooter (QHBoxLayout #paginationFooter)
            │       ├── RangeInfoLabel (QLabel)
            │       ├── RowsPerPageComboBox (QComboBox)
            │       └── PageNavigationWidget (QHBoxLayout)
            └── ProductFormDialog (QDialog #productFormDialog) [Modal]
```

---

## 3. Spacing & Density Scale

The visual layout operates on a strict **4px Baseline Grid**.

| Token | Pixel Value | Usage |
|---|---|---|
| `space-xs` | 4px | Tight element padding, icon-to-label gaps |
| `space-sm` | 8px | Button internal vertical padding, dense grid gaps |
| `space-md` | 16px | Standard component padding, table column gutter |
| `space-lg` | 24px | Outer page container padding, section vertical separation |
| `space-xl` | 32px | Modal dialog outer margins, major block margins |

### Table Density Specs
- **Dense Row Height (`row-height-dense`):** 32px (for compact/high-volume lists).
- **Standard Row Height (`row-height-standard`):** 48px (default for Product Catalog table).
- **Column Gutters:** Minimum 16px horizontal padding.

---

## 4. Typography System

The design system utilizes **Inter** for all UI elements and **JetBrains Mono** for numerical and tabular data.

| TextStyle | Font Family | Size | Weight | Line Height | Letter Spacing | Usage |
|---|---|---|---|---|---|---|
| `display-lg` | Inter | 32px | 700 (Bold) | 40px | -0.02em | Main Page Headlines |
| `headline-md` | Inter | 24px | 600 (SemiBold) | 32px | -0.01em | Section Titles, Modal Titles |
| `title-sm` | Inter | 18px | 600 (SemiBold) | 24px | 0 | Metric Card Labels, Section Headers |
| `body-md` | Inter | 14px | 400 (Regular) | 20px | 0 | Standard Form Inputs, Buttons |
| `body-sm` | Inter | 13px | 400 (Regular) | 18px | 0 | Secondary Labels, Subtitles |
| `label-caps` | Inter | 11px | 700 (Bold) | 16px | +0.05em | Table Header Titles, Badges (UPPERCASE) |
| `data-tabular` | JetBrains Mono | 13px | 500 (Medium) | 16px | 0 | SKUs, Barcodes, Prices (`₱ PHP`), Stock Counts |

---

## 5. UI States & Semantic Color Mapping

### Color Palette

- **Primary Canvas:** `#F7F9FB`
- **Surface Container (Cards/Toolbar):** `#FFFFFF` / `#F1F5F9`
- **Primary Accent (Navy):** `#0F172A`
- **Border / Divider:** `#E2E8F0`

### Semantic Stock Badges

1. **In Stock State:**
   - **Background:** `rgba(34, 197, 94, 0.10)` (10% Green)
   - **Text / Icon:** `#15803D` (Dark Green)
   - **Text format:** `150 In Stock`

2. **Low Stock State (Warning):**
   - **Background:** `rgba(234, 179, 8, 0.10)` (10% Yellow)
   - **Text / Icon:** `#A16207` (Dark Amber)
   - **Text format:** `8 Low Stock`

3. **Out of Stock State (Critical Error):**
   - **Background:** `rgba(239, 68, 68, 0.10)` (10% Red)
   - **Text / Icon:** `#B91C1C` (Dark Red)
   - **Text format:** `0 Out of Stock`

### View States

- **Loading State:** Gray skeleton pulsing placeholders (`#E2E8F0` animation) replacing data table rows.
- **Empty Catalog State:** Centered vector icon + "No products in catalog" text + "+ Add Product" primary button.
- **Empty Search State:** Magnifying glass illustration + "No products match your filter criteria" + "Reset Filters" text button.
- **Error State:** Banner at top of page (`#FEF2F2` bg, `#991B1B` border) with message + "Retry Connection" button.

---

## 6. Interaction Behavior & Shortcuts

### Keyboard Navigation & Shortcuts
- **`F3` or `Ctrl+F`:** Moves cursor focus directly to the Search Bar input.
- **`Ctrl+N`:** Opens the Add Product Modal Dialog.
- **`Esc`:** Clears search filter input if focused; closes open modal dialogs.
- **`Enter`:** Immediately submits search or submits open modal form.

### Search & Filter Dynamics
- **Multi-attribute matching:** Searches across `name`, `sku`, and `barcode` simultaneously.
- **Debounce:** 300ms delay on keystrokes before triggering background filtering query.
- **Barcode Scanner Support:** Physical barcode scanners sending standard string + `\n` immediately execute exact barcode matching.

---

## 7. Responsive Desktop Behavior

| Breakpoint | Window Width | Layout Adjustments |
|---|---|---|
| **Desktop High-Res** | `≥ 1440px` | 240px Sidebar + Full 12-column Grid + 4 Metrics Cards in a single row. |
| **Laptop Standard** | `1024px – 1439px` | 240px Sidebar + Metrics Cards wrap to 2x2 grid if needed + Table enables horizontal scroll for secondary columns. |
| **Compact Tablet/POS** | `768px – 1023px` | Sidebar collapses to 64px icon-only bar + Metrics Cards stack vertically + Filters condense to collapsible drawer. |

---

## 8. Accessibility Considerations (WCAG 2.1 AA Compliance)

1. **Color Contrast:**
   - All body and tabular text achieves minimum **4.5:1** contrast ratio against backgrounds (e.g., `#191C1E` on `#FFFFFF`).
   - Semantic badge text achieves minimum **7:1** contrast.

2. **Focus Indicators:**
   - Interactive controls (inputs, buttons, table rows) feature a **2px solid Deep Navy (`#0F172A`) focus ring** with a 2px offset when navigated via keyboard `Tab`.

3. **Screen Reader & Qt Accessibility:**
   - Every PySide6 widget must set `setAccessibleName()` and `setAccessibleDescription()`.
   - Table headers are mapped as column headers for screen readers.

4. **Keyboard-Only Operation:**
   - Strict tab order defined from top-left to bottom-right (Header -> Search -> Filters -> Table -> Pagination).
   - No keyboard traps in modal dialogs.
