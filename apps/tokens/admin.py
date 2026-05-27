from django.contrib import admin

from .models import PersonalToken


@admin.register(PersonalToken)
class PersonalTokenAdmin(admin.ModelAdmin):
    list_display = ("label", "user", "created_at", "last_used_at", "revoked_at")
    list_filter = ("revoked_at",)
    search_fields = ("label", "user__email", "user__username")
    readonly_fields = ("token_hash", "created_at", "last_used_at")
    actions = ["revoke_selected"]

    @admin.action(description="Revoke selected tokens")
    def revoke_selected(self, request, queryset):
        from django.utils import timezone

        n = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, f"Revoked {n} token(s).")
