from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

LOAN_PERIOD_DAYS = 21
MAX_UNRETURNED_BOOKS = 4
FINE_PER_DAY_UGX = 1_000


class Author(models.Model):
    name = models.CharField(max_length=160)
    biography = models.TextField("biography", blank=True)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "author"
        verbose_name_plural = "authors"

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255, db_index=True)
    genre = models.CharField("subject area", max_length=80, blank=True)
    description = models.TextField("summary", blank=True)
    isbn = models.CharField("ISBN", max_length=20, unique=True)
    publication_year = models.PositiveSmallIntegerField("year published")
    authors = models.ManyToManyField(Author, related_name="books", blank=True)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", "pk")
        verbose_name = "title"
        verbose_name_plural = "titles"
        constraints = [
            models.CheckConstraint(
                condition=Q(available_copies__lte=F("total_copies")),
                name="book_available_not_above_total",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.total_copies is not None
            and self.available_copies is not None
            and self.available_copies > self.total_copies
        ):
            raise ValidationError(
                {"available_copies": "Available copies cannot exceed the total copies."}
            )

    def __str__(self):
        return f"{self.title} ({self.publication_year})"


class Member(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member",
    )
    membership_number = models.CharField("student number", max_length=32, unique=True)
    phone_number = models.CharField("phone number", max_length=32)
    joined_at = models.DateTimeField("registered on", auto_now_add=True)

    class Meta:
        ordering = ("membership_number",)
        verbose_name = "student"
        verbose_name_plural = "students"

    def __str__(self):
        return f"{self.membership_number} — {self.user.get_full_name() or self.user.username}"


class Loan(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="loans",
        verbose_name="student",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name="loans",
        verbose_name="title",
    )
    borrowed_at = models.DateTimeField("borrowed on", default=timezone.now, editable=False)
    due_date = models.DateField("due back", editable=False)
    returned_at = models.DateTimeField("returned on", null=True, blank=True)

    class Meta:
        ordering = ("-borrowed_at", "-pk")
        verbose_name = "borrowing"
        verbose_name_plural = "borrowings"
        indexes = [
            models.Index(fields=("returned_at", "due_date"), name="loan_status_due_idx"),
            models.Index(fields=("member", "returned_at"), name="loan_member_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.due_date:
            borrowed_at = self.borrowed_at or timezone.now()
            if timezone.is_aware(borrowed_at):
                borrowed_on = timezone.localtime(borrowed_at).date()
            else:
                borrowed_on = borrowed_at.date()
            self.due_date = borrowed_on + timedelta(days=LOAN_PERIOD_DAYS)
        super().save(*args, **kwargs)

    @property
    def is_returned(self):
        return self.returned_at is not None

    @property
    def is_overdue(self):
        return not self.is_returned and self.due_date < timezone.localdate()

    @property
    def overdue_days(self):
        if self.returned_at and timezone.is_aware(self.returned_at):
            through_date = timezone.localtime(self.returned_at).date()
        elif self.returned_at:
            through_date = self.returned_at.date()
        else:
            through_date = timezone.localdate()
        return max((through_date - self.due_date).days, 0)

    @property
    def fine_owed(self):
        return self.overdue_days * FINE_PER_DAY_UGX

    def __str__(self):
        status = "returned" if self.is_returned else "on loan"
        return f"{self.book.title} — {self.member.membership_number} ({status})"
