from rest_framework import serializers
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings

from ..models import *
from ...models import User
from ...Credit.credit_models import UserCreditVault

from ..emails import *
from ...User.models import *

import platform
import datetime
import urllib.parse
import re
import random
from django.db.models import Q

# --------------------------------------------- Authentication Serializers -------------------------------------------------------------

class UserRegistrationSerializer(serializers.ModelSerializer):
    identifier = serializers.CharField(required=False)
    username = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = "__all__"

    def create(self, validated_data):
        otp = str(random.randint(100000, 999999))
        identifier = validated_data.get("identifier")
        username = validated_data.get("username")
        

        if not identifier:
            raise serializers.ValidationError({"message": "Either email or phone number must be provided."})

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"message": "This username is already taken."})

        # Check if identifier is an email
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            if User.objects.filter(email=identifier).exists():
                raise serializers.ValidationError({"message": "This email is already registered."})
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            send_registration_otp_email(identifier, otp)

        # Check if identifier is a phone number
        elif identifier.isdigit():
            if User.objects.filter(phone=identifier).exists():
                raise serializers.ValidationError({"message": "This phone number is already registered."})
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            # send_registration_otp_sms(identifier, otp)  # Uncomment when SMS sending logic is added

        else:
            raise serializers.ValidationError({"message": "Invalid identifier. Must be an email or phone number."})

        return {"message": "One-time password sent to your email/phone for verification."}

class ResentOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False)

    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        if not identifier:
            raise serializers.ValidationError("Either email or phone must be provided.")
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            otp = str(random.randint(100000, 999999))
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            send_registration_otp_email(identifier, otp)

        elif identifier.isdigit() and len(identifier):
            otp = str(random.randint(100000, 999999))
            RegistrationOTP.objects.create(identifier=identifier, otp=otp)
            # send_registration_otp_sms(identifier, otp)  # Implement SMS sending logic here

        return {'message': 'One time password sent to your email/phone for verification.'}

class EmailOTPVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, required=True)
    username = serializers.CharField(required=True)
    
    

    def validate(self, data):
        identifier = data.get("identifier")
        if not identifier:
            raise serializers.ValidationError({"message": "Either email or phone must be provided"})
        
        try:
            otp_instance = RegistrationOTP.objects.get(identifier=identifier)
        except RegistrationOTP.DoesNotExist:
            raise serializers.ValidationError({"message": "Invalid OTP or identifier"})
        
        if otp_instance.otp != data.get("otp"):
            raise serializers.ValidationError({"message": "Invalid OTP"})
        
        if not otp_instance.is_valid(data.get("otp")):
            raise serializers.ValidationError({"message": "OTP has already been used or is invalid"})

        return data
    
    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            user = User.objects.create_user(
                username=validated_data.get("username"),
                email=validated_data.get("identifier"),
                password=validated_data.get("password")
            )
            user.save()
            user_created_email(user, validated_data.get("email"))
            user.is_email_verified = True
            RegistrationOTP.objects.filter(identifier=validated_data.get("email")).delete()
        elif identifier.isdigit() and len(identifier):
                user = User.objects.create_user(
                    username=validated_data.get("username"),
                    phone=validated_data.get("identifier"),
                    password=validated_data.get("password")
                )
                user.is_phone_verified = True
                user.save()
                RegistrationOTP.objects.filter(identifier=validated_data.get("phone")).delete()

        else:
            raise serializers.ValidationError("Invalid identifier format.")
        
        UserProfileModel.objects.create(user=user)
        UserCreditVault.objects.create(user=user, total_credits=0, total_value=0)

        return user

class ResetPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False)
    class Meta:
        model = ResetPasswordOTP
        fields = "__all__"
    
    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        if not identifier:
            raise serializers.ValidationError("Either email or phone must be provided.")
        
        if not User.objects.filter(Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)).exists():
            raise serializers.ValidationError("Invalid identifier.")
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            otp = str(random.randint(100000, 999999))
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            forgot_password_otp_email(identifier, otp)

        elif identifier.isdigit() and len(identifier):
            otp = str(random.randint(100000, 999999))
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            # send_reset_password_otp_sms(identifier, otp)  # Implement SMS sending logic here

        return {'message': 'One time password sent to your email/phone for verification.'}

class ResendResetPasswordOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False)

    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        
        if not identifier:
            raise serializers.ValidationError("Either email or phone must be provided.")
        
        
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            otp = str(random.randint(100000, 999999))
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            forgot_password_otp_email(identifier, otp)

        elif identifier.isdigit() and len(identifier):
            otp = str(random.randint(100000, 999999))
            ResetPasswordOTP.objects.create(identifier=identifier, otp=otp)
            # send_reset_password_otp_sms(identifier, otp)  # Implement SMS sending logic here

        return {'message': 'One time password sent to your email/phone for verification.'}

class VerifyResetPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False)
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, required=False)
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)
    device_info = serializers.CharField(required=False)

    def validate(self, data):
        identifier = data.get("identifier")
        if not identifier:
            raise serializers.ValidationError("Either email or phone must be provided.")
        
        try:
            otp_instance = ResetPasswordOTP.objects.get(identifier=identifier)
        except ResetPasswordOTP.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP or identifier.")
        
        if otp_instance.otp != data.get("otp"):
            raise serializers.ValidationError("Invalid OTP.")
        
        if not otp_instance.is_valid(data.get("otp")):
            raise serializers.ValidationError("OTP has already been used or is invalid.")

        return data
    
    def create(self, validated_data):
        identifier = validated_data.get("identifier")
        new_password = validated_data.get("new_password")
        ip_address = validated_data.get('ip_address')
        user_agent = validated_data.get('user_agent')
        device_info = validated_data.get('device_info')
        user = None
        
        if not identifier:
            raise serializers.ValidationError("Either email or phone must be provided.")
        
        if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
            user = User.objects.get(email=identifier)
            user.set_password(new_password)
            user.save()
            
            ResetPasswordOTP.objects.filter(identifier=validated_data.get("email")).delete()
            
        elif identifier.isdigit() and len(identifier):
            user = User.objects.get(phone=identifier)
            user.set_password(new_password)
            user.save()
            ResetPasswordOTP.objects.filter(identifier=validated_data.get("phone")).delete()

        else:
            raise serializers.ValidationError("Invalid identifier format.")
        
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