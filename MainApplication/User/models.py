from  django.db import models
from datetime import datetime, timedelta
from django.utils import timezone


from ..models import User

import uuid


class UserProfileModel(models.Model):
    account_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    designation = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    fullname = models.CharField(max_length=150, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    account_plan = models.CharField(max_length=50, default='Free')  # e.g., Free, Premium, Enterprise
    plan_purchase_date = models.DateTimeField(blank=True, null=True)
    plan_expiry_date = models.DateTimeField(blank=True, null=True)

    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    
    deleted_at = models.DateTimeField(blank=True, null=True)
    
    
    def __str__(self):
        return f"{self.user.username}'s Profile"



class ExternalLinks(models.Model):
    user_profile = models.ForeignKey(UserProfileModel, on_delete=models.CASCADE, related_name='external_links')
    platform_name = models.CharField(max_length=100) 
    url = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.platform_name} - {self.user_profile.user.username}"

class UserActivityLog(models.Model):
    user_profile = models.ForeignKey(UserProfileModel, on_delete=models.CASCADE, related_name='activity_logs')
    activity_type = models.CharField(max_length=100)  # e.g., Login, Logout, Profile Update
    activity_description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)  # Additional data related to the activity

    def __str__(self):
        return f"{self.user_profile.user.username} - {self.activity_type}"

class UserFollowersModel(models.Model):
    user_profile = models.ForeignKey(UserProfileModel, on_delete=models.CASCADE, related_name='followers')
    follower = models.OneToOneField(UserProfileModel, on_delete=models.CASCADE, related_name='following_set')
    followed_at = models.DateTimeField(auto_now_add=True)
    followed = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user_profile', 'follower')

    def __str__(self):
        return f"{self.follower.user.username} follows {self.user_profile.user.username}"

class UserFollowingModel(models.Model):
    user_profile = models.ForeignKey(UserProfileModel, on_delete=models.CASCADE, related_name='following')
    following = models.OneToOneField(UserProfileModel, on_delete=models.CASCADE, related_name='followers_set')
    followed_at = models.DateTimeField(auto_now_add=True)
    followed = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('user_profile', 'following')

    def __str__(self):
        return f"{self.user_profile.user.username} follows {self.following.user.username}"