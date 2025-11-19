from django.db import models
import uuid
from django.utils import timezone
from datetime import timedelta
from ..models import User 

class RegistrationOTP(models.Model):
    identifier = models.CharField(max_length=255)  # can be email or phone
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.identifier} - {self.otp}"
    
    def save(self, *args, **kwargs):
        from django.utils import timezone
        from datetime import timedelta

        # Delete old OTPs for the same identifier
        RegistrationOTP.objects.filter(identifier=self.identifier).delete()
        super().save(*args, **kwargs)

    def is_valid(self, input_otp):
        # OTP is valid for 10 minutes

        if self.otp != input_otp:
            return False
        if timezone.now() > self.created_at + timedelta(minutes=10):
            return False
        return True


    
class RecentLogin(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    device_info = models.CharField(max_length=255, null=True, blank=True)
    trusted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.ip_address or 'Unknown IP'} - {'Trusted' if self.trusted else 'Untrusted'}"
    
    
class ResetPasswordOTP(models.Model):
    identifier = models.CharField(max_length=255)  # can be email or phone
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.identifier} - {self.otp}"
    
    def save(self, *args, **kwargs):
        from django.utils import timezone
        from datetime import timedelta

        # Delete old OTPs for the same identifier
        ResetPasswordOTP.objects.filter(identifier=self.identifier).delete()
        super().save(*args, **kwargs)
        
    def is_valid(self, input_otp):
        # OTP is valid for 10 minutes

        if self.otp != input_otp:
            return False
        if timezone.now() > self.created_at + timedelta(minutes=10):
            return False
        return True