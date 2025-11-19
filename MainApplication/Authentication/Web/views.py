from django.shortcuts import render
from django.http import HttpResponse

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q




import platform
import datetime
import urllib.parse
import re
import random


from ..models import *
from ..models import User
from ...User.models import UserProfileModel

from .serializers import *
from ..emails import *

User = get_user_model()

# from django_smart_ratelimit import rate_limit
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from ...auth_utils import get_user_from_request



# ---------------------------------------- Authentication Views --------------------------------------------------------------


class CheckUsernameView(APIView):
    def get(self, request):
        new_username = request.query_params.get("username", "").strip()


        # --- Validation checks ---
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

        # --- Check directly in the database ---
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

        # Identify whether it's an email or phone number
        is_email = re.match(r"[^@]+@[^@]+\.[^@]+", identifier)
        is_phone = re.match(r"^\+?\d{7,15}$", identifier)  # allows optional + and 7–15 digits

        if not (is_email or is_phone):
            return Response({
                "message": "Invalid email or phone number format",
                "is_available": False,
            })

        # Check database for existence
        if is_email:
            exists = User.objects.filter(email__iexact=identifier).exists()
            id_type = "Email"
        else:
            exists = User.objects.filter(username__iexact=identifier).exists()  # assuming phone is stored in username
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


# @rate_limit(key='ip', rate='1/m', block=True)
class RegisterView(APIView):
   def post(self, request):
       serializer = UserRegistrationSerializer(data=request.data)
       if serializer.is_valid():
           serializer.save()
           return Response({"message": "One time password sent to your email/phone for verification."}, status=status.HTTP_201_CREATED)
       return Response({
           'message': 'Registration failed.',
           'errors': serializer.errors
         }, status=status.HTTP_400_BAD_REQUEST)

# @rate_limit(key='ip', rate='1/m', block=True)
class ResendOTPView(APIView):
   def post(self, request):
       serializer = ResentOTPSerializer(data=request.data, context={'request': request})
       if serializer.is_valid():
           serializer.save()
           return Response({"message": "One time password sent to your email/phone for verification."}, status=status.HTTP_201_CREATED)
       return Response({
           'message': 'Registration failed.',
           'errors': serializer.errors
         }, status=status.HTTP_400_BAD_REQUEST)
   
class VerifyOTPView(APIView):
    def post(self, request):
        serializer = EmailOTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()  # capture the created user here
            if_new_user = True
            if UserProfileModel.objects.get(user=user).fullname:
                if_new_user = False
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            response = Response({
                'message': 'Account verified successfully.',
                'new_user': if_new_user,
            }, status=status.HTTP_200_OK)

            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=3600,
            )

            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=7 * 24 * 3600,
            )

            return response
        # --- flatten the error response here ---
        errors = serializer.errors
        message = None

        if isinstance(errors, dict):
            # Try to get first field error
            for key, value in errors.items():
                if isinstance(value, list) and len(value) > 0:
                    message = value[0]
                else:
                    message = value
                break
        elif isinstance(errors, list):
            message = errors[0]
        else:
            message = str(errors)

        return Response({"message": message}, status=status.HTTP_400_BAD_REQUEST)

# @method_decorator(csrf_exempt, name='dispatch')
# @rate_limit(key='ip', rate='5/m', block=True)
class LoginView(APIView):
    def post(self, request):
        identifier = request.data.get("identifier")  # can be email, phone, or username
        password = request.data.get("password")

        if not identifier or not password:
            return Response(
                {"message": "Identifier and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(
            Q(username=identifier) | Q(email=identifier) | Q(phone=identifier)
        ).first()

        if not user:
            return Response({"message": "No user found with this credential"},
                            status=status.HTTP_404_NOT_FOUND)

        if not user.check_password(password):
            return Response({"message": "Your password is incorrect"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Capture device info
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown device')
        ip_address = (
            request.META.get('HTTP_X_FORWARDED_FOR')
            or request.META.get('REMOTE_ADDR')
            or 'Unknown IP'
        )
        login_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create secure notify link
        get_current_site = request.get_host()
        base_url = f"http://{get_current_site}"
        notify_url_yes = f"{base_url}/login-confirm?user={user.id}&confirm=yes"
        notify_url_no = f"{base_url}/login-confirm?user={user.id}&confirm=no"
        email = user.email

        # --- Send security email ---
        try:
            login_detected_email(user, email, ip_address, user_agent, login_time, notify_url_yes, notify_url_no)
        except Exception as e:
            print("Email send failed:", e)
        if_new_user = True
        if UserProfileModel.objects.get(user=user).fullname:
            if_new_user = False
        # Response JSON
        response_data = {
            "message": "Login successful.",
            'new_user': if_new_user,
            "user": {"username": user.username, "email": user.email},
            "device_info": {"ip_address": ip_address, "user_agent": user_agent},
            "login_time": login_time,
            "security_notify_urls": {
                "yes": notify_url_yes,
                "no": notify_url_no
            },
        }

        response = Response(response_data, status=status.HTTP_200_OK)

        # Set cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=3600,
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=7 * 24 * 3600,
        )

        return response
    
class VerifyLoginView(APIView):
    def get(self, request):
        user_id = request.query_params.get("user")
        confirm = request.query_params.get("confirm")

        if not user_id or not confirm:
            return Response({"message": "Invalid verification link"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if confirm == "no":
            # Blacklist all active tokens
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)

            return Response({
                "message": "Suspicious login detected. All sessions have been logged out for your security."
            }, status=status.HTTP_200_OK)

        elif confirm == "yes":
            return Response({
                "message": "Thank you for confirming. Your account remains active."
            }, status=status.HTTP_200_OK)

        return Response({"error": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
    
class LogoutView(APIView):
    def post(self, request):
        response = Response({
            "message": "Logged out successfully"
        }, status=status.HTTP_200_OK)

        # Delete cookies
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

        return response

class RefreshTokenView(APIView):
    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            raise AuthenticationFailed("Authentication credentials were not provided")

        try:
            refresh = RefreshToken(refresh_token)
            new_access_token = str(refresh.access_token)
        except Exception:
            raise AuthenticationFailed("Invalid refresh token")

        response = Response({"message": "Access token refreshed"}, status=status.HTTP_200_OK)
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=3600,
        )

        return response
    
class CheckLoginView(APIView):
    def get(self, request):
        user = request.user

        # ✅ Step 1: Check if user is authenticated
        if user and not isinstance(user, AnonymousUser) and user.is_authenticated:
            return Response({
                'is_logged_in': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'phone': getattr(user, 'phone', None),
                }
            }, status=status.HTTP_200_OK)

        # ✅ Step 2: Check token in cookies if not authenticated
        access_token = request.COOKIES.get('access_token')
        if not access_token:
            return Response({
                'is_logged_in': False,
                'message': 'No access token found.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ✅ Step 3: Verify JWT token
        try:
            token = AccessToken(access_token)
            user_id = token['user_id']
            user = User.objects.get(id=user_id)
        except Exception as e:
            return Response({
                'is_logged_in': False,
                'message': f'Invalid or expired token: {str(e)}'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ✅ Step 4: If token valid, return user info
        return Response({
            'is_logged_in': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'phone': getattr(user, 'phone', None),
            }
        }, status=status.HTTP_200_OK)
        


# ---------------------------------------- End of Authentication Views --------------------------------------------------------------