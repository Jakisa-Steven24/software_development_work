# Community Shelf — Community Library Borrowing Register

A Django web application (template-based) that replaces the paper borrowing register of a
community library. Members can browse the catalogue, borrow books, and keep track of their
loans; library staff get an overdue-loans desk with live fine calculations, and a Django
admin configured for day-to-day cataloguing and circulation.

## Features

- **Books** — title, unique ISBN, year of publication, total and available copies.
  `available_copies ≤ total_copies` is enforced at both the model (`full_clean`) and the
  database (`CheckConstraint`) level.
- **Authors** — many-to-many with books (a book may have several authors and an author several books).
- **Members** — linked one-to-one to Django user accounts, with a unique membership number and a phone number.
- **Self-service signup** (`/accounts/signup/`) — visitors create their own login and get a
  membership number (e.g. `CS-0001`) assigned automatically. The header has **Sign in** / **Sign up**
  buttons, and new members are signed in straight after joining.
- **Ratings & reviews** — members can rate any book one to five stars and leave a short comment
  (one review per member per book, editable; staff can moderate in the admin). Average rating and
  review count appear on book cards and the book detail page.
- **Reading list ("My shelf")** — members save books to a personal shelf to read next, with a
  one-tap toggle on every book page and a dedicated `/my-shelf/` page.
- **Loan renewal** — an active, non-overdue loan can be renewed once, extending the due date by
  14 days from the current due date. Overdue loans cannot be renewed.
- **Member reading stats & badges** — the My loans page shows books borrowed, on-time returns,
  active loans and shelf size, plus six achievement badges (First Borrow, On the Dot, Perfect
  Reader, Bookworm, Reviewer, Shelf Builder).
- **Staff picks** — librarians can flag titles as staff picks (admin or bulk action); they get a
  ribbon on cards, a chip on the detail page, a home-page rail, and a filter in the catalogue.
- **Genre filter** — the catalogue can be filtered by genre alongside search, availability and the
  staff-picks toggle.
- **Borrowing rules**
  - Login required; POST-only, CSRF-protected form.
  - A copy must be available and the member must hold fewer than 3 unreturned loans.
  - Loans are due **14 days** after borrowing; late returns accrue **UGX 500 per overdue day**.
  - Stock is checked and decremented inside an atomic transaction with row locking
    (`select_for_update`) to prevent over-borrowing under concurrency.
- **Returns** — a member returns their own books (staff may return any loan); returning
  restores available stock exactly once (idempotent).
- **Staff overdue desk** (`/staff/overdue/`) — lists every overdue loan with member details,
  days late, and the fine owed (UGX 500 × days overdue), plus the total outstanding.
- **Staff due-soon panel** (`/staff/overdue/`) — in addition to the overdue desk, staff see every
  loan due in the next 7 days so they can nudge members before books go late.
- **Django admin** — search books by title or ISBN; filter loans by return status
  (plus due date); loan records are read-only / cannot be created or deleted through the
  admin so circulation history and stock stay consistent.
- **Member feedback** — Django messages framework is used throughout (borrow success,
  stock exhausted, loan limit reached, late-return fines, …).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_catalog      # optional starter collection: nine titles with authors and summaries
python manage.py createsuperuser   # e.g. a "librarian" staff account
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

For a local demo, create an account at <http://127.0.0.1:8000/accounts/signup/> — you will get
a membership number immediately and can borrow books straight away. You can also sign in with a
member account you create in the admin (**Library → Members**, link it to a user) or with the
superuser itself.

## Starter collection and appearance

`python manage.py seed_catalog` adds nine books, including *Kintu*, *The First
Woman* and *Things Fall Apart*, with authors, genres, summaries and three copies
per title. These are starter inventory records: adjust the copy counts in the
admin to match your physical shelves before opening borrowing to members.
The command is safe to rerun: it matches ISBNs and never resets existing stock,
overwrites catalogue edits, creates accounts or invents loan history. Two starter titles
(*Kintu* and *Things Fall Apart*) are flagged as staff picks on creation only.

The interface uses a two-letter **CS** monogram and solid shades of brown — espresso, walnut,
tobacco and sand. There are no textures or gradients anywhere, just flat colour blocks.
Book covers are typographic library designs, not reproductions of publisher artwork.
No external fonts or image services are needed.

## Running the checks and tests

```bash
python manage.py check
python manage.py test
```

The test suite covers model invariants, the due-date/fine calculation, the
borrow/return flows (stock restoration, the 3-loan limit, idempotency), access control,
and the admin configuration.

## Layout

```
library_project/        Django project settings, root URLconf, WSGI/ASGI
library/                The library app
  forms.py              Sign-up and review forms
  models.py             Author, Book, Member, Loan, Review, ReadingListItem (+ domain constants & fine logic)
  views.py              Home, catalogue, book detail, borrow/return/renew, reviews, reading list, my-loans, my-shelf, staff overdue desk
  admin.py              Admin configuration (search, filters, protected circulation history)
  templates/library/    Templates (extends library/base.html)
  static/library/       Stylesheet
```

## Configuration

Settings are read from environment variables (with development defaults):

| Variable               | Default                              | Purpose                |
|------------------------|--------------------------------------|------------------------|
| `DJANGO_SECRET_KEY`    | insecure local-development default   | Set in production      |
| `DJANGO_DEBUG`         | `true`                               | Set to `false` in production |
| `DJANGO_PREVIEW_EMBED` | `false`                              | Allow iframe embedding for a local preview only when debug is enabled |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1],.e2b.app` | Comma-separated hosts  |

`TIME_ZONE` is `Africa/Kampala`; `USE_TZ` is enabled.
