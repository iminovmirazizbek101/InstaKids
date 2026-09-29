from django.db import models


class SocialState(models.Model):
	payload = models.JSONField(default=dict)
	updated_at = models.DateTimeField(auto_now=True)


class EmailCode(models.Model):
	email = models.EmailField()
	purpose = models.CharField(max_length=20)
	code = models.CharField(max_length=6)
	created_at = models.DateTimeField(auto_now_add=True)
	used = models.BooleanField(default=False)
