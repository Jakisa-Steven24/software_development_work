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
python manage.py createsuperuser   # e.g. a "librarian" staff account
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

For a local demo you can sign in with a member account you create in the admin
(**Library → Members**, link it to a user) or with the superuser itself.

## Running the checks and tests

```bash
python manage.py check
python manage.py test
```

The suite (28 tests) covers model invariants, the due-date/fine calculation, the
borrow/return flows (stock restoration, the 3-loan limit, idempotency), access control,
and the admin configuration.

## Layout

```
library_project/        Django project settings, root URLconf, WSGI/ASGI
library/                The library app
  models.py             Author, Book, Member, Loan (+ domain constants & fine logic)
  views.py              Home, catalogue, book detail, borrow/return, my-loans, staff overdue desk
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
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1],.e2b.app` | Comma-separated hosts  |

`TIME_ZONE` is `Africa/Kampala`; `USE_TZ` is enabled.
