from django.contrib import admin
from .models import RepaymentSchedule, Repayment


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ('loan', 'period_number', 'scheduled_date', 'total_amount', 'amount_paid', 'status')
    list_filter = ('status', 'scheduled_date')
    search_fields = ('loan__client__email',)


@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'amount', 'actual_date', 'method', 'status')
    list_filter = ('method', 'status')
    search_fields = ('loan__client__email', 'reference')
