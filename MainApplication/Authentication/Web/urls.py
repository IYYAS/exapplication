from django.urls import path
from .views import *

urlpatterns = [
    path('register/', RegisterView.as_view(), name="register"),
    path('resend-otp/', ResendOTPView.as_view(), name='resent-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('login/', LoginView.as_view(), name='login'),
    path("login-confirm/", VerifyLoginView.as_view(), name="verify-login"),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token-refresh'),
    path('check-login/', CheckLoginView.as_view(), name='check-login'),
    
    path('check-username/', CheckUsernameView.as_view(), name='check-username'),
    path('check-identifier/', CheckIdentifierView.as_view(), name='check-identifier'),
]