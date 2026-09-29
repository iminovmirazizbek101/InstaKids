from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import change_password, csrf_token, home, reset_password, send_code, login, logout, register, realtime, set_follow, social_state, users

router = DefaultRouter()
# router.register("tovar", basename="tovar")

urlpatterns = [path("", home, name="home"),
              path("csrf/", csrf_token, name="csrf-token"),
              path("register/", register, name="register"),
              path("login/", login, name="login"),
              path("users/", users, name="users"),
              path("change-password/", change_password, name="change-password"),
              path("send-code/", send_code, name="send-code"),
              path("reset-password/", reset_password, name="reset-password"),
              path("logout/", logout, name="logout"),
              path("social/", social_state, name="social-state"),
              path("follow/", set_follow, name="set-follow"),
              path("realtime/", realtime, name="realtime"),
               
               ]
urlpatterns += router.urls
