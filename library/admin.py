from django import forms
from django.contrib import admin
from django.db.models import QuerySet

from .models import Author, Book, Loan, Member, Review


class BookAdminForm(forms.ModelForm):
    """Default a new title's available stock to its total stock."""

    class Meta:
        model = Book
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["available_copies"].required = False
            self.fields["available_copies"].initial = None

    def clean_available_copies(self):
        available = self.cleaned_data.get("available_copies")
        if available is None:
            return self.cleaned_data["total_copies"]
        return available


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count")
    search_fields = ("name",)

    @admin.display(description="Books")
    def book_count(self, author):
        return author.books.count()


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    form = BookAdminForm
    list_display = ("title", "isbn", "publication_year", "total_copies", "available_copies", "staff_pick")
    list_filter = ("genre", "publication_year", "authors", "staff_pick")
    actions = ("make_staff_pick", "remove_staff_pick")
    search_fields = ("title", "isbn")
    filter_horizontal = ("authors",)
    ordering = ("title",)

    @admin.action(description="Mark as staff pick")
    def make_staff_pick(self, request, queryset):
        queryset.update(staff_pick=True)

    @admin.action(description="Remove staff pick")
    def remove_staff_pick(self, request, queryset):
        queryset.update(staff_pick=False)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("membership_number", "member_name", "phone_number", "joined_at")
    search_fields = (
        "membership_number",
        "phone_number",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    list_select_related = ("user",)
    readonly_fields = ("joined_at",)

    @admin.display(description="Member", ordering="user__last_name")
    def member_name(self, member):
        return member.user.get_full_name() or member.user.username


class ReturnStatusFilter(admin.SimpleListFilter):
    title = "return status"
    parameter_name = "return_status"

    def lookups(self, request, model_admin):
        return (
            ("outstanding", "Not returned"),
            ("returned", "Returned"),
        )

    def queryset(self, request, queryset: QuerySet):
        if self.value() == "outstanding":
            return queryset.filter(returned_at__isnull=True)
        if self.value() == "returned":
            return queryset.filter(returned_at__isnull=False)
        return queryset


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "book",
        "member",
        "borrowed_at",
        "due_date",
        "returned_at",
        "fine_owed_display",
    )
    list_filter = (ReturnStatusFilter, "due_date")
    search_fields = (
        "book__title",
        "book__isbn",
        "member__membership_number",
        "member__user__username",
        "member__user__first_name",
        "member__user__last_name",
    )
    list_select_related = ("book", "member", "member__user")
    readonly_fields = ("borrowed_at", "due_date", "returned_at")
    date_hierarchy = "borrowed_at"
    ordering = ("due_date",)

    @admin.display(description="Fine owed", ordering="due_date")
    def fine_owed_display(self, loan):
        return f"UGX {loan.fine_owed:,}"

    def has_add_permission(self, request):
        # Loans must go through the borrowing flow so stock and member limits stay in sync.
        return False

    def has_delete_permission(self, request, obj=None):
        # Preserve the circulation history and avoid silently changing stock.
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("book", "member", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = (
        "book__title",
        "book__isbn",
        "member__membership_number",
        "member__user__username",
    )
    list_select_related = ("book", "member", "member__user")
    readonly_fields = ("created_at", "updated_at")
