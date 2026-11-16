from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    MAX_UNRETURNED_BOOKS,
    Book,
    Loan,
    Member,
)


def _member_for_user(user):
    if not user.is_authenticated:
        return None
    try:
        return Member.objects.select_related("user").get(user_id=user.pk)
    except Member.DoesNotExist:
        return None


def home(request):
    context = {
        "book_count": Book.objects.count(),
        "available_title_count": Book.objects.filter(available_copies__gt=0).count(),
        "member_count": Member.objects.count(),
        "latest_books": Book.objects.prefetch_related("authors").order_by("-created_at")[:3],
    }
    return render(request, "library/home.html", context)


def book_list(request):
    query = request.GET.get("q", "").strip()
    availability = request.GET.get("availability", "all")
    books = Book.objects.prefetch_related("authors")

    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(isbn__icontains=query)
            | Q(authors__name__icontains=query)
        ).distinct()
    if availability == "available":
        books = books.filter(available_copies__gt=0)

    page_obj = Paginator(books, 12).get_page(request.GET.get("page"))
    return render(
        request,
        "library/book_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "availability": availability,
            "result_count": page_obj.paginator.count,
        },
    )


def book_detail(request, pk):
    book = get_object_or_404(Book.objects.prefetch_related("authors"), pk=pk)
    member = _member_for_user(request.user)
    active_loan_count = 0
    if member:
        active_loan_count = member.loans.filter(returned_at__isnull=True).count()

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
        },
    )


@login_required
def my_loans(request):
    member = _member_for_user(request.user)
    if member is None:
        messages.info(
            request,
            "Your account is not linked to a library membership yet. Please ask library staff for help.",
        )
        active_loans = []
        returned_loans = []
    else:
        loans = member.loans.select_related("book").all()
        active_loans = loans.filter(returned_at__isnull=True)
        returned_loans = loans.filter(returned_at__isnull=False)

    return render(
        request,
        "library/my_loans.html",
        {
            "member": member,
            "active_loans": active_loans,
            "returned_loans": returned_loans,
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
    return render(
        request,
        "library/overdue_loans.html",
        {
            "overdue_loans": overdue_list,
            "overdue_count": len(overdue_list),
            "total_fines": total_fines,
            "query": query,
        },
    )
