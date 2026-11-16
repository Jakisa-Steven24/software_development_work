from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ReviewForm, SignUpForm
from .models import (
    LOAN_PERIOD_DAYS,
    MAX_LOAN_RENEWALS,
    MAX_UNRETURNED_BOOKS,
    Book,
    Loan,
    Member,
    ReadingListItem,
    Review,
)


def _member_for_user(user):
    if not user.is_authenticated:
        return None
    try:
        return Member.objects.select_related("user").get(user_id=user.pk)
    except Member.DoesNotExist:
        return None


def _rating_annotations(queryset):
    return queryset.annotate(
        avg_rating=Avg("reviews__rating"),
        review_count=Count("reviews", distinct=True),
    )


def _unique_membership_number(user):
    base = f"CS-{user.pk:04d}"
    candidate, suffix = base, 2
    while Member.objects.filter(membership_number=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def home(request):
    context = {
        "book_count": Book.objects.count(),
        "available_title_count": Book.objects.filter(available_copies__gt=0).count(),
        "member_count": Member.objects.count(),
        "latest_books": _rating_annotations(
            Book.objects.prefetch_related("authors").order_by("-created_at")
        )[:3],
        "staff_picks": _rating_annotations(
            Book.objects.filter(staff_pick=True).prefetch_related("authors")
        )[:3],
    }
    return render(request, "library/home.html", context)


def book_list(request):
    query = request.GET.get("q", "").strip()
    availability = request.GET.get("availability", "all")
    genre = request.GET.get("genre", "").strip()
    staff_picks_only = request.GET.get("staff_picks") == "1"
    books = Book.objects.prefetch_related("authors")

    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(isbn__icontains=query)
            | Q(authors__name__icontains=query)
        ).distinct()
    if availability == "available":
        books = books.filter(available_copies__gt=0)
    if genre:
        books = books.filter(genre__iexact=genre)
    if staff_picks_only:
        books = books.filter(staff_pick=True)

    books = _rating_annotations(books).order_by("title", "pk")

    page_obj = Paginator(books, 12).get_page(request.GET.get("page"))
    genres = list(
        Book.objects.exclude(genre="")
        .values_list("genre", flat=True)
        .distinct()
        .order_by("genre")
    )
    return render(
        request,
        "library/book_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "availability": availability,
            "genre": genre,
            "genres": genres,
            "staff_picks_only": staff_picks_only,
            "result_count": page_obj.paginator.count,
        },
    )


def book_detail(request, pk):
    book = get_object_or_404(
        _rating_annotations(Book.objects.prefetch_related("authors")),
        pk=pk,
    )
    member = _member_for_user(request.user)
    active_loan_count = 0
    member_review = None
    saved_to_shelf = False
    if member:
        active_loan_count = member.loans.filter(returned_at__isnull=True).count()
        member_review = Review.objects.filter(book=book, member=member).first()
        saved_to_shelf = ReadingListItem.objects.filter(member=member, book=book).exists()

    review_form = ReviewForm(
        initial={
            "rating": member_review.rating if member_review else 5,
            "comment": member_review.comment if member_review else "",
        }
    )
    reviews = book.reviews.select_related("member__user").all()

    return render(
        request,
        "library/book_detail.html",
        {
            "book": book,
            "member": member,
            "active_loan_count": active_loan_count,
            "loan_limit": MAX_UNRETURNED_BOOKS,
            "can_borrow": bool(
                member
                and active_loan_count < MAX_UNRETURNED_BOOKS
                and book.available_copies > 0
            ),
            "reviews": reviews,
            "review_form": review_form,
            "member_review": member_review,
            "saved_to_shelf": saved_to_shelf,
        },
    )


