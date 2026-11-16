from django.core.management.base import BaseCommand
from django.db import transaction

from library.models import Author, Book


# ISBNs and years identify the listed editions, not first publication dates.
# ISBNs of starter titles the library considers librarian picks from day one.
STAFF_PICK_ISBNS = {"9781945492010", "9780385474542"}

STARTER_BOOKS = (
    (
        "Kintu", "Jennifer Nansubuga Makumbi", "9781945492010", 2017,
        "Ugandan fiction",
        "Beginning in eighteenth-century Buganda, the story follows Kintu Kidda and the generations who inherit his name. A family saga about ancestry, belonging and the stories people carry.",
    ),
    (
        "The First Woman", "Jennifer Nansubuga Makumbi", "9781786078587", 2020,
        "Ugandan fiction",
        "Kirabo grows up in a Ugandan village surrounded by family, but with questions about her absent mother. Her search takes her through school, changing friendships and competing ideas of what it means to be a woman.",
    ),
    (
        "Things Fall Apart", "Chinua Achebe", "9780385474542", 1994,
        "African classics",
        "Okonkwo has built his standing in Umuofia through determination and hard work. As colonial rule and Christian missionaries reach his community, the foundations of his world begin to shift.",
    ),
    (
        "The River and the Source", "Margaret A. Ogola", "9789966460191", 1994,
        "Family saga",
        "Four generations of Kenyan women navigate family life, education and social change. Their connected stories trace the choices and sacrifices that shape a family across the twentieth century.",
    ),
    (
        "Weep Not, Child", "Ngũgĩ wa Thiong’o", "9780143106692", 2012,
        "Historical fiction",
        "Njoroge dreams of an education and a better future for his family. Set in colonial Kenya during the Mau Mau uprising, his story brings the hopes of childhood into conflict with a divided country.",
    ),
    (
        "The Old Man and the Sea", "Ernest Hemingway", "9780684801223", 1995,
        "Literary fiction",
        "After a long run without a catch, an ageing Cuban fisherman heads far out to sea. His encounter with a great marlin becomes a spare, moving story of endurance and the cost of a hard-won victory.",
    ),
    (
        "Pride and Prejudice", "Jane Austen", "9780141439518", 2002,
        "Classic fiction",
        "Elizabeth Bennet is quick to judge the reserved Mr Darcy, and he is no less certain of his own opinions. Their encounters unfold amid family expectations, money and marriage in the English countryside.",
    ),
    (
        "A Grain of Wheat", "Ngũgĩ wa Thiong’o", "9780141186993", 2002,
        "Historical fiction",
        "As a Kenyan village prepares to celebrate independence, memories of the struggle reveal private loyalties and betrayals. Several lives converge around a man the community has come to regard as a hero.",
    ),
    (
        "The Secret Garden", "Frances Hodgson Burnett", "9780141321066", 2008,
        "Young readers",
        "Sent to live in a Yorkshire manor, Mary Lennox discovers a locked garden and a household full of secrets. With new friends and patient care, she begins to bring the neglected garden back to life.",
    ),
)


class Command(BaseCommand):
    help = "Add nine starter titles without changing existing books, authors or stock."

    @transaction.atomic
    def handle(self, *args, **options):
        added = 0
        for title, author_name, isbn, year, genre, description in STARTER_BOOKS:
            book, created = Book.objects.get_or_create(
                isbn=isbn,
                defaults={
                    "title": title,
                    "publication_year": year,
                    "genre": genre,
                    "description": description,
                    "total_copies": 3,
                    "available_copies": 3,
                    "staff_pick": isbn in STAFF_PICK_ISBNS,
                },
            )
            if created:
                author = Author.objects.filter(name=author_name).order_by("pk").first()
                if author is None:
                    author = Author.objects.create(name=author_name)
                book.authors.add(author)
                added += 1

        self.stdout.write(self.style.SUCCESS(f"Added {added} starter titles; existing titles were left unchanged."))
