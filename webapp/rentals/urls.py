from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="rentals/login.html", redirect_authenticated_user=True), name="login"),
    path("", views.dashboard, name="dashboard"),
    path("manage/", views.manage_home, name="manage"),
    path("rentals/new/", views.rental_new, name="rental_new"),
    path("rentals/<int:pk>/", views.rental_detail, name="rental_detail"),
    path("rentals/<int:pk>/return/", views.rental_return, name="rental_return"),
    path("search/", views.global_search, name="search"),

    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/new/", views.CustomerCreateView.as_view(), name="customer_new"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_edit"),
    path("customers/<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),

    path("materials/", views.MaterialListView.as_view(), name="material_list"),
    path("materials/new/", views.MaterialCreateView.as_view(), name="material_new"),
    path("materials/<int:pk>/edit/", views.MaterialUpdateView.as_view(), name="material_edit"),
    path("materials/<int:pk>/delete/", views.MaterialDeleteView.as_view(), name="material_delete"),

    path("receipts/", views.ReceiptListView.as_view(), name="receipt_list"),
    path("receipts/new/", views.ReceiptCreateView.as_view(), name="receipt_new"),
    path("receipts/<int:pk>/edit/", views.ReceiptUpdateView.as_view(), name="receipt_edit"),
    path("receipts/<int:pk>/delete/", views.ReceiptDeleteView.as_view(), name="receipt_delete"),

    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/new/", views.PaymentCreateView.as_view(), name="payment_new"),
    path("payments/<int:pk>/edit/", views.PaymentUpdateView.as_view(), name="payment_edit"),
    path("payments/<int:pk>/delete/", views.PaymentDeleteView.as_view(), name="payment_delete"),

    path("purchases/", views.ProductPurchaseListView.as_view(), name="purchase_list"),
    path("purchases/new/", views.ProductPurchaseCreateView.as_view(), name="purchase_new"),
    path("purchases/<int:pk>/edit/", views.ProductPurchaseUpdateView.as_view(), name="purchase_edit"),
    path("purchases/<int:pk>/delete/", views.ProductPurchaseDeleteView.as_view(), name="purchase_delete"),

    path("expenses/", views.DailyExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.DailyExpenseCreateView.as_view(), name="expense_new"),
    path("expenses/<int:pk>/edit/", views.DailyExpenseUpdateView.as_view(), name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.DailyExpenseDeleteView.as_view(), name="expense_delete"),
]
