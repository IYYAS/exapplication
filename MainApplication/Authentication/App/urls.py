from django.urls import path
from .views import *

urlpatterns = [
    path('register/', RegisterView.as_view(), name="register"),
    path('resend-otp/', ResendOTPView.as_view(), name='resent-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('password/reset/direct/', DirectResetPasswordView.as_view(), name='direct-reset-password'),
    path('password/reset/otp/', ResetPasswordOTPView.as_view(), name='reset-password'),
    path('password/reset/otp/resent/', ResendResetPasswordOTPView.as_view(), name='reset-password-confirm'),
    path('password/reset/otp/verify/', VerifyResetPasswordOTPView.as_view(), name='reset-password-verify'),
    path('password/reset/new/', SetNewPasswordView.as_view(), name='set-new-password'),  # Sets new password after OTP verification

    path('check-username/', CheckUsernameView.as_view(), name='check-username'),
    path('check-identifier/', CheckIdentifierView.as_view(), name='check-identifier'),
]