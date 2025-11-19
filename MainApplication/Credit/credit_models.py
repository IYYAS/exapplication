from django.db import models
from django.core.exceptions import ValidationError
from ..Authentication.models import User

class CreditModel(models.Model):
    credit = models.PositiveIntegerField(default=0)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        if not self.pk and CreditModel.objects.exists():
            raise ValidationError("Only one CreditModel instance is allowed.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Credit: {self.credit}, Value: ₹ {self.value} " 

    class Meta:
        verbose_name = 'Credit'
        verbose_name_plural = 'Credit Information'
        

class UserCreditVault(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit_vault')
    total_credits = models.PositiveIntegerField(default=0,null=True, blank=True)
    total_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,null=True, blank=True)
    gained_credits = models.PositiveIntegerField(default=0,null=True, blank=True)
    spent_credits = models.PositiveIntegerField(default=0,null=True, blank=True)
    purchased_credits = models.PositiveIntegerField(default=0,null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    def save(self, *args, **kwargs):
        # Fetch the single global CreditModel
        credit_model = CreditModel.objects.first()
        if credit_model:
            # Automatically calculate total value
            self.total_value = self.total_credits * credit_model.value
        else:
            # Fallback: no CreditModel defined
            self.total_value = 0
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.user.username}'s Credit Vault - Credits: {self.total_credits}, Value: ₹ {self.total_value}"
    
    class Meta:
        verbose_name = 'User Credit Vault'
        verbose_name_plural = 'User Credit Vaults'
        
    
class CreditTransactionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_transactions')
    transaction_type = models.CharField(max_length=50)  # e.g., Purchase, Spend, Gain
    credits_changed = models.IntegerField()  # Positive for gain/purchase, negative for spend
    value_changed = models.DecimalField(max_digits=10, decimal_places=2)  # Corresponding value change
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - Credits: {self.credits_changed}, Value: ₹ {self.value_changed} at {self.timestamp}"
    
    class Meta:
        verbose_name = 'Credit Transaction Log'
        verbose_name_plural = 'Credit Transaction Logs'
    


# Credit Coasts 

class CreditCostsModel(models.Model):
    following_cost = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    post_creation_cost = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    star_rating_cost = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    post_liking_cost = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk and CreditCostsModel.objects.exists():
            raise ValidationError("Only one CreditCostsModel instance is allowed.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Following Cost: {self.following_cost}, Post Creation Cost: {self.post_creation_cost}, Star Rating Cost: {self.star_rating_cost}, Post Liking Cost: {self.post_liking_cost}" 

    class Meta:
        verbose_name = 'Credit Costs'
        verbose_name_plural = 'Credit Costs Information'