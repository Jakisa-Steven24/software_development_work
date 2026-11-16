from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import LoanAdmin
from .models import (
    FINE_PER_DAY_UGX,
    LOAN_PERIOD_DAYS,
    MAX_UNRETURNED_BOOKS,
    Author,
    Book,
    Loan,
    Member,
)

User = get_user_model()


def make_user(username, password="test-pass-123", **extra):
    return User.objects.create_user(username=username, password=password, **extra)


def make_member(username, membership_number, phone="+256700000000", **user_extra):
    user = make_user(username, **user_extra)
    return Member.objects.create(
        user=user,
        membership_number=membership_number,
        phone_number=phone,
    )


def make_book(title="A Test Title", isbn="9780000000001", total=2, authors=()):
    book = Book.objects.create(
        title=title,
        isbn=isbn,
        publication_year=2020,
        total_copies=total,
        available_copies=total,
    )
    if authors:
        book.authors.set(authors)
    return book


class ModelTests(TestCase):
    def test_available_copies_cannot_exceed_total(self):
        book = Book(
            title="Overstock",
            isbn="9780000000002",
            publication_year=2021,
            total_copies=1,
            available_copies=2,
        )
        with self.assertRaises(Exception):
            book.full_clean()

    def test_due_date_is_fourteen_days_after_borrow(self):
        member = make_member("alice", "M-001")
        book = make_book()
        loan = Loan.objects.create(member=member, book=book)
        expected = timezone.localtime(loan.borrowed_at).date() + timedelta(days=LOAN_PERIOD_DAYS)
        self.assertEqual(loan.due_date, expected)
        self.assertEqual(LOAN_PERIOD_DAYS, 14)

    def test_overdue_days_and_fine(self):
        member = make_member("bob", "M-002")
        book = make_book(title="Late Book", isbn="9780000000003")
        loan = Loan.objects.create(member=member, book=book)
        loan.due_date = timezone.localdate() - timedelta(days=4)
        loan.save(update_fields=("due_date",))
        self.assertEqual(loan.overdue_days, 4)
        self.assertEqual(loan.fine_owed, 4 * FINE_PER_DAY_UGX)
        self.assertEqual(FINE_PER_DAY_UGX, 500)
        self.assertTrue(loan.is_overdue)

    def test_returned_loan_is_not_overdue_and_fine_frozen(self):
        member = make_member("carol", "M-003")
        book = make_book(title="Returned Book", isbn="9780000000004")
        past = timezone.now() - timedelta(days=20)
        loan = Loan.objects.create(member=member, book=book)
        loan.due_date = past.date()
        loan.returned_at = past + timedelta(days=3)
        loan.save(update_fields=("due_date", "returned_at"))
        self.assertFalse(loan.is_overdue)
        self.assertEqual(loan.overdue_days, 3)
        self.assertEqual(loan.fine_owed, 3 * FINE_PER_DAY_UGX)


class CatalogViewTests(TestCase):
    def setUp(self):
        self.book = make_book(
            title="The Community Shelf",
            isbn="9780000000100",
            authors=[Author.objects.create(name="Nalwoga Sarah")],
        )

    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Community Shelf")

    def test_catalog_search_by_title(self):
        response = self.client.get(reverse("catalog"), {"q": "community shelf"})
        self.assertContains(response, "The Community Shelf")
        response = self.client.get(reverse("catalog"), {"q": "nonexistent-title-xyz"})
        self.assertNotContains(response, "The Community Shelf")

    def test_catalog_search_by_isbn(self):
        response = self.client.get(reverse("catalog"), {"q": "9780000000100"})
        self.assertContains(response, "The Community Shelf")

    def test_catalog_search_by_author(self):
        response = self.client.get(reverse("catalog"), {"q": "Nalwoga"})
        self.assertContains(response, "The Community Shelf")

    def test_catalog_availability_filter(self):
        self.book.available_copies = 0
        self.book.save()
        response = self.client.get(reverse("catalog"), {"availability": "available"})
        self.assertNotContains(response, "The Community Shelf")


