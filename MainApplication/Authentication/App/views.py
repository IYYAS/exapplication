from django.shortcuts import render
from django.http import HttpResponse

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model, authenticate
from django.db.models import Q
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

import platform
import datetime
import urllib.parse
import re
import random

from ..models import *
from ..models import User

from .serializers import *
from ..emails import *

User = get_user_model()

# ---------------------------------------- Authentication Views --------------------------------------------------------------


class CheckUsernameView(APIView):
    def get(self, request):
        new_username = request.query_params.get("username", "").strip()

        if not new_username:
            return Response({
                "message": "Enter a username",
                "is_available": False,
                "color": "gray"
            })

        if not re.match(r'^[A-Za-z0-9_.]+$', new_username):
            return Response({
                "message": "Only letters, numbers, underscores and periods are allowed",
                "is_available": False,
                "color": "red"
            })

        if len(new_username) < 3 or len(new_username) > 20:
            return Response({
                "message": "Username must be 3 - 20 characters long",
                "is_available": False,
                "color": "red"
            })

        username_taken = User.objects.filter(username__iexact=new_username).exists()

        if username_taken:
            data = {
                "message": "Username already taken",
                "is_available": False,
                "color": "red"
            }
        else:
            data = {
                "message": "Username available",
                "is_available": True,
                "color": "green"
            }

        return Response(data)


class CheckIdentifierView(APIView):
    def get(self, request):
        identifier = request.query_params.get("identifier", "").strip()
        
        if not identifier:
            return Response({
                "message": "Enter an email address or phone number",
                "is_available": False,
            })

        is_email = re.match(r"[^@]+@[^@]+\.[^@]+", identifier)
        is_phone = re.match(r"^\+?\d{7,15}$", identifier)

        if not (is_email or is_phone):
            return Response({
                "message": "Invalid email or phone number format",
                "is_available": False,
            })

        if is_email:
            exists = User.objects.filter(email__iexact=identifier).exists()
            id_type = "Email"
        else:
            exists = User.objects.filter(phone__iexact=identifier).exists()
            id_type = "Phone number"

        if exists:
            data = {
                "message": f"{id_type} already exists",
                "is_available": False,
            }
        else:
            data = {
                "message": f"{id_type} is available",
                "is_available": True,
            }

        return Response(data)


class RegisterView(APIView):
    """Step 1: Send OTP (does NOT create user)"""
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "OTP sent to your email/phone. Please verify to complete registration."
            }, status=status.HTTP_200_OK)
        return Response({
            'message': 'Registration failed.',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ResendOTPView(APIView):
    """Resend OTP"""
    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "OTP resent successfully."
            }, status=status.HTTP_200_OK)
        return Response({
            'message': 'Failed to resend OTP.',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    """Step 2: Verify OTP and CREATE user"""
    def post(self, request):
        serializer = EmailOTPVerifySerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                "error": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create user after successful OTP verification
        user = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Account created and verified successfully.',
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'phone': user.phone,
                'fullname': user.fullname,
                'is_email_verified': user.is_email_verified,
                'is_phone_verified': user.is_phone_verified
            }
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    """Login with any identifier (username/email/phone) + password"""
    def post(self, request):
        identifier = request.data.get("identifier")
        password = request.data.get("password")

        if not identifier or not password:
            return Response(
                {"error": "Identifier and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by username, email, OR phone
        user = User.objects.filter(
            Q(username=identifier) | Q(email=identifier) | Q(phone=identifier)
        ).first()

        if not user:
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Verify password
        if not user.check_password(password):
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if account is verified
        if not (user.is_email_verified or user.is_phone_verified):
            return Response(
                {"error": "Please verify your account first."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 🔥 BLACKLIST ALL EXISTING TOKENS FOR THIS USER
        try:
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                try:
                    BlacklistedToken.objects.get_or_create(token=token)
                except Exception as e:
                    print(f"Error blacklisting token: {e}")
        except Exception as e:
            print(f"Error fetching outstanding tokens: {e}")

        # Generate NEW JWT tokens (after blacklisting old ones)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Capture device info
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown device')
        ip_address = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR')
            or 'Unknown IP'
        )
        login_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Log the login
        RecentLogin.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=platform.system(),
            trusted=True
        )

        # Create security notification URLs
        get_current_site = request.get_host()
        base_url = f"http://{get_current_site}"
        notify_url_yes = f"{base_url}/login-confirm?user={user.id}&confirm=yes"
        notify_url_no = f"{base_url}/login-confirm?user={user.id}&confirm=no"

        # Send security email
        if user.email:
            try:
                login_detected_email(
                    user, user.email, ip_address, user_agent,
                    login_time, notify_url_yes, notify_url_no
                )
            except Exception as e:
                print(f"Security email failed: {e}")

        return Response({
            "message": "Login successful.",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "fullname": user.fullname
            },
            "access_token": access_token,
            "refresh_token": str(refresh),
            "device_info": {
                "ip_address": ip_address,
                "user_agent": user_agent,
                "login_time": login_time
            }
        }, status=status.HTTP_200_OK)


class DirectResetPasswordView(APIView):
    """Direct password reset (requires authentication)"""
    def post(self, request):
        user = request.user
        current_password = request.data.get("current_password")
        new_password = request.data.get("password")
        
        if not current_password:
            return Response(
                {"error": "Current password is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not new_password:
            return Response(
                {"error": "New password is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user.set_password(new_password)
            user.save()
            
            if user.email:
                password_reset_success_email(user, user.email, new_password)
            
            return Response(
                {"message": "Password updated successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": "Password reset failed."},
                status=status.HTTP_400_BAD_REQUEST
            )


class ResetPasswordOTPView(APIView):
    """Request password reset OTP"""
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'OTP sent successfully.',
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendResetPasswordOTPView(APIView):
    """Resend password reset OTP"""
    def post(self, request):
        serializer = ResendResetPasswordOTPSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "OTP resent successfully."
            }, status=status.HTTP_200_OK)
        return Response({
            'message': 'Failed to resend OTP.',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class VerifyResetPasswordOTPView(APIView):
    """Step 2: Only verify OTP (doesn't reset password)"""
    def post(self, request):
        serializer = VerifyResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            
            return Response({
                'message': result['message'],
                'identifier': result['identifier'],
                'next_step': 'Use /password/reset/new/ to set your new password'
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetNewPasswordView(APIView):
    """Step 3: Set new password after OTP verification"""
    def post(self, request):
        # Add device info to request data
        data = request.data.copy()
        data['ip_address'] = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR')
            or 'Unknown IP'
        )
        data['user_agent'] = request.META.get('HTTP_USER_AGENT', 'Unknown')
        data['device_info'] = platform.system()
        
        serializer = SetNewPasswordSerializer(data=data)
        if serializer.is_valid():
            result = serializer.save()
            user = result['user']
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': 'Password reset successfully.',
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------- End of Authentication Views --------------------------------------------------------------