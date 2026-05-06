# Database schema (current)

## users

### `users_user`
- `public_id` (unique, yearly format)
- `role` (`admin` / `staff` / `customer`)
- plus standard Django `AbstractUser` fields

## settings

### `settings_setting`
- `key` (unique)
- `value` (text)
- `description` (text)

## products

### `products_product`
- `public_id` (unique, monthly format)
- `name`, `slug` (unique), `description`
- `price`, `is_active`, `image`
- soft delete fields: `is_deleted`, `deleted_at`

## orders

### `orders_order`
- `public_id` (unique, monthly format)
- `customer` → `users_user`
- `status` (pending/confirmed/processing/shipped/delivered/cancelled)
- `note`, `total_amount`
- soft delete fields: `is_deleted`, `deleted_at`

### `orders_orderitem`
- `order` → `orders_order`
- `product` → `products_product`
- `quantity`, `unit_price`, `line_total`
- unique constraint: (`order`, `product`)
- soft delete fields: `is_deleted`, `deleted_at`

### `orders_ordertracking`
- `order` → `orders_order`
- `status`
- `timestamp`
- `note`

## Inventory / Accounts / Reports

## accounts

### `accounts_income`
- `public_id` (monthly format `INC-*`)
- `date`, `amount`, `title`, `note`
- optional `order` → `orders_order`

### `accounts_expense`
- `public_id` (monthly format `EXP-*`)
- `date`, `amount`, `title`, `category`, `note`

### `accounts_ledgerentry`
- `entry_type` (`income`/`expense`)
- `date`, `amount`, `narration`
- optional one-to-one: `income` → `accounts_income`, `expense` → `accounts_expense`

## inventory

### `inventory_inventoryitem`
- one-to-one `product` → `products_product`
- `quantity_on_hand`, `reorder_level`, `last_counted_at`

### `inventory_purchase`
- `public_id` (yearly format `PUR-*`)
- `date`, `supplier_name`, `reference`, `note`, `total_cost`

### `inventory_purchaseitem`
- `purchase` → `inventory_purchase`
- `product` → `products_product`
- `quantity`, `unit_cost`, `line_total`
- unique constraint: (`purchase`, `product`)

### `inventory_inventorytransaction`
- `product` → `products_product`
- `txn_type` (purchase/sale/adjustment), `quantity_delta`, `note`
- optional: `order` → `orders_order`, `purchase` → `inventory_purchase`

## reports

App exists under `apps/reports` (models not implemented yet).
