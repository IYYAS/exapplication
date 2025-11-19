from django.shortcuts import render
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from django.db.models import Q

import platform
import datetime
import urllib.parse
import re
import json

from ..Authentication.models import User
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken


from ..auth_utils import get_user_from_request
from .models import *
from .serializers import *
from ..Credit.credit_models import UserCreditVault, CreditTransactionLog, CreditModel, CreditCostsModel


from rest_framework.permissions import IsAuthenticated, AllowAny

from django_smart_ratelimit import rate_limit

import redis
from django.conf import settings
from django.http import JsonResponse




r = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True
)


class EditUsernameView(APIView):
    def get(self, request):
        new_username = request.query_params.get("username", "").strip()
        user = get_user_from_request(request)

        if not user:
            return Response({
                "message": "Invalid or missing user",
                "is_available": False,
                "color": "red"
            })

        # --- If user entered their same username ---
        if new_username == user.username:
            return Response({
                "message": "This is your current username",
                "is_available": True,
                "color": "blue"
            })

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

        
    def put(self, request):
        new_username = request.query_params.get("username", "").strip()
        user = get_user_from_request(request)

        if not user:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        if not new_username:
            return Response({"detail": "Username cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        if not re.match(r'^[A-Za-z0-9_.]+$', new_username):
            return Response({"detail": "Only letters, numbers, underscores and periods are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_username) < 3 or len(new_username) > 30:
            return Response({"detail": "Username must be 3 - 30 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username__iexact=new_username).exists():
            return Response({"detail": "Username already taken."}, status=status.HTTP_400_BAD_REQUEST)

        user.username = new_username
        user.save()

        return Response({"detail": "Username updated successfully."})



class UserProfileAPIView(APIView):
    def get(self, request):
        try:
            # Connect to Redis
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )

            # Get the current user
            user = get_user_from_request(request)
            if not user:
                return Response(
                    {"detail": "Authentication credentials were not provided."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Create a unique cache key for the user's profile
            cache_key = f"user_profile:{user.id}"

            # Try to fetch profile data from Redis
            cached_profile = r.get(cache_key)
            if cached_profile:
                return JsonResponse({
                    "status": "success",
                    "cached": True,
                    "data": eval(cached_profile)
                })

            # If not found in cache, fetch from DB
            profile = UserProfileModel.objects.filter(user=user).first()
            if not profile:
                return Response(
                    {"detail": "User profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = UserProfileSerializer(profile)

            # Store the serialized data in Redis for 10 minutes (600 seconds)
            r.setex(cache_key, 600, str(serializer.data))

            return JsonResponse({
                "status": "success",
                "cached": False,
                "data": serializer.data
            })

        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            })

    
    def put(self, request):
        user = get_user_from_request(request)
        phone = request.data.get("phone")
        if not user:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        
        profile = UserProfileModel.objects.filter(user=user)
        if not profile.exists():
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserProfileSerializer(profile.first(), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        user = get_user_from_request(request)
        if not user:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        
        profile = UserProfileModel.objects.filter(user=user)
        if not profile.exists():
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserProfileSerializer(profile.first(), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# User Follow/Unfollow API
class UserFollowingAPIView(APIView):
    def get(self, request):
        try:
            # Connect to Redis
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )

            # Get authenticated user
            user = get_user_from_request(request)
            if not user:
                return Response(
                    {"detail": "Authentication credentials were not provided."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            profile = UserProfileModel.objects.filter(user=user).first()
            if not profile:
                return Response(
                    {"detail": "User profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Handle search
            search = request.query_params.get("search", "").strip()

            # Create a unique Redis key for this query
            cache_key = f"user_following:{user.id}:{search if search else 'all'}"

            # Try to get data from Redis
            cached_data = r.get(cache_key)
            if cached_data:
                return JsonResponse({
                    "status": "success",
                    "cached": True,
                    "data": eval(cached_data)  # Convert string back to list/dict
                })

            # If not cached, query the database
            if search:
                following = UserFollowingModel.objects.filter(
                    user_profile=profile,
                    following__user__username__icontains=search
                )
            else:
                following = UserFollowingModel.objects.filter(user_profile=profile)

            serializer = UserFollowingSerializer(following, many=True, context={'request': request})

            # Cache the data in Redis for 10 minutes (600 seconds)
            r.setex(cache_key, 600, str(serializer.data))

            return JsonResponse({
                "status": "success",
                "cached": False,
                "data": serializer.data
            })

        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            })
    
    def post(self, request):
        
        # fetch user from request
        user = get_user_from_request(request)
        
        # fetch username to follow/unfollow
        following_username = request.data.get("username", "").strip()
        
        # fetch user's total credits
        total_credit = UserCreditVault.objects.filter(user=user).first()
        
        # fetch user's following cost 
        following_credit_cost =  CreditCostsModel.objects.first().following_cost
        
        # calculate user's total credits
        user_total_credit = total_credit.total_credits if total_credit else 0

        
        if not user:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        
        if not following_username:
            return Response({"detail": "Following username cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        
        user_profile = UserProfileModel.objects.filter(user=user)
        following_profile = UserProfileModel.objects.filter(user__username=following_username)
        if not user_profile.exists() or not following_profile.exists():
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)
        
        follow_data = UserFollowingModel.objects.filter(user_profile=user_profile.first(), following=following_profile.first())
        
        
        # If already following or unfollowing
        
        if follow_data.exists():
            
            # Toggle follow/unfollow
            
            if follow_data.first().followed == True:
                
                # Unfollow
                
                follow_data.update(followed=False)
                return Response({"detail": f"You have unfollowed {following_username}."})
            
            elif follow_data.first().followed == False:
                
                # Refollow
                
                if user_total_credit < following_credit_cost:
                    
                    return Response({"detail": "Insufficient credits to follow this user."}, status=status.HTTP_400_BAD_REQUEST)
                
                follow_data.update(followed=True)
                total_credit.total_credits = user_total_credit - following_credit_cost
                total_credit.total_value = total_credit.total_value - (following_credit_cost * (CreditModel.objects.first().value / CreditModel.objects.first().credit))
                total_credit.save()
                
                # credit transaction log
                CreditTransactionLog.objects.create(
                    user=user,
                    transaction_type="Follow User",
                    credits_changed=-following_credit_cost,
                    value_changed=-(following_credit_cost * (CreditModel.objects.first().value / CreditModel.objects.first().credit)),
                    description=f"Followed user {following_username}",
                )           
                     
                return Response({"detail": f"You are now following {following_username}."})
        else:
            
            # New follow
            
            UserFollowingModel.objects.create(user_profile=user_profile.first(), following=following_profile.first(), followed=True)
            
            total_credit.total_credits = user_total_credit - following_credit_cost
            total_credit.total_value = total_credit.total_value - (following_credit_cost * (CreditModel.objects.first().value / CreditModel.objects.first().credit))
            total_credit.save()
            
            # credit transaction log
            CreditTransactionLog.objects.create(
                user=user,
                transaction_type="Follow User",
                credits_changed=-following_credit_cost,
                value_changed=-(following_credit_cost * (CreditModel.objects.first().value / CreditModel.objects.first().credit)),
                description=f"Followed user {following_username}",
            )
            
            return Response({"detail": f"You are now following {following_username}."})
        
        return Response({"detail": "Something went wrong."}, status=status.HTTP_400_BAD_REQUEST)
            
        

class HelloworldView(APIView):
    permission_classes = [AllowAny]

    @rate_limit(key='ip', rate='5/m', block=True)
    def get(self, request):
        return Response({"message": "Hello, world!"})
    
    
    
def test_redis_view(request):
    try:
        # Connect to Redis
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True  # Decode bytes to string
        )

        # Test set/get
        r.set('test_key', 'Hello Redis!')
        value = r.get('test_key')

        return JsonResponse({
            'status': 'success',
            'message': 'Redis is working!',
            'stored_value': value
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })
        
        