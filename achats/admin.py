from django.contrib import admin

from .models import Article, Category, DailyEntry


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "articles_count")
    search_fields = ("name",)

    @admin.display(description="Articles")
    def articles_count(self, obj):
        return obj.articles.count()


class DailyEntryInline(admin.TabularInline):
    model = DailyEntry
    extra = 0
    readonly_fields = ("updated_at",)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "base_price", "unit", "is_active", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name",)
    inlines = [DailyEntryInline]


@admin.register(DailyEntry)
class DailyEntryAdmin(admin.ModelAdmin):
    list_display = ("article", "date", "done", "price", "quantity", "updated_at")
    list_filter = ("done", "date")
    search_fields = ("article__name",)
