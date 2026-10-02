from django.db import models

from accounts.ownership import UserOwned


class OwnedNote(UserOwned):
    text = models.CharField(max_length=100)