class BorrowFlowTests(TestCase):
    def setUp(self):
        self.member = make_member("reader", "M-100")
        self.book = make_book(title="Borrowable", isbn="9780000000200", total=2)
        self.client.login(username="reader", password="test-pass-123")

    def test_borrow_decrements_stock(self):
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]), follow=True)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        self.assertEqual(Loan.objects.count(), 1)
        self.assertContains(response, "You borrowed")

    def test_borrow_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Loan.objects.count(), 0)

    def test_borrow_rejects_get(self):
        response = self.client.get(reverse("borrow_book", args=[self.book.pk]))
        self.assertEqual(response.status_code, 403)

    def test_borrow_fails_when_no_copies_available(self):
        self.book.available_copies = 0
        self.book.save()
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]), follow=True)
        self.assertEqual(Loan.objects.count(), 0)
        self.assertContains(response, "no available copies")

    def test_borrow_limited_to_three_unreturned_books(self):
        for index in range(MAX_UNRETURNED_BOOKS):
            extra = make_book(title=f"Extra {index}", isbn=f"97800000003{index:02d}")
            Loan.objects.create(member=self.member, book=extra)
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]), follow=True)
        self.assertEqual(Loan.objects.filter(member=self.member).count(), MAX_UNRETURNED_BOOKS)
        self.assertContains(response, "unreturned books")

    def test_borrow_requires_membership(self):
        make_user("nomember", password="test-pass-123")
        self.client.login(username="nomember", password="test-pass-123")
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]), follow=True)
        self.assertEqual(Loan.objects.count(), 0)
        self.assertContains(response, "not linked to a library membership")

    def test_returned_loans_do_not_count_toward_limit(self):
        for index in range(MAX_UNRETURNED_BOOKS):
            extra = make_book(title=f"Done {index}", isbn=f"97800000004{index:02d}")
            loan = Loan.objects.create(member=self.member, book=extra)
            loan.returned_at = timezone.now()
            loan.save(update_fields=("returned_at",))
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]), follow=True)
        self.assertEqual(Loan.objects.filter(member=self.member, returned_at__isnull=True).count(), 1)
        self.assertContains(response, "You borrowed")


