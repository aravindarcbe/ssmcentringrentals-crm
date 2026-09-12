from django import forms

from .models import RentalTransaction, RentalLineItem


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
