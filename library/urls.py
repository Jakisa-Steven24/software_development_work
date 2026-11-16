from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("books/", views.book_list, name="catalog"),
    path("books/<int:pk>/", views.book_detail, name="book_detail"),
    path("books/<int:book_id>/borrow/", views.borrow_book, name="borrow_book"),
    path("my-loans/", views.my_loans, name="my_loans"),
    path("loans/<int:loan_id>/return/", views.return_loan, name="return_loan"),
    path("staff/overdue/", views.overdue_loans, name="overdue_loans"),
]
