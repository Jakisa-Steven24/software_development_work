import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()

PHONE_PATTERN = re.compile(r"^[+0-9][0-9\s()\-]{6,31}$")


class SignUpForm(UserCreationForm):
    """Create a user account and, with it, a library membership."""

    first_name = forms.CharField(max_length=150, strip=True)
    last_name = forms.CharField(max_length=150, required=False, strip=True)
    email = forms.EmailField(required=False)
    phone_number = forms.CharField(max_length=32, strip=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "phone_number",
            "password1",
            "password2",
        )

    def clean_phone_number(self):
        phone = re.sub(r"\s+", " ", self.cleaned_data["phone_number"]).strip()
        if not PHONE_PATTERN.match(phone):
            raise forms.ValidationError(
                "Enter a valid phone number, for example +256 7XX XXX XXX."
            )
        return phone


class ReviewForm(forms.Form):
    RATING_CHOICES = [(i, f"{i} star{'s' if i != 1 else ''}") for i in range(5, 0, -1)]

    rating = forms.TypedChoiceField(choices=RATING_CHOICES, coerce=int, empty_value=None)
    comment = forms.CharField(
        max_length=1200,
        required=False,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "What did you think of this book? (optional)",
            }
        ),
    )
