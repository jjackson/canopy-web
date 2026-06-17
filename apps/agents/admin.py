from django.contrib import admin

from .models import Agent, AgentSkill, AgentSync, AgentTask, AgentWorkProduct


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "email", "owner", "updated_at")
    search_fields = ("slug", "name", "email")


@admin.register(AgentSync)
class AgentSyncAdmin(admin.ModelAdmin):
    list_display = ("agent", "title", "period_end", "source", "created_at")
    list_filter = ("agent", "source")


@admin.register(AgentWorkProduct)
class AgentWorkProductAdmin(admin.ModelAdmin):
    list_display = ("agent", "title", "kind", "created_at")
    list_filter = ("agent", "kind")


@admin.register(AgentSkill)
class AgentSkillAdmin(admin.ModelAdmin):
    list_display = ("agent", "name", "updated_at")
    list_filter = ("agent",)


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ("agent", "title", "status", "priority", "owner", "due", "updated_at")
    list_filter = ("agent", "status", "priority")
