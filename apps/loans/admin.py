"""Admin configuration for loans."""
from django.contrib import admin, messages
from django.utils.html import format_html

from apps.ai.models import AIAffordabilityAssessment
from apps.payments.models import DebitInstruction

from .models import Loan, LoanAgreement, LoanApplication, LoanApplicationEvent, LoanProduct


class DebitInstructionInline(admin.StackedInline):
    """Inline used on LoanAdmin — DebitInstruction FK points at Loan, not Application."""
    model = DebitInstruction
    extra = 0
    fields = (
        'status', 'bank_name', 'account_number_last4', 'account_type',
        'mandate_reference', 'mandate_signed_at',
        'reviewed_by', 'reviewed_at', 'review_notes',
    )
    readonly_fields = ('mandate_signed_at',)
    can_delete = False
    show_change_link = True


class AIAffordabilityInline(admin.StackedInline):
    model = AIAffordabilityAssessment
    extra = 0
    fields = (
        'verdict', 'confidence', 'dti_ratio', 'disposable_income',
        'reasons', 'risk_factors', 'positive_factors',
        'recommended_max_amount', 'recommended_term_months',
        'created_at',
    )
    readonly_fields = (
        'verdict', 'confidence', 'dti_ratio', 'disposable_income',
        'reasons', 'risk_factors', 'positive_factors',
        'recommended_max_amount', 'recommended_term_months', 'created_at',
    )
    can_delete = False
    max_num = 1
    verbose_name = 'AI Affordability Assessment'
    verbose_name_plural = 'AI Affordability Assessments'


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'interest_rate', 'min_amount', 'max_amount', 'min_term', 'max_term', 'is_active')
    list_filter = ('interest_type', 'repayment_frequency', 'is_active')
    search_fields = ('name', 'description')


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client', 'requested_amount', 'status',
        'affordability_badge', 'mandate_status', 'created_at',
    )
    list_filter = ('status', 'product', 'created_at')
    search_fields = ('client__email', 'client__first_name', 'client__last_name', 'id')
    readonly_fields = (
        'id', 'client', 'product', 'created_at', 'updated_at',
        'submitted_at', 'reviewed_at', 'kyc_status_snapshot',
    )
    inlines = [AIAffordabilityInline]
    actions = [
        'action_run_affordability',
        'action_approve',
        'action_reject',
        'action_activate_mandate',
        'action_trigger_disbursement',
    ]

    def affordability_badge(self, obj):
        a = obj.ai_affordability_assessments.order_by('-created_at').first()
        if not a:
            return '—'
        colors = {
            'likely_to_pay': '#10b981',
            'at_risk': '#f59e0b',
            'unlikely_to_pay': '#ef4444',
            'insufficient_data': '#6b7280',
        }
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            colors.get(a.verdict, '#6b7280'),
            a.get_verdict_display(),
        )
    affordability_badge.short_description = 'AI Verdict'

    def mandate_status(self, obj):
        loan = getattr(obj, 'loan', None)
        if not loan:
            return '—'
        m = loan.debit_instructions.order_by('-created_at').first()
        return m.get_status_display() if m else '—'
    mandate_status.short_description = 'Mandate'

    @admin.action(description='Run AI affordability check')
    def action_run_affordability(self, request, queryset):
        from apps.ai.services import AIService
        count = 0
        for app in queryset:
            try:
                AIService.assess_affordability(app, actor=request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"{app.id}: {e}", messages.ERROR)
        self.message_user(request, f"Ran affordability on {count} application(s).")

    @admin.action(description='Approve selected (creates loan + mandate draft)')
    def action_approve(self, request, queryset):
        from apps.loans.services import LoanApplicationService
        count = 0
        for app in queryset:
            try:
                if app.status != 'approved':
                    LoanApplicationService.transition(
                        app, 'approved', request.user,
                        notes='Approved via admin',
                    )
                LoanApplicationService.transition(
                    app, 'mandate_required', request.user,
                    notes='Requesting client mandate',
                )
                count += 1
            except ValueError as e:
                self.message_user(request, f"{app.id}: {e}", messages.ERROR)
        self.message_user(request, f"Approved {count} application(s).")

    @admin.action(description='Reject selected')
    def action_reject(self, request, queryset):
        from apps.loans.services import LoanApplicationService
        count = 0
        for app in queryset:
            try:
                LoanApplicationService.transition(
                    app, 'rejected', request.user, notes='Rejected via admin',
                )
                count += 1
            except ValueError as e:
                self.message_user(request, f"{app.id}: {e}", messages.ERROR)
        self.message_user(request, f"Rejected {count} application(s).")

    @admin.action(description='Activate mandate → advance to agreement')
    def action_activate_mandate(self, request, queryset):
        from apps.payments.services import PaymentService
        count = 0
        for app in queryset:
            loan = getattr(app, 'loan', None)
            if not loan:
                continue
            m = loan.debit_instructions.filter(status='pending_review').first()
            if not m:
                continue
            try:
                PaymentService.activate_mandate(
                    m, request.user, notes='Activated via admin',
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"{app.id}: {e}", messages.ERROR)
        self.message_user(request, f"Activated {count} mandate(s).")

    @admin.action(description='Trigger disbursement')
    def action_trigger_disbursement(self, request, queryset):
        from apps.loans.services import LoanApplicationService
        from apps.payments.tasks import process_disbursement
        count = 0
        for app in queryset:
            try:
                LoanApplicationService.transition(
                    app, 'disbursement_pending', request.user,
                    notes='Disbursement initiated via admin',
                )
                process_disbursement.delay(str(app.id))
                count += 1
            except ValueError as e:
                self.message_user(request, f"{app.id}: {e}", messages.ERROR)
        self.message_user(request, f"Triggered disbursement for {count} application(s).")


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'principal_amount', 'interest_rate', 'status', 'outstanding_balance')
    list_filter = ('status',)
    search_fields = ('client__email',)
    readonly_fields = ('id', 'application', 'client', 'created_at', 'updated_at')
    inlines = [DebitInstructionInline]


@admin.register(LoanAgreement)
class LoanAgreementAdmin(admin.ModelAdmin):
    list_display = ('id', 'loan', 'version', 'status', 'generated_at', 'accepted_at')
    list_filter = ('status',)
    readonly_fields = ('id', 'agreement_hash', 'generated_at', 'accepted_at',
                       'accepted_by', 'accepted_ip', 'accepted_user_agent')


@admin.register(LoanApplicationEvent)
class LoanApplicationEventAdmin(admin.ModelAdmin):
    list_display = ('application', 'from_status', 'to_status', 'actor', 'timestamp')
    list_filter = ('from_status', 'to_status')
    search_fields = ('application__client__email',)
    readonly_fields = ('id', 'application', 'from_status', 'to_status', 'actor', 'notes', 'timestamp')