class ReturnFlowTests(TestCase):
    def setUp(self):
        self.member = make_member("returner", "M-200")
        self.book = make_book(title="Returnable", isbn="9780000000500", total=1)
        self.book.available_copies = 0
        self.book.save()
        self.loan = Loan.objects.create(member=self.member, book=self.book)
        self.client.login(username="returner", password="test-pass-123")

    def test_return_restores_stock(self):
        response = self.client.post(reverse("return_loan", args=[self.loan.pk]), follow=True)
        self.book.refresh_from_db()
        self.loan.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        self.assertIsNotNone(self.loan.returned_at)
        self.assertContains(response, "has been returned")

    def test_return_is_idempotent(self):
        self.client.post(reverse("return_loan", args=[self.loan.pk]))
        response = self.client.post(reverse("return_loan", args=[self.loan.pk]), follow=True)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        self.assertContains(response, "already marked as returned")

    def test_return_rejects_get(self):
        response = self.client.get(reverse("return_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_return_another_members_loan(self):
        other = make_member("other", "M-201")
        other_book = make_book(title="Not Yours", isbn="9780000000501")
        other_loan = Loan.objects.create(member=other, book=other_book)
        response = self.client.post(reverse("return_loan", args=[other_loan.pk]))
        self.assertEqual(response.status_code, 403)

    def test_late_return_reports_fine(self):
        self.loan.due_date = timezone.localdate() - timedelta(days=2)
        self.loan.save(update_fields=("due_date",))
        response = self.client.post(reverse("return_loan", args=[self.loan.pk]), follow=True)
        self.assertContains(response, f"UGX {2 * FINE_PER_DAY_UGX:,}")


class OverdueDeskTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", password="test-pass-123", is_staff=True)
        self.member = make_member("latemember", "M-300")
        self.book = make_book(title="Overdue Gem", isbn="9780000000600")
        self.loan = Loan.objects.create(member=self.member, book=self.book)
        self.loan.due_date = timezone.localdate() - timedelta(days=6)
        self.loan.save(update_fields=("due_date",))

    def test_overdue_page_requires_staff(self):
        self.client.login(username="latemember", password="test-pass-123")
        response = self.client.get(reverse("overdue_loans"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_overdue_page_lists_fine(self):
        self.client.login(username="staff1", password="test-pass-123")
        response = self.client.get(reverse("overdue_loans"))
        self.assertContains(response, "Overdue Gem")
        self.assertContains(response, f"UGX {6 * FINE_PER_DAY_UGX:,}")
        self.assertContains(response, "M-300")

    def test_overdue_page_search(self):
        self.client.login(username="staff1", password="test-pass-123")
        response = self.client.get(reverse("overdue_loans"), {"q": "Overdue Gem"})
        self.assertContains(response, "Overdue Gem")
        response = self.client.get(reverse("overdue_loans"), {"q": "no-such-thing"})
        self.assertNotContains(response, "Overdue Gem")

    def test_returned_loans_do_not_appear(self):
        self.loan.returned_at = timezone.now()
        self.loan.save(update_fields=("returned_at",))
        self.client.login(username="staff1", password="test-pass-123")
        response = self.client.get(reverse("overdue_loans"))
        self.assertNotContains(response, "Overdue Gem")


class AdminConfigurationTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.loan_admin = LoanAdmin(Loan, self.site)

    def test_book_admin_searches_title_and_isbn(self):
        from .admin import BookAdmin

        book_admin = BookAdmin(Book, self.site)
        self.assertIn("title", book_admin.search_fields)
        self.assertIn("isbn", book_admin.search_fields)

    def test_loan_admin_filters_by_return_status(self):
        filter_names = [getattr(f, "parameter_name", f) for f in self.loan_admin.list_filter]
        self.assertIn("return_status", filter_names)

    def test_loan_admin_disables_add_and_delete(self):
        request = self.client.get("/admin/").wsgi_request  # request is unused by both methods
        self.assertFalse(self.loan_admin.has_add_permission(request))
        self.assertFalse(self.loan_admin.has_delete_permission(request))


class StarterCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from io import StringIO
        from django.core.management import call_command

        call_command("seed_catalog", stdout=StringIO())

    def test_starter_collection_has_authors_summaries_and_stock(self):
        self.assertEqual(Book.objects.count(), 9)
        self.assertEqual(Author.objects.count(), 7)
        for book in Book.objects.all():
            self.assertTrue(book.authors.exists())
            self.assertTrue(book.description)
            self.assertTrue(book.genre)
            self.assertEqual(book.total_copies, 3)
            self.assertEqual(book.available_copies, 3)
            book.full_clean()
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Loan.objects.count(), 0)

    def test_rerun_preserves_catalogue_edits_and_borrowed_stock(self):
        from io import StringIO
        from django.core.management import call_command

        book = Book.objects.get(title="Kintu")
        book.title = "Kintu — library copy"
        book.description = "Librarian's reading notes."
        book.available_copies = 1
        book.save()
        author_ids = list(book.authors.values_list("pk", flat=True))
        call_command("seed_catalog", stdout=StringIO())
        book.refresh_from_db()
        self.assertEqual(Book.objects.count(), 9)
        self.assertEqual(Author.objects.count(), 7)
        self.assertEqual(book.title, "Kintu — library copy")
        self.assertEqual(book.description, "Librarian's reading notes.")
        self.assertEqual(book.available_copies, 1)
        self.assertEqual(list(book.authors.values_list("pk", flat=True)), author_ids)

    def test_seeded_titles_are_searchable(self):
        for query in ("Kintu", "Makumbi", "9781945492010"):
            response = self.client.get(reverse("catalog"), {"q": query})
            self.assertContains(response, "Kintu")

    def test_book_detail_displays_summary_and_genre(self):
        book = Book.objects.get(title="Kintu")
        response = self.client.get(reverse("book_detail", args=[book.pk]))
        self.assertContains(response, book.description)
        self.assertContains(response, book.genre)
        self.assertContains(response, "Jennifer Nansubuga Makumbi")

    def test_home_has_two_letter_monogram_and_real_book_links(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, '<span class="brand-mark" aria-hidden="true">CS</span>', count=2)
        self.assertContains(response, 'class="shelf-book"', count=3)
        self.assertNotContains(response, "✳")
        self.assertNotContains(response, "stack-book")

    def test_starter_book_can_be_borrowed(self):
        member = make_member("starter-reader", "M-STARTER")
        self.client.force_login(member.user)
        book = Book.objects.get(title="Kintu")
        response = self.client.post(reverse("borrow_book", args=[book.pk]), follow=True)
        self.assertContains(response, "You borrowed")
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 2)
        self.assertTrue(Loan.objects.filter(member=member, book=book).exists())


class SignUpTests(TestCase):
    def test_signup_page_loads_with_button_friendly_copy(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your")
        self.assertContains(response, "phone")

    def test_signup_creates_user_membership_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Nakato",
                "last_name": "Peace",
                "username": "nakato",
                "email": "nakato@example.com",
                "phone_number": "+256 701 234 567",
                "password1": "read-with-me-2026",
                "password2": "read-with-me-2026",
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get(username="nakato")
        member = Member.objects.get(user=user)
        self.assertTrue(member.membership_number.startswith("CS-"))
        self.assertEqual(member.phone_number, "+256 701 234 567")
        self.assertContains(response, "Welcome to Community Shelf")
        # The new member is signed in straight away and can reach the member area.
        response = self.client.get(reverse("my_loans"))
        self.assertEqual(response.status_code, 200)

    def test_signup_rejects_weak_or_mismatched_password(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Test",
                "username": "badpass",
                "phone_number": "+256 700 000 000",
                "password1": "12345678",
                "password2": "87654321",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="badpass").exists())

    def test_signup_rejects_invalid_phone(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Test",
                "username": "badphone",
                "phone_number": "not-a-phone",
                "password1": "read-with-me-2026",
                "password2": "read-with-me-2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="badphone").exists())

    def test_signup_button_appears_in_header_for_anonymous_users(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, ">Sign up<")
        self.assertContains(response, reverse("signup"))


class ReviewTests(TestCase):
    def setUp(self):
        self.member = make_member("reviewer", "M-200")
        self.book = make_book(title="Reviewable", isbn="9780000000300")
        self.client.force_login(self.member.user)

    def test_member_can_post_a_review(self):
        response = self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "5", "comment": "A beautiful story."},
            follow=True,
        )
        self.assertContains(response, "Your review of")
        review = self.book.reviews.get(member=self.member)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "A beautiful story.")

    def test_review_is_one_per_member_and_updates_in_place(self):
        for rating in ("2", "4"):
            self.client.post(
                reverse("post_review", args=[self.book.pk]),
                {"rating": rating, "comment": "Changed my mind."},
            )
        self.assertEqual(self.book.reviews.count(), 1)
        self.assertEqual(self.book.reviews.get().rating, 4)

    def test_average_rating_is_shown_on_book_detail(self):
        self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "4", "comment": "Solid read."},
        )
        response = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(response, "4.0")
        self.assertContains(response, "Solid read.")

    def test_invalid_rating_is_rejected(self):
        response = self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "9", "comment": "Off the scale."},
            follow=True,
        )
        self.assertContains(response, "between 1 and 5")
        self.assertEqual(self.book.reviews.count(), 0)

    def test_member_can_delete_own_review(self):
        self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "3", "comment": "It was okay."},
        )
        review = self.book.reviews.get()
        self.client.post(reverse("delete_review", args=[review.pk]))
        self.assertEqual(self.book.reviews.count(), 0)

    def test_other_member_cannot_delete_my_review(self):
        self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "3", "comment": "Keep this one."},
        )
        review = self.book.reviews.get()
        other = make_member("intruder", "M-201")
        self.client.force_login(other.user)
        response = self.client.post(reverse("delete_review", args=[review.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.book.reviews.count(), 1)

    def test_review_form_requires_membership(self):
        plain_user = make_user("plainuser")
        self.client.force_login(plain_user)
        response = self.client.post(
            reverse("post_review", args=[self.book.pk]),
            {"rating": "5", "comment": "Hi"},
            follow=True,
        )
        self.assertContains(response, "Only library members can review")


class RenewalTests(TestCase):
    def setUp(self):
        self.member = make_member("renewer", "M-300")
        self.book = make_book(title="Renewable", isbn="9780000000400", total=1)
        self.client.force_login(self.member.user)
        self.client.post(reverse("borrow_book", args=[self.book.pk]))
        self.loan = Loan.objects.get(member=self.member, book=self.book)

    def test_renewal_extends_due_date_by_fourteen_days(self):
        original_due = self.loan.due_date
        response = self.client.post(reverse("renew_loan", args=[self.loan.pk]), follow=True)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, original_due + timedelta(days=LOAN_PERIOD_DAYS))
        self.assertEqual(self.loan.renewed_count, 1)
        self.assertIsNotNone(self.loan.renewed_at)
        self.assertContains(response, "renewed")

    def test_only_one_renewal_is_allowed(self):
        self.client.post(reverse("renew_loan", args=[self.loan.pk]))
        self.loan.refresh_from_db()
        original_due = self.loan.due_date
        response = self.client.post(reverse("renew_loan", args=[self.loan.pk]), follow=True)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, original_due)
        self.assertEqual(self.loan.renewed_count, 1)
        self.assertContains(response, "one renewal")

    def test_overdue_loan_cannot_be_renewed(self):
        self.loan.due_date = timezone.localdate() - timedelta(days=1)
        self.loan.save(update_fields=("due_date",))
        response = self.client.post(reverse("renew_loan", args=[self.loan.pk]), follow=True)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.renewed_count, 0)
        self.assertContains(response, "cannot be renewed")

    def test_renewal_renews_own_loans_only(self):
        other = make_member("someoneelse", "M-301")
        self.client.force_login(other.user)
        response = self.client.post(reverse("renew_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 403)


class ReadingListTests(TestCase):
    def setUp(self):
        self.member = make_member("shelver", "M-400")
        self.book = make_book(title="Shelved", isbn="9780000000500")
        self.client.force_login(self.member.user)

    def test_toggle_adds_and_removes_book_from_shelf(self):
        self.client.post(reverse("toggle_reading_list", args=[self.book.pk]))
        self.assertTrue(self.member.reading_list.filter(book=self.book).exists())
        self.client.post(reverse("toggle_reading_list", args=[self.book.pk]))
        self.assertFalse(self.member.reading_list.filter(book=self.book).exists())

    def test_my_shelf_page_lists_saved_books(self):
        self.client.post(reverse("toggle_reading_list", args=[self.book.pk]))
        response = self.client.get(reverse("my_shelf"))
        self.assertContains(response, "Shelved")

    def test_my_shelf_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("my_shelf"))
        self.assertEqual(response.status_code, 302)


class StaffPickTests(TestCase):
    def test_staff_pick_badge_is_shown(self):
        book = make_book(title="Pick of the month", isbn="9780000000600")
        book.staff_pick = True
        book.save(update_fields=("staff_pick",))
        response = self.client.get(reverse("book_detail", args=[book.pk]))
        self.assertContains(response, "Staff pick")
        response = self.client.get(reverse("catalog"), {"staff_picks": "1"})
        self.assertContains(response, "Pick of the month")

    def test_staff_picks_filter_excludes_regular_titles(self):
        picked = make_book(title="Picked Title", isbn="9780000000700")
        picked.staff_pick = True
        picked.save(update_fields=("staff_pick",))
        make_book(title="Regular Title", isbn="9780000000701")
        response = self.client.get(reverse("catalog"), {"staff_picks": "1"})
        self.assertContains(response, "Picked Title")
        self.assertNotContains(response, "Regular Title")


class MemberStatsTests(TestCase):
    def test_loans_page_shows_stats_and_badges(self):
        member = make_member("collector", "M-500")
        book = make_book(title="Stats Book", isbn="9780000000800")
        self.client.force_login(member.user)
        self.client.post(reverse("borrow_book", args=[book.pk]))
        response = self.client.get(reverse("my_loans"))
        self.assertContains(response, "books borrowed")
        self.assertContains(response, "on-time returns")
        self.assertContains(response, "First Borrow")
        self.assertContains(response, "Perfect Reader")


class DueSoonStaffDeskTests(TestCase):
    def test_staff_desk_lists_books_coming_due(self):
        staff = make_user("deskstaff", is_staff=True)
        member = make_member("borrower", "M-600")
        book = make_book(title="Due Soon Book", isbn="9780000000900")
        self.client.force_login(member.user)
        self.client.post(reverse("borrow_book", args=[book.pk]))
        loan = Loan.objects.get(member=member, book=book)
        loan.due_date = timezone.localdate() + timedelta(days=3)
        loan.save(update_fields=("due_date",))
        self.client.force_login(staff)
        response = self.client.get(reverse("overdue_loans"))
        self.assertContains(response, "Due in the next 7 days")
        self.assertContains(response, "Due Soon Book")
