from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("books/", views.book_list, name="catalog"),
    path("books/<int:pk>/", views.book_detail, name="book_detail"),
    path("books/<int:book_id>/borrow/", views.borrow_book, name="borrow_book"),
    path("books/<int:book_id>/shelf/", views.toggle_reading_list, name="toggle_reading_list"),
    path("books/<int:book_id>/review/", views.post_review, name="post_review"),
    path("reviews/<int:review_id>/delete/", views.delete_review, name="delete_review"),
    path("my-loans/", views.my_loans, name="my_loans"),
    path("my-shelf/", views.my_shelf, name="my_shelf"),
    path("loans/<int:loan_id>/return/", views.return_loan, name="return_loan"),
    path("loans/<int:loan_id>/renew/", views.renew_loan, name="renew_loan"),
    path("staff/overdue/", views.overdue_loans, name="overdue_loans"),
]
