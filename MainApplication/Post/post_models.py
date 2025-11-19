# MainApplication/Post/post_models.py
from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
import uuid
from MainApplication.models import User  # Adjust based on your User model location


def validate_image_size(file):
    """Validate image file size (max 20MB)"""
    max_size_mb = 20
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f'Image file size cannot exceed {max_size_mb}MB')


def validate_video_size(file):
    """Validate video file size (max 20MB)"""
    max_size_mb = 20
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f'Video file size cannot exceed {max_size_mb}MB')


def validate_image_format(file):
    """Validate that only JPG and PNG are allowed"""
    import os
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.jpg', '.jpeg', '.png']
    if ext not in valid_extensions:
        raise ValidationError('Only JPG, JPEG, and PNG image formats are allowed')


class Post(models.Model):
    POST_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('text', 'Text'),
    ]
    
    CONTENT_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    rating_count = models.IntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    saves_count = models.IntegerField(default=0)
    post_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    
    caption = models.TextField(blank=True, null=True)
    post_type = models.CharField(max_length=10, choices=POST_TYPE_CHOICES)
    
    # Video field with validation
    video = models.FileField(
        upload_to='posts/videos/%Y/%m/%d/',
        blank=True,
        null=True,
        validators=[
            validate_video_size,
            FileExtensionValidator(allowed_extensions=['mp4', 'avi', 'mov', 'mkv', 'webm'])
        ]
    )
    
    # Content moderation
    content_status = models.CharField(
        max_length=20, 
        choices=CONTENT_STATUS_CHOICES, 
        default='approved'
    )
    flagged_reason = models.TextField(blank=True, null=True)
    
    likes_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)
    
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username}'s {self.post_type} post - {self.post_id}"


class PostImage(models.Model):
    """Model to store multiple images for a post (max 5)"""
    image_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        validators=[
            validate_image_size,
            validate_image_format,
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])
        ]
    )
    alt_text = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Alternative text for accessibility"
    )  # ← ADDED THIS FIELD
    order = models.PositiveIntegerField(default=0)  # To maintain image order
    
    # Content moderation for individual images
    is_safe = models.BooleanField(default=True)
    moderation_result = models.JSONField(blank=True, null=True)  # Store API response
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"Image {self.order + 1} for post {self.post.post_id}"
    
    def clean(self):
        """Validate image format"""
        if self.image:
            validate_image_format(self.image)


class PostLike(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='liked_posts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('post', 'user')
    
    def __str__(self):
        return f"{self.user.username} likes {self.post.post_id}"


class PostComment(models.Model):
    comment_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} commented on {self.post.post_id}"
    

class PostSave(models.Model):
    """Model for saving posts (bookmarking)"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='saves')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_posts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('post', 'user')
        verbose_name = 'Post Save'
        verbose_name_plural = 'Post Saves'
    
    def __str__(self):
        return f"{self.user.username} saved {self.post.post_id}"


class PostShare(models.Model):
    """Model for tracking post shares"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='share_records')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_posts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Post Share'
        verbose_name_plural = 'Post Shares'
    
    def __str__(self):
        return f"{self.user.username} shared {self.post.post_id}"


class PostRating(models.Model):
    """Model for rating posts (1-5 stars) - Costs credits"""
    RATING_CHOICES = [(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)]
    
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_ratings')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('post', 'user')
        verbose_name = 'Post Rating'
        verbose_name_plural = 'Post Ratings'
    
    def __str__(self):
        return f"{self.user.username} rated {self.post.post_id} - {self.rating}⭐"    