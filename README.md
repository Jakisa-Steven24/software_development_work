# Hillcrest Shelf — Hillcrest College Library Borrowing Register

A Django web application (template-based) that replaces the paper borrowing register of the
Hillcrest College library in Kampala. Students browse the catalogue, borrow titles for their
programmes and track their own loans; library staff get an overdue-borrowings desk with live
fine calculations, and a Django admin configured for day-to-day cataloguing and circulation.

> **Provenance.** Hillcrest Shelf is a rebranded deployment of the *Community Shelf* borrowing
> register concept: same data model, circulation rules and screens, but a different institution,
> wordmark, palette, vocabulary and lending policy. All institution-specific copy lives in
> `library/context_processors.py` and `library/static/library/styles.css`.

## Features

- **Titles** — name, unique ISBN, year published, subject area, summary, total and available copies.
  `available_copies ≤ total_copies` is enforced at both the model (`full_clean`) and the
  database (`CheckConstraint`) level.
- **Authors** — many-to-many with titles (a title may have several authors and an author several titles).
- **Students** — linked one-to-one to Django user accounts, with a unique student number and a phone number.
- **Borrowing rules (Hillcrest College policy)**
  - Login required; POST-only, CSRF-protected form.
  - A copy must be on the shelf and the student must hold fewer than **4** unreturned loans.
  - Loans are due **21 days** after borrowing; late returns accrue **UGX 1,000 per overdue day**.
  - Stock is checked and decremented inside an atomic transaction with row locking
    (`select_for_update`) to prevent over-borrowing under concurrency.
- **Returns** — a student returns their own books (staff may return any loan); returning
  restores available stock exactly once (idempotent) and freezes the fine at the return date.
- **Staff fines desk** (`/staff/overdue/`) — lists every overdue loan with student details,
  days late, and the fine accrued (UGX 1,000 × days overdue), plus the total outstanding.
- **Django admin** — branded for the library desk; search titles by name or ISBN; filter loans by
  return status (plus due date); loan records are read-only / cannot be created or deleted through
  the admin so circulation history and stock stay consistent.
- **Student feedback** — Django messages framework is used throughout (borrow success,
  stock exhausted, loan limit reached, late-return fines, …).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_catalog      # optional foundation collection: nine titles with authors and summaries
python manage.py createsuperuser   # e.g. a "librarian" staff account
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

For a local demo you can sign in with a student account you create in the admin
(**Hillcrest College Library → Students**, link it to a user) or with the superuser itself.

## Foundation collection and appearance

`python manage.py seed_catalog` adds the nine-title foundation reading list, including *Kintu*,
*The First Woman* and *Things Fall Apart*, with authors, subject areas, summaries and three
copies per title. These are starter inventory records: adjust the copy counts in the admin to
match the physical shelves before opening borrowing to students.
The command is safe to rerun: it matches ISBNs and never resets existing stock,
overwrites catalogue edits, creates accounts or invents loan history.

The interface uses an **HC** monogram, a pine-teal and brass palette on uncoated paper,
and CSS paper and printed-board textures. Book covers are typographic library designs,
not reproductions of publisher artwork. No external fonts or image services are needed.

## Running the checks and tests

```bash
python manage.py check
python manage.py test
```

The test suite covers model invariants, the due-date/fine calculation, the
borrow/return flows (stock restoration, the 4-title limit, idempotency), access control,
the admin configuration, and that the institution's branding and policy appear consistently.

## Layout

```
library_project/        Django project settings, root URLconf, WSGI/ASGI
library/                The library app
  models.py             Author, Book, Member, Loan (+ domain constants & fine logic)
  context_processors.py Institution brand + lending policy shared by all templates
  views.py              Home, catalogue, title detail, borrow/return, my loans, staff fines desk
  admin.py              Admin configuration (branding, search, filters, protected circulation history)
  templates/library/    Templates (extends library/base.html)
  static/library/       Stylesheet
```

## Changing institution

To stand up the same system for another college, edit:

1. `library/context_processors.py` — name, institution, monogram, desk contact and hours.
2. `library/static/library/styles.css` — the `:root` palette and textures.
3. `library/models.py` — `LOAN_PERIOD_DAYS`, `MAX_UNRETURNED_BOOKS`, `FINE_PER_DAY_UGX`
   (templates read these through `loan_policy`, so they update everywhere at once).
4. Template copy that names the institution.

## Configuration

Settings are read from environment variables (with development defaults):

| Variable               | Default                              | Purpose                |
|------------------------|--------------------------------------|------------------------|
| `DJANGO_SECRET_KEY`    | insecure local-development default   | Set in production      |
| `DJANGO_DEBUG`         | `true`                               | Set to `false` in production |
| `DJANGO_PREVIEW_EMBED` | `false`                              | Allow iframe embedding for a local preview only when debug is enabled |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1],.e2b.app` | Comma-separated hosts  |

`TIME_ZONE` is `Africa/Kampala`; `USE_TZ` is enabled.
