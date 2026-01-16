# Product Module

A comprehensive Odoo module for managing product registration with automatic QR code generation and assembly instructions.

## Features

### 1. Product Registration

- **Product Name**: Required field for product identification
- **Product ID**: Unique identifier for each product (used for QR code generation)
- **Variant**: Optional field for product variants
- **Photo**: Optional product image upload

### 2. QR Code Generation

- Automatic QR code generation based on Product ID
- Static QR codes displayed in product list
- Downloadable QR codes with custom filenames
- QR codes visible in both list and detail views

### 3. Assembly Instructions

- Add step-by-step assembly instructions for each product
- Drag-and-drop sequence ordering
- Each instruction includes:
  - Step number (sequence)
  - Step title
  - Detailed description
  - Optional illustration image

## User Interface

The module provides a clean interface with three main tabs matching the wireframe design:

### Tab 1: Product Type

Product job management with visual cards:

- Create and manage product types/jobs
- Visual kanban view showing type names and total variants
- Each type can have an image and description
- Shows count of products in each type

### Tab 2: Product List

Comprehensive product overview:

- View all registered products in a list format
- Display product images, names, codes, variants, and types
- Show QR codes and instruction counts
- Click "View Details" button to select a product for the Details tab
- Products with instructions highlighted in blue

### Tab 3: Product Details

Detailed product information and editing:

- Shows selected product's name, code, and description
- Displays product image
- Edit button to open full product form for editing
- Access to assembly instructions and QR code generation

## How to Use

### Creating Product Types

1. Navigate to **Product Module > Products**
2. Go to the **Product Type** tab
3. Click "Add a line" to create a new product type
4. Fill in:
   - Job Name (required)
   - Description (optional)
   - Image (optional)
5. The system will automatically count products in each type

### Registering Products

1. Go to the **Product List** tab
2. Click "Add a line" to create a new product
3. Fill in:
   - Product Name (required)
   - Product Code (required)
   - Variant (optional)
   - Product Job (optional)
   - Image (optional)
4. QR code is automatically generated

### Viewing Product Details

1. Go to the **Product List** tab
2. Click "View Details" button on any product
3. Switch to the **Product Details** tab
4. View the selected product's information
5. Click "Edit" button to modify the product

### Adding Assembly Instructions

1. Select a product using "View Details" button
2. Click "Edit" button in Product Details tab
3. Go to the **Assembly Instructions** tab in the product form
4. Click "Add a line" to add a new instruction
5. Fill in:
   - Step # (for ordering)
   - Step Title (required)
   - Instructions (detailed description)
   - Illustration (optional image)
6. Use the drag handle to reorder steps

### Viewing QR Codes

QR codes are automatically generated and visible:

- In the Products List tab (thumbnail view)
- In the product detail form (larger view)
- Can be downloaded using the filename format: `qr_{product_id}.png`

## Technical Details

## Arkite Integration Notes

This repository supports integrating Odoo Projects with Arkite via the Arkite REST API.

- **Credentials are server-specific**: if you have multiple Arkite servers (e.g. different IPs), each server can have a different `apiKey`. A key for one server will not work on another.
- **Recommended configuration**: create/select an **Arkite Unit** (`product_module.arkite.unit`) on the Odoo Project and store the Unit's `API Base URL` + `API Key` there. This avoids relying on a single global `.env` and supports multi-server setups.
- **Duplicate-from-template API behavior** (as implemented/expected):
  - `POST /projects/{templateId}/duplicate/` uses an **empty body**.
  - `PATCH /projects/{newId}` to rename uses a JSON object like `{"Name": "..."}` and typically returns **204 No Content**.

### Models

#### `product_module.page`

- Main container model
- Holds the list of registered products

#### `product_module.product`

- Stores product information
- Auto-generates QR codes
- Fields: name, product_code, variant, image, qr_image, instruction_ids

#### `product_module.instruction`

- Assembly instructions linked to products
- Sequenced for proper ordering
- Fields: sequence, title, description, image

### Dependencies

- **Odoo Base Module**: `base`
- **Python qrcode library**: Required for QR code generation (should be installed in Odoo container)

### Permissions

Default permissions for `base.group_user`:

- **Page**: Read, Write
- **Product**: Read, Write, Create, Delete
- **Instruction**: Read, Write, Create, Delete

## Installation

1. Ensure the `qrcode` Python library is installed in your Odoo container:

   ```bash
   pip install qrcode[pil]
   ```

2. Place the module in your Odoo addons directory

3. Update the app list in Odoo:

   - Go to Apps
   - Click "Update Apps List"

4. Search for "Product Module" and click Install

## Module Structure

```
product_module/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── main.py
├── data/
│   └── page_data.xml
├── models/
│   ├── __init__.py
│   ├── page.py
│   ├── product.py
│   └── instruction.py
├── security/
│   └── ir.model.access.csv
└── views/
    └── product_assemble_views.xml
```

## Author

**II- F Information Technology (NHL Stenden)**

## License

LGPL-3
