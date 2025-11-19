# MainApplication/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField, AdminPasswordChangeForm
from django import forms
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import *
from .Authentication.models import *
from .User.models import *
from .Credit.credit_models import *
from .Post.post_models import Post, PostImage, PostLike, PostComment  # ← Add this import


# --- Forms ---

class UserCreationForm(forms.ModelForm):
    """Form for creating new users in the admin."""
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("username", "email", "phone")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """Form for updating users in the admin."""
    password = ReadOnlyPasswordHashField(
        label="Password",
        help_text=_("Passwords are not stored in plain text. "
                    "You can change the password using <a href='../password/'>this form</a>.")
    )

    class Meta:
        model = User
        fields = ("username", "email", "phone", "password", "is_active", "is_staff", "is_superuser")

    def clean_password(self):
        return self.initial["password"]


# --- Admin ---

class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = ("unique_id", "username", "email", "phone", "is_active")
    list_filter = ("is_staff", "is_active", "is_superuser")
    search_fields = ("username", "email", "phone")
    ordering = ("id",)

    fieldsets = (
        (None, {"fields": ("username", "email", "phone", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "phone", "password1", "password2", "is_staff", "is_active"),
        }),
    )

    # ✅ Reset password view
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<id>/password/",
                self.admin_site.admin_view(self.user_change_password),
                name="user_change_password",
            ),
        ]
        return custom_urls + urls

    def user_change_password(self, request, id, form_url=""):
        user = self.get_object(request, id)
        if not user:
            return redirect("..")

        if request.method == "POST":
            form = AdminPasswordChangeForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, _("Password changed successfully."))
                return redirect("..")
        else:
            form = AdminPasswordChangeForm(user)

        context = {
            "title": _("Change password"),
            "form": form,
            "is_popup": False,
            "add": False,
            "change": True,
            "has_view_permission": True,
            "opts": self.model._meta,
            "original": user,
        }
        return render(request, "admin/auth/user/change_password.html", context)


admin.site.register(User, UserAdmin)

admin.site.site_header = "ExApp Admin"
admin.site.site_title = "ExApp Admin Portal"
admin.site.index_title = "Welcome to ExApp Admin Portal"
admin.site.site_url = None  # Disable the "View site" link


admin.site.register(RegistrationOTP)

admin.site.register(RecentLogin)
class RecentLoginAdmin(admin.ModelAdmin):
    # Shows in the list view
    list_display = ['user', 'login_time', 'ip_address', 'device_info', 'trusted']
    
    # Shows in the detail/edit form (THIS IS WHAT YOU NEED)
    fields = ['user', 'login_time', 'ip_address', 'user_agent', 'device_info', 'trusted', 'created_at']
    
    # Make these read-only (can't edit)
    readonly_fields = ['login_time', 'created_at']
    
    def has_add_permission(self, request):
        # Optional: Prevent manual addition of login records
        return True
    
    ordering = ['-login_time']

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio', 'location')
    search_fields = ('user__username', 'location')
    list_filter = ('location',)
admin.site.register(UserProfileModel, UserProfileAdmin)


# credit models
# ========== CREDIT MODELS ========== #

@admin.register(CreditModel)
class CreditModelAdmin(admin.ModelAdmin):
    list_display = ['credit', 'value']
    fieldsets = (
        ('Credit Configuration', {
            'fields': ('credit', 'value'),
            'description': 'Set the base credit value. Only one instance allowed.'
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one instance
        if CreditModel.objects.exists():
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditCostsModel)
class CreditCostsModelAdmin(admin.ModelAdmin):
    list_display = ['following_cost', 'post_creation_cost', 'star_rating_cost', 'post_liking_cost']
    fieldsets = (
        ('Action Costs (in Credits)', {
            'fields': ('following_cost', 'post_creation_cost', 'star_rating_cost', 'post_liking_cost'),
            'description': 'Configure how many credits each action costs. Only one instance allowed.'
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one instance
        if CreditCostsModel.objects.exists():
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserCreditVault)
class UserCreditVaultAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_credits', 'total_value', 'gained_credits', 'spent_credits', 'purchased_credits', 'updated_at']
    search_fields = ['user__username', 'user__email']
    list_filter = ['created_at', 'updated_at']
    readonly_fields = ['total_value', 'created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Credit Balance', {
            'fields': ('total_credits', 'total_value')
        }),
        ('Credit Breakdown', {
            'fields': ('gained_credits', 'spent_credits', 'purchased_credits')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-total_credits']


@admin.register(CreditTransactionLog)
class CreditTransactionLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction_type', 'credits_changed', 'value_changed', 'timestamp', 'description']
    list_filter = ['transaction_type', 'timestamp']
    search_fields = ['user__username', 'description']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Transaction Info', {
            'fields': ('user', 'transaction_type', 'credits_changed', 'value_changed')
        }),
        ('Details', {
            'fields': ('description', 'timestamp')
        }),
    )
    
    ordering = ['-timestamp']
    
    def has_add_permission(self, request):
        # Prevent manual creation of transaction logs
        return False
admin.site.register(UserFollowersModel)
admin.site.register(UserFollowingModel)


# ========== POST MODELS ========== #

class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 0
    readonly_fields = ['image_id', 'is_safe', 'moderation_result', 'created_at']
    fields = ['image', 'order', 'is_safe', 'moderation_result']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['post_id', 'user', 'post_type', 'content_status', 'likes_count', 'comments_count', 'created_at']
    list_filter = ['post_type', 'content_status', 'is_active', 'is_deleted', 'created_at']
    search_fields = ['user__username', 'caption', 'post_id']
    readonly_fields = ['post_id', 'created_at', 'updated_at']
    inlines = [PostImageInline]
    
    fieldsets = (
        ('Post Info', {
            'fields': ('post_id', 'user', 'post_type', 'caption')
        }),
        ('Media', {
            'fields': ('video',)
        }),
        ('Moderation', {
            'fields': ('content_status', 'flagged_reason')
        }),
        ('Stats', {
            'fields': ('likes_count', 'comments_count', 'shares_count')
        }),
        ('Status', {
            'fields': ('is_active', 'is_deleted', 'created_at', 'updated_at', 'deleted_at')
        }),
    )


@admin.register(PostImage)
class PostImageAdmin(admin.ModelAdmin):
    list_display = ['image_id', 'post', 'order', 'is_safe', 'created_at']
    list_filter = ['is_safe', 'created_at']
    readonly_fields = ['image_id', 'moderation_result', 'created_at']
    search_fields = ['post__post_id', 'post__user__username']


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'post__post_id']


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ['comment_id', 'user', 'post', 'text', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'text', 'post__post_id']
    readonly_fields = ['comment_id', 'created_at', 'updated_at']