@login_required
def my_loans(request):
    member = _member_for_user(request.user)
    stats = None
    badges = []
    due_soon_count = 0
    if member is None:
        messages.info(
            request,
            "Your account is not linked to a library membership yet. Please ask library staff for help.",
        )
        active_loans = []
        returned_loans = []
    else:
        loans = list(member.loans.select_related("book").all())
        active_loans = [loan for loan in loans if not loan.is_returned]
        returned_loans = [loan for loan in loans if loan.is_returned]
        today = timezone.localdate()
        for loan in active_loans:
            loan.days_until_due = (loan.due_date - today).days
        due_soon_count = sum(
            1 for loan in active_loans if not loan.is_overdue and loan.days_until_due <= 3
        )

        on_time_returns = sum(
            1
            for loan in returned_loans
            if (timezone.localtime(loan.returned_at).date() if timezone.is_aware(loan.returned_at) else loan.returned_at.date())
            <= loan.due_date
        )
        late_returns = len(returned_loans) - on_time_returns
        shelf_count = member.reading_list.count()
        review_count = member.reviews.count()
        total_borrowed = len(loans)
        stats = {
            "total_borrowed": total_borrowed,
            "on_time_returns": on_time_returns,
            "late_returns": late_returns,
            "active_count": len(active_loans),
            "due_soon_count": due_soon_count,
            "shelf_count": shelf_count,
            "review_count": review_count,
        }
        badges = [
            {
                "glyph": "★",
                "name": "First Borrow",
                "description": "Borrowed your first book",
                "earned": total_borrowed >= 1,
            },
            {
                "glyph": "✓",
                "name": "On the Dot",
                "description": "3 books returned on time",
                "earned": on_time_returns >= 3,
            },
            {
                "glyph": "♦",
                "name": "Perfect Reader",
                "description": "5+ returns, none of them late",
                "earned": on_time_returns >= 5 and late_returns == 0,
            },
            {
                "glyph": "✦",
                "name": "Bookworm",
                "description": "Borrowed 10 books in total",
                "earned": total_borrowed >= 10,
            },
            {
                "glyph": "✎",
                "name": "Reviewer",
                "description": "Wrote your first review",
                "earned": review_count >= 1,
            },
            {
                "glyph": "▧",
                "name": "Shelf Builder",
                "description": "3 books saved to your shelf",
                "earned": shelf_count >= 3,
            },
        ]

    return render(
        request,
        "library/my_loans.html",
        {
            "member": member,
            "active_loans": active_loans,
            "returned_loans": returned_loans,
            "stats": stats,
            "badges": badges,
            "due_soon_count": due_soon_count,
            "max_renewals": MAX_LOAN_RENEWALS,
        },
    )


@login_required
@transaction.atomic
def borrow_book(request, book_id):
    """Create a loan only after locking and checking the member and stock rows."""
    if request.method != "POST":
        return HttpResponseForbidden("Borrowing must be submitted using the protected form.")

    try:
        member = Member.objects.select_for_update().get(user_id=request.user.pk)
    except Member.DoesNotExist:
        messages.error(
            request,
            "Your account is not linked to a library membership. Please contact library staff.",
        )
        return redirect("book_detail", pk=book_id)

    try:
        book = Book.objects.select_for_update().get(pk=book_id)
    except Book.DoesNotExist as exc:
        raise Http404("Book not found") from exc

    active_count = member.loans.filter(returned_at__isnull=True).count()
    if active_count >= MAX_UNRETURNED_BOOKS:
        messages.error(
            request,
            f"You already have {MAX_UNRETURNED_BOOKS} unreturned books. Return one before borrowing again.",
        )
    elif book.available_copies < 1:
        messages.error(request, "There are no available copies of this book right now.")
    else:
        loan = Loan.objects.create(member=member, book=book)
        book.available_copies -= 1
        book.save(update_fields=("available_copies", "updated_at"))
        messages.success(
            request,
            f"You borrowed “{book.title}”. Please return it by {loan.due_date.day} {loan.due_date:%b %Y}.",
        )

    return redirect("book_detail", pk=book.pk)


@login_required
@transaction.atomic
def return_loan(request, loan_id):
    """Return a member's own loan (or any loan for a staff user) exactly once."""
    if request.method != "POST":
        return HttpResponseForbidden("Returns must be submitted using the protected form.")

    try:
        loan = Loan.objects.select_for_update().select_related("member").get(pk=loan_id)
    except Loan.DoesNotExist as exc:
        raise Http404("Loan not found") from exc

    if loan.member.user_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("You can only return your own books.")

    if loan.returned_at:
        messages.info(request, f"“{loan.book.title}” was already marked as returned.")
    else:
        book = Book.objects.select_for_update().get(pk=loan.book_id)
        loan.returned_at = timezone.now()
        loan.save(update_fields=("returned_at",))
        # Keep the database constraint intact even if stock was manually edited by staff.
        if book.available_copies < book.total_copies:
            book.available_copies += 1
            book.save(update_fields=("available_copies", "updated_at"))

        if loan.fine_owed:
            messages.warning(
                request,
                f"“{book.title}” was returned {loan.overdue_days} day(s) late. "
                f"Fine owed: UGX {loan.fine_owed:,}.",
            )
        else:
            messages.success(request, f"“{book.title}” has been returned. Thank you!")

    return redirect("overdue_loans" if request.user.is_staff else "my_loans")


@login_required
@transaction.atomic
def renew_loan(request, loan_id):
    """Extend an active, non-overdue loan by the loan period — once per loan."""
    if request.method != "POST":
        return HttpResponseForbidden("Renewals must be submitted using the protected form.")

    try:
        loan = Loan.objects.select_for_update().select_related("member", "book").get(pk=loan_id)
    except Loan.DoesNotExist as exc:
        raise Http404("Loan not found") from exc

    if loan.member.user_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("You can only renew your own loans.")

    if loan.returned_at:
        messages.info(request, f"“{loan.book.title}” has already been returned.")
    elif loan.is_overdue:
        messages.error(
            request,
            f"“{loan.book.title}” is overdue, so it cannot be renewed. Please return it to the desk.",
        )
    elif loan.renewed_count >= MAX_LOAN_RENEWALS:
        messages.error(
            request,
            f"You have already used the one renewal allowed for “{loan.book.title}”.",
        )
    else:
        loan.due_date = loan.due_date + timedelta(days=LOAN_PERIOD_DAYS)
        loan.renewed_count += 1
        loan.renewed_at = timezone.now()
        loan.save(update_fields=("due_date", "renewed_count", "renewed_at"))
        messages.success(
            request,
            f"“{loan.book.title}” was renewed. New due date: {loan.due_date.day} {loan.due_date:%b %Y}.",
        )

    return redirect("my_loans")


@login_required
def toggle_reading_list(request, book_id):
    """Add or remove a book from the member's reading list."""
    if request.method != "POST":
        return HttpResponseForbidden("The reading list must be updated using the protected form.")

    member = _member_for_user(request.user)
    if member is None:
        messages.info(request, "Only library members can keep a reading list.")
        return redirect("book_detail", pk=book_id)

    book = get_object_or_404(Book, pk=book_id)
    item, created = ReadingListItem.objects.get_or_create(member=member, book=book)
    if created:
        messages.success(request, f"“{book.title}” was added to your shelf.")
    else:
        item.delete()
        messages.info(request, f"“{book.title}” was removed from your shelf.")

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("book_detail", pk=book.pk)


@login_required
def my_shelf(request):
    member = _member_for_user(request.user)
    books = []
    if member is None:
        messages.info(
            request,
            "Your account is not linked to a library membership yet. Please ask library staff for help.",
        )
    else:
        books = list(
            _rating_annotations(
                Book.objects.filter(reading_list_entries__member=member)
                .annotate(saved_at=Max("reading_list_entries__created_at"))
                .prefetch_related("authors")
                .order_by("-saved_at")
            )
        )

    return render(
        request,
        "library/my_shelf.html",
        {
            "member": member,
            "saved_books": books,
        },
    )


@login_required
def post_review(request, book_id):
    if request.method != "POST":
        return HttpResponseForbidden("Reviews must be submitted using the protected form.")

    member = _member_for_user(request.user)
    if member is None:
        messages.info(request, "Only library members can review books.")
        return redirect("book_detail", pk=book_id)

    book = get_object_or_404(Book, pk=book_id)
    form = ReviewForm(request.POST)
    if form.is_valid():
        Review.objects.update_or_create(
            book=book,
            member=member,
            defaults={
                "rating": form.cleaned_data["rating"],
                "comment": form.cleaned_data["comment"],
            },
        )
        messages.success(request, f"Thank you! Your review of “{book.title}” has been saved.")
    else:
        messages.error(request, "Please choose a rating between 1 and 5 stars.")

    return redirect("book_detail", pk=book.pk)


@login_required
def delete_review(request, review_id):
    if request.method != "POST":
        return HttpResponseForbidden("Reviews can only be deleted using the protected form.")

    review = get_object_or_404(Review.objects.select_related("member", "book"), pk=review_id)
    if review.member.user_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("You can only delete your own reviews.")

    book_id = review.book_id
    review.delete()
    messages.info(request, "Your review was deleted.")
    return redirect("book_detail", pk=book_id)


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            member = Member.objects.create(
                user=user,
                membership_number=_unique_membership_number(user),
                phone_number=form.cleaned_data["phone_number"],
            )
        login(request, user)
        display_name = user.first_name or user.username
        messages.success(
            request,
            f"Welcome to Community Shelf, {display_name}! "
            f"Your membership number is {member.membership_number} — keep it safe.",
        )
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("home")

    return render(request, "registration/signup.html", {"form": form})


@staff_member_required(login_url="login")
def overdue_loans(request):
    today = timezone.localdate()
    query = request.GET.get("q", "").strip()
    loans = Loan.objects.filter(
        returned_at__isnull=True,
        due_date__lt=today,
    ).select_related("book", "member", "member__user")
    if query:
        loans = loans.filter(
            Q(book__title__icontains=query)
            | Q(book__isbn__icontains=query)
            | Q(member__membership_number__icontains=query)
            | Q(member__user__username__icontains=query)
            | Q(member__user__first_name__icontains=query)
            | Q(member__user__last_name__icontains=query)
        )

    overdue_list = list(loans.order_by("due_date", "pk"))
    total_fines = sum(loan.fine_owed for loan in overdue_list)

    due_soon = list(
        Loan.objects.filter(
            returned_at__isnull=True,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        )
        .select_related("book", "member", "member__user")
        .order_by("due_date", "pk")
    )
    for loan in due_soon:
        loan.days_until_due = (loan.due_date - today).days

    return render(
        request,
        "library/overdue_loans.html",
        {
            "overdue_loans": overdue_list,
            "overdue_count": len(overdue_list),
            "total_fines": total_fines,
            "query": query,
            "due_soon": due_soon,
        },
    )
