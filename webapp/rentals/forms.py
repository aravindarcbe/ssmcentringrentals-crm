from django import forms

from .models import (
    Customer,
    DailyExpense,
    Material,
    Payment,
    ProductPurchase,
    Receipt,
    RentalLineItem,
    RentalTransaction,
)


class RentalTransactionForm(forms.ModelForm):
    class Meta:
        model = RentalTransaction
        fields = ["customer", "date_out", "discount", "remarks"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "date_out": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }


class DepositCollectedForm(forms.Form):
    amount_collected = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "place", "aadhar_number"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "place": forms.TextInput(attrs={"class": "form-control"}),
            "aadhar_number": forms.TextInput(attrs={"class": "form-control"}),
        }


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["category", "size_label", "ft_value", "default_rate_per_day", "total_stock_count", "available_count"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "size_label": forms.TextInput(attrs={"class": "form-control"}),
            "ft_value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "default_rate_per_day": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "total_stock_count": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "available_count": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        }


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ["transaction", "date", "amount", "payment_mode", "note"]
        widgets = {
            "transaction": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "payment_mode": forms.Select(attrs={"class": "form-select"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["date", "description", "payee", "amount", "payment_mode"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "payee": forms.TextInput(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "payment_mode": forms.Select(attrs={"class": "form-select"}),
        }


class ProductPurchaseForm(forms.ModelForm):
    class Meta:
        model = ProductPurchase
        fields = ["date", "category", "size_label", "count", "rate", "amount"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "size_label": forms.TextInput(attrs={"class": "form-control"}),
            "count": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


class DailyExpenseForm(forms.ModelForm):
    class Meta:
        model = DailyExpense
        fields = ["date", "category", "description", "amount", "payment_mode"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "payment_mode": forms.Select(attrs={"class": "form-select"}),
        }


RentalLineItemFormSet = forms.modelformset_factory(
    RentalLineItem,
    fields=["material", "count", "days_estimated", "rate"],
    extra=2,
    can_delete=True,
    widgets={
        "material": forms.Select(attrs={"class": "form-select form-select-sm"}),
        "count": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "1"}),
        "days_estimated": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "1"}),
        "rate": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    },
)
