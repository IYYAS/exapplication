from rest_framework import serializers

from ..Authentication.models import User
from ..auth_utils import get_user_from_request

from .models import *

from ..Credit.credit_models import UserCreditVault, CreditTransactionLog


class UserCreditVaultSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    class Meta:
        model = UserCreditVault
        fields = "__all__"


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_credit_vault = UserCreditVaultSerializer(source='user.credit_vault', read_only=True)
    class Meta:
        model = UserProfileModel
        fields = "__all__"
        
    def create(self, validated_data):
        user = validated_data.get('user')
        if UserProfileModel.objects.filter(user=user).exists():
            raise ValueError("User profile already exists.")
        return super().create(validated_data)

    

class UserFollowingSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFollowingModel
        fields = "__all__"
    

class UserFollowersSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    class Meta:
        model = UserFollowersModel
        fields = "__all__"