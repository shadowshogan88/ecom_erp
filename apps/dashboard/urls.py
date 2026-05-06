from django.urls import path, register_converter

from core.url_converters import ProductPublicIdConverter

register_converter(ProductPublicIdConverter, "prd")

from .views import (
    dashboard_home,
    dashboard_logout,
    dashboard_inventory_list,
    dashboard_order_detail,
    dashboard_order_invoice_pdf,
    dashboard_orders_list,
    dashboard_customers_list,
    dashboard_products_list,
    dashboard_product_create,
    dashboard_product_delete,
    dashboard_product_edit,
    dashboard_product_image_create,
    dashboard_product_image_delete,
    dashboard_product_image_make_primary,
    dashboard_product_inventory_update,
    dashboard_product_variant_create,
    dashboard_product_variant_delete,
    dashboard_product_variant_edit,
    dashboard_product_variant_generator,
    dashboard_api_attribute_value_create,
    dashboard_api_generate_variants,
    dashboard_api_preview_variants,
    dashboard_api_product_variants_data,
    dashboard_api_variant_bulk_update,
    dashboard_api_variant_delete,
    dashboard_api_variant_image_upload,
    dashboard_api_variant_set_default,
    dashboard_attribute_values_manage,
    dashboard_attributes_list,
    dashboard_profile_edit,
    dashboard_reports,
    dashboard_reports_pdf,
    dashboard_site_content,
)

urlpatterns = [
    path("", dashboard_home, name="dashboard-home"),
    path("logout/", dashboard_logout, name="dashboard-logout"),
    path("profile/", dashboard_profile_edit, name="dashboard-profile"),
    path("reports/", dashboard_reports, name="dashboard-reports"),
    path("reports/export.pdf", dashboard_reports_pdf, name="dashboard-reports-pdf"),
    path("site-content/", dashboard_site_content, name="dashboard-site-content"),
    path("orders/", dashboard_orders_list, name="dashboard-orders"),
    path("orders/<path:public_id>/", dashboard_order_detail, name="dashboard-order-detail"),
    path("orders/<path:public_id>/invoice.pdf", dashboard_order_invoice_pdf, name="dashboard-order-invoice"),
    path("products/", dashboard_products_list, name="dashboard-products"),
    path("products/new/", dashboard_product_create, name="dashboard-product-create"),
    path("products/<prd:public_id>/inventory/", dashboard_product_inventory_update, name="dashboard-product-inventory"),
    # NOTE: `public_id` contains `/` (e.g. PRD-1/05-26), so we must use `<path:public_id>`.
    # This makes URL ordering important: keep more specific nested routes BEFORE generic ones
    # like `products/<path:public_id>/edit|delete/` to avoid routing conflicts.

    path(
        "products/<prd:public_id>/variants/generator/",
        dashboard_product_variant_generator,
        name="dashboard-product-variant-generator",
    ),
    path("products/<prd:public_id>/variants/new/", dashboard_product_variant_create, name="dashboard-product-variant-create"),
    path(
        "products/<prd:public_id>/variants/<int:variant_id>/edit/",
        dashboard_product_variant_edit,
        name="dashboard-product-variant-edit",
    ),
    path(
        "products/<prd:public_id>/variants/<int:variant_id>/delete/",
        dashboard_product_variant_delete,
        name="dashboard-product-variant-delete",
    ),
    # Variant Generator AJAX endpoints (Vanilla JS)
    path(
        "products/<prd:public_id>/variants/data/",
        dashboard_api_product_variants_data,
        name="dashboard-api-product-variants-data",
    ),
    path(
        "products/<prd:public_id>/variants/generate/",
        dashboard_api_generate_variants,
        name="dashboard-api-generate-variants",
    ),
    path(
        "products/<prd:public_id>/variants/preview/",
        dashboard_api_preview_variants,
        name="dashboard-api-preview-variants",
    ),
    path(
        "products/<prd:public_id>/variants/bulk-update/",
        dashboard_api_variant_bulk_update,
        name="dashboard-api-variant-bulk-update",
    ),
    path(
        "products/<prd:public_id>/variants/<int:variant_id>/default/",
        dashboard_api_variant_set_default,
        name="dashboard-api-variant-set-default",
    ),
    path(
        "products/<prd:public_id>/variants/<int:variant_id>/image/",
        dashboard_api_variant_image_upload,
        name="dashboard-api-variant-image-upload",
    ),
    path(
        "products/<prd:public_id>/variants/<int:variant_id>/delete-ajax/",
        dashboard_api_variant_delete,
        name="dashboard-api-variant-delete",
    ),
    path(
        "attributes/<int:attribute_id>/values/create/",
        dashboard_api_attribute_value_create,
        name="dashboard-api-attribute-value-create",
    ),
    path("products/<prd:public_id>/images/new/", dashboard_product_image_create, name="dashboard-product-image-create"),
    path(
        "products/<prd:public_id>/images/<int:image_id>/primary/",
        dashboard_product_image_make_primary,
        name="dashboard-product-image-primary",
    ),
    path(
        "products/<prd:public_id>/images/<int:image_id>/delete/",
        dashboard_product_image_delete,
        name="dashboard-product-image-delete",
    ),

    # Generic product routes LAST (avoid conflicts with nested /variants/... and /images/...)
    path("products/<prd:public_id>/edit/", dashboard_product_edit, name="dashboard-product-edit"),
    path("products/<prd:public_id>/delete/", dashboard_product_delete, name="dashboard-product-delete"),

    path("inventory/", dashboard_inventory_list, name="dashboard-inventory"),
    path("customers/", dashboard_customers_list, name="dashboard-customers"),
    path("attributes/", dashboard_attributes_list, name="dashboard-attributes"),
    path("attributes/<int:attribute_id>/", dashboard_attribute_values_manage, name="dashboard-attribute-values"),
]
