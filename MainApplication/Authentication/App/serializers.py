from rest_framework import serializers
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings

from ..models import *
from ...models import User
from ..emails import *
from ...User.models import *
from ...Credit.credit_models import UserCreditVault

import platform
import datetime
import urllib.parse
import re
import random
from django.db.models import Q

# --------------------------------------------- Authentication Serializers -------------------------------------------------------------

class UserRegistrationSerializer(serializers.Serializer):
    """Only validates and sends OTP - does NOT create user"""
    identifier = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    username = serializers.CharField(required=False, allow_blank=True)
    fullname = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        identifier = data.get("identifier")
        
        if not identifier:
            raise serializers.ValidationError("Email, phone, or username is required.")
        
        # Check if user already exists
        if User.objects.filter(
            Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)
        ).exists():
            raise serializers.ValidationError("User already exists.")
        
        return data

    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        # Store registration data temporarily in OTP model
        # We'll retrieve this during OTP verification
        
        # Generate and send OTP based on identifier type
        otp = str(random.randint(100000, 999999))
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            # Email registration
            RegistrationOTP.objects.create(
                identifier=identifier,
                otp=otp,
                # Store the full registration data as JSON in a metadata field
                # OR create a separate PendingRegistration model
            )
            send_registration_otp_email(identifier, otp)
            
        elif identifier.isdigit() and len(identifier) >= 7:
            # Phone registration
            RegistrationOTP.objects.create(
                identifier=identifier,
                otp=otp
            )
            # send_registration_otp_sms(identifier, otp)  # Uncomment when SMS is ready
            
        else:
            # Username registration - you might want to require email/phone for OTP
            raise serializers.ValidationError(
                "For username registration, please provide email or phone for verification."
            )
        
        return validated_data


class ResendOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)

    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        if not identifier:
            raise serializers.ValidationError("Email or phone must be provided.")
        
        # Generate new OTP
        otp = str(random.randint(100000, 999999))
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            send_registration_otp_email(identifier, otp)
        elif identifier.isdigit() and len(identifier) >= 7:
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            # send_registration_otp_sms(identifier, otp)
        else:
            raise serializers.ValidationError("Invalid identifier format.")

        return {'message': 'OTP resent successfully.'}


class EmailOTPVerifySerializer(serializers.Serializer):
    """Creates user ONLY after OTP verification"""
    identifier = serializers.CharField(required=True)
    otp = serializers.CharField(max_length=6, required=True)
    password = serializers.CharField(write_only=True, required=True)
    username = serializers.CharField(required=False, allow_blank=True)
    fullname = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        identifier = data.get("identifier")
        otp = data.get("otp")
        
        # Verify OTP
        try:
            otp_instance = RegistrationOTP.objects.get(identifier=identifier)
        except RegistrationOTP.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP or identifier.")
        
        if otp_instance.otp != otp:
            raise serializers.ValidationError("Invalid OTP.")
        
        if not otp_instance.is_valid(otp):
            raise serializers.ValidationError("OTP has expired or is invalid.")

        # Check if user already exists
        if User.objects.filter(
            Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)
        ).exists():
            raise serializers.ValidationError("User already exists.")

        return data
    
    def save(self):
        identifier = self.validated_data.get("identifier")
        password = self.validated_data.get("password")
        username = self.validated_data.get("username")
        fullname = self.validated_data.get("fullname", "")
        
        # Prepare user data
        user_data = {
            'password': password,
            'fullname': fullname
        }
        
        # Determine identifier type and set appropriate field
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            user_data['email'] = identifier
            user_data['is_email_verified'] = True
            if username:
                user_data['username'] = username
            
        elif identifier.isdigit() and len(identifier) >= 7:
            user_data['phone'] = identifier
            user_data['is_phone_verified'] = True
            if username:
                user_data['username'] = username
        else:
            user_data['username'] = identifier
        
        # CREATE USER NOW (after OTP verification)
        user = User.objects.create_user(**user_data)
        
        # Create related records
        from ...User.models import UserProfileModel
        from ...Credit.credit_models import UserCreditVault
        
        UserProfileModel.objects.create(user=user)
        UserCreditVault.objects.create(user=user, total_credits=0, total_value=0)
        
        # Send welcome email if email exists
        if user.email:
            try:
                user_created_email(user, user.email)
            except Exception as e:
                print(f"Welcome email failed: {e}")
        
        # Delete used OTP
        RegistrationOTP.objects.filter(identifier=identifier).delete()
        
        return user


class ResetPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    
    def validate(self, data):
        identifier = data.get("identifier")
        
        if not identifier:
            raise serializers.ValidationError("Email, phone, or username is required.")
        
        # Check if user exists
        if not User.objects.filter(
            Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)
        ).exists():
            raise serializers.ValidationError("User not found.")
        
        return data
    
    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        # Get user to find their email/phone
        user = User.objects.filter(
            Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)
        ).first()
        
        # Generate OTP
        otp = str(random.randint(100000, 999999))
        
        # Send to email or phone (prioritize email if both exist)
        if user.email and (identifier == user.email or identifier == user.username):
            ResetPasswordOTP.objects.create(identifier=user.email, otp=otp)
            forgot_password_otp_email(user.email, otp)
        elif user.phone:
            ResetPasswordOTP.objects.create(identifier=user.phone, otp=otp)
            # send_reset_password_otp_sms(user.phone, otp)
        else:
            raise serializers.ValidationError("No email or phone associated with this account.")

        return {'message': 'OTP sent successfully.'}


class ResendResetPasswordOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)

    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        # Generate new OTP
        otp = str(random.randint(100000, 999999))
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            forgot_password_otp_email(identifier, otp)
        elif identifier.isdigit() and len(identifier) >= 7:
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            # send_reset_password_otp_sms(identifier, otp)
        else:
            raise serializers.ValidationError("Invalid identifier format.")

        return {'message': 'OTP resent successfully.'}


class VerifyResetPasswordSerializer(serializers.Serializer):
    """Step 2: Only verify OTP (doesn't reset password)"""
    identifier = serializers.CharField(required=True)
    otp = serializers.CharField(max_length=6, required=True)

    def validate(self, data):
        identifier = data.get("identifier")
        otp = data.get("otp")
        
        # Verify OTP
        try:
            otp_instance = ResetPasswordOTP.objects.get(identifier=identifier)
        except ResetPasswordOTP.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP or identifier.")
        
        if otp_instance.otp != otp:
            raise serializers.ValidationError("Invalid OTP.")
        
        if not otp_instance.is_valid(otp):
            raise serializers.ValidationError("OTP has expired or is invalid.")

        return data
    
    def save(self):
        identifier = self.validated_data.get("identifier")
        
        # Find user
        user = User.objects.filter(
            Q(email=identifier) | Q(phone=identifier)
        ).first()
        
        if not user:
            raise serializers.ValidationError("User not found.")
        
        # Mark OTP as verified by updating it
        otp_instance = ResetPasswordOTP.objects.get(identifier=identifier)
        # Don't delete yet - we'll delete after password is set
        
        return {
            'message': 'OTP verified successfully. You can now set a new password.',
            'identifier': identifier
        }


class SetNewPasswordSerializer(serializers.Serializer):
    """Step 3: Set new password after OTP verification"""
    identifier = serializers.CharField(required=True)
    otp = serializers.CharField(max_length=6, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)
    device_info = serializers.CharField(required=False)

    def validate(self, data):
        identifier = data.get("identifier")
        otp = data.get("otp")
        new_password = data.get("new_password")
        
        if not new_password or len(new_password) < 6:
            raise serializers.ValidationError("Password must be at least 6 characters long.")
        
        # Verify OTP still exists and is valid
        try:
            otp_instance = ResetPasswordOTP.objects.get(identifier=identifier)
        except ResetPasswordOTP.DoesNotExist:
            raise serializers.ValidationError("OTP session expired. Please request a new OTP.")
        
        if otp_instance.otp != otp:
            raise serializers.ValidationError("Invalid OTP.")
        
        if not otp_instance.is_valid(otp):
            raise serializers.ValidationError("OTP has expired. Please request a new one.")

        return data
    
    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        new_password = validated_data.get("new_password")
        ip_address = validated_data.get('ip_address')
        user_agent = validated_data.get('user_agent')
        device_info = validated_data.get('device_info')
        
        # Find user by email or phone
        user = User.objects.filter(
            Q(email=identifier) | Q(phone=identifier)
        ).first()
        
        if not user:
            raise serializers.ValidationError("User not found.")
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        # Send confirmation email
        if user.email:
            try:
                password_reset_success_email(user, user.email, new_password)
            except Exception as e:
                print(f"Password reset email failed: {e}")
        
        # Delete used OTP
        ResetPasswordOTP.objects.filter(identifier=identifier).delete()
        
        # Log the password reset
        RecentLogin.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
            trusted=True 
        )

        return {
            'message': 'Password reset successfully.',
            'user': user
        }

# ---------------------------------------- End of Authentication Serializers --------------------------------------------------------------