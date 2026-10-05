"""URL configuration for the Wethu Micro Lenders web app."""

from django.urls import path
from django.contrib.auth import views as auth_views
from .views import vendors as vendors_views


from .views import public
from .views import staff_compliance
from .views import auth as web_auth
from .views import portal
from .views import loans_client
from .views import (
    documents_client,
    banking_client,
    profile_client,
    agreement_client,
    mandate_client,
    staff_mandates,
    staff_payments,
    staff,
    support_client,
    staff_support,
)


urlpatterns = [
    # ─────────────────────────────────────────────────────────────
    # PUBLIC
    # ─────────────────────────────────────────────────────────────
    path('', public.home, name='home'),
    path('about/', public.about, name='about'),
    path('how-it-works/', public.how_it_works, name='how_it_works'),
    path('products/', public.products, name='products'),
    path('affordability/', public.affordability, name='affordability'),
    path('faq/', public.faq, name='faq'),
    path('contact/', public.contact, name='contact'),
    path('security/', public.security, name='security'),
    path('privacy/', public.privacy, name='privacy'),
    path('terms/', public.terms, name='terms'),
    path('responsible-lending/', public.responsible_lending, name='responsible_lending'),
    path('accessibility/', public.accessibility, name='accessibility'),

    # ─────────────────────────────────────────────────────────────
    # AUTH
    # ─────────────────────────────────────────────────────────────
    path('login/', web_auth.login_view, name='login'),
    path('logout/', web_auth.logout_view, name='logout'),
    path('register/', web_auth.register_view, name='register'),
    path('password-change/', web_auth.password_change_view, name='password_change'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset.html',
        email_template_name='auth/password_reset_email.html',
        subject_template_name='auth/password_reset_subject.txt',
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html',
        success_url='/password-reset/complete/',
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('password-reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
            template_name='auth/password_reset_confirm.html',
            success_url='/password-reset/complete/',
         ), name='password_reset_confirm'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — dashboard, loans, payments, notifications
    # ─────────────────────────────────────────────────────────────
    path('portal/', portal.dashboard, name='portal_dashboard'),
    path('portal/loans/', portal.loan_list, name='client_loan_list'),
    path('portal/loans/apply/', loans_client.apply_start, name='client_loan_apply'),
    path('portal/loans/apply/preview/', loans_client.apply_preview, name='client_loan_apply_preview'),
    path('portal/loans/apply/submit/', loans_client.apply_submit, name='client_loan_apply_submit'),
    path('portal/loans/<uuid:loan_id>/', portal.loan_detail, name='client_loan_detail'),
    path('portal/loans/<uuid:loan_id>/schedule/', portal.loan_schedule, name='client_loan_schedule'),
    path('portal/payments/', portal.payments_list, name='client_payment_list'),
    path('portal/notifications/', portal.notifications_list, name='client_notification_list'),
    path('portal/notifications/<uuid:notification_id>/read/', portal.notification_mark_read, name='client_notification_read'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Documents
    # ─────────────────────────────────────────────────────────────
    path('portal/documents/', portal.documents_list, name='client_document_list'),
    path('portal/documents/upload/', documents_client.upload, name='client_document_upload'),
    path('portal/documents/<uuid:document_id>/download/', documents_client.download, name='client_document_download'),
    path('portal/documents/<uuid:document_id>/reextract/', documents_client.reextract, name='client_document_reextract'),
    path('portal/documents/<uuid:document_id>/request-replacement/', documents_client.request_replacement, name='client_document_request_replacement'),
    path('portal/documents/requests/<uuid:request_id>/cancel/', documents_client.request_replacement_cancel, name='client_document_request_cancel'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Bank statements
    # ─────────────────────────────────────────────────────────────
    path('portal/bank-statements/', banking_client.list_statements, name='client_bank_list'),
    path('portal/bank-statements/upload/', banking_client.upload_statement, name='client_bank_upload'),
    path('portal/bank-statements/<uuid:statement_id>/', banking_client.detail, name='client_bank_detail'),
    path('portal/bank-statements/<uuid:statement_id>/analyze/', banking_client.analyze, name='client_bank_analyze'),
    path('portal/bank-statements/<uuid:statement_id>/spending/', banking_client.statement_spending, name='client_bank_spending'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Loan agreement
    # ─────────────────────────────────────────────────────────────
    path('portal/loans/<uuid:loan_id>/agreement/', agreement_client.view_agreement, name='client_loan_agreement'),
    path('portal/loans/<uuid:loan_id>/agreement/download/', agreement_client.download_agreement, name='client_loan_agreement_download'),
    path('portal/loans/<uuid:loan_id>/agreement/accept/', agreement_client.accept_agreement, name='client_loan_agreement_accept'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Profile
    # ─────────────────────────────────────────────────────────────
    path('portal/profile/', profile_client.profile, name='client_profile'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Debit mandates
    # ─────────────────────────────────────────────────────────────
    path('portal/mandates/', mandate_client.mandate_list, name='client_mandate_list'),
    path('portal/loans/<uuid:loan_id>/mandate/new/', mandate_client.mandate_create, name='client_mandate_create'),
    path('portal/mandates/<uuid:mandate_id>/', mandate_client.mandate_detail, name='client_mandate_detail'),
    path('portal/mandates/<uuid:mandate_id>/sign/', mandate_client.mandate_sign, name='client_mandate_sign'),
    path('portal/mandates/<uuid:mandate_id>/download/', mandate_client.mandate_download, name='client_mandate_download'),

    # ─────────────────────────────────────────────────────────────
    # CLIENT PORTAL — Support tickets
    # ─────────────────────────────────────────────────────────────
    path('portal/support/', support_client.ticket_list, name='client_support_list'),
    path('portal/support/new/', support_client.ticket_create, name='client_support_create'),
    path('portal/support/<uuid:ticket_id>/', support_client.ticket_detail, name='client_support_detail'),
]


urlpatterns += [
    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — dashboard + AI
    # ─────────────────────────────────────────────────────────────
    path('staff/', staff.dashboard, name='staff_dashboard'),
    path('staff/ai-insights/', staff.ai_insights, name='staff_ai_insights'),
    path('staff/assistant/', staff.staff_chat, name='staff_chat'),
    path('staff/assistant/<uuid:conversation_id>/messages/', staff.staff_chat_messages,
         name='staff_chat_messages'),
    path('staff/assistant/<uuid:conversation_id>/send/', staff.staff_chat_send,
         name='staff_chat_send'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Applications
    # ─────────────────────────────────────────────────────────────
    path('staff/applications/', staff.applications_list, name='staff_applications_list'),
    path('staff/applications/<uuid:application_id>/', staff.application_detail, name='staff_application_detail'),
    path('staff/applications/<uuid:application_id>/transition/', staff.application_transition, name='staff_application_transition'),
    path('staff/applications/<uuid:application_id>/mark-documents-reviewed/',
         staff.application_mark_documents_reviewed,
         name='staff_application_mark_documents_reviewed'),
    path('staff/applications/<uuid:application_id>/mark-transactions-reviewed/',
         staff.application_mark_transactions_reviewed,
         name='staff_application_mark_transactions_reviewed'),
    path('staff/applications/<uuid:application_id>/verify-contract/',
         staff.application_verify_contract,
         name='staff_application_verify_contract'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — KYC review
    # ─────────────────────────────────────────────────────────────
    path('staff/kyc/', staff.kyc_list, name='staff_kyc_list'),
    path('staff/kyc/<uuid:profile_id>/action/', staff.kyc_action, name='staff_kyc_action'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Document review
    # ─────────────────────────────────────────────────────────────
    path('staff/documents/', staff.documents_list, name='staff_documents_list'),
    path('staff/documents/<uuid:document_id>/review/', staff.document_review, name='staff_document_review'),
    path('staff/documents/<uuid:document_id>/download/', staff.document_download, name='staff_document_download'),
    path('staff/replacements/<uuid:request_id>/review/', staff.replacement_review, name='staff_replacement_review'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Compliance
    # ─────────────────────────────────────────────────────────────
    path('staff/compliance/', staff_compliance.compliance_dashboard,
         name='staff_compliance_dashboard'),
    path('staff/compliance/policies/', staff_compliance.policy_list,
         name='staff_compliance_policies'),
    path('staff/compliance/tasks/', staff_compliance.task_list,
         name='staff_compliance_tasks'),
    path('staff/compliance/tasks/<uuid:task_id>/update/',
         staff_compliance.task_update, name='staff_compliance_task_update'),
    path('staff/compliance/dsars/', staff_compliance.dsar_list,
         name='staff_compliance_dsars'),
    path('staff/compliance/dsars/<uuid:dsar_id>/',
         staff_compliance.dsar_detail, name='staff_compliance_dsar_detail'),
    path('staff/compliance/dsars/<uuid:dsar_id>/complete/',
         staff_compliance.dsar_complete, name='staff_compliance_dsar_complete'),
    path('staff/compliance/dsars/<uuid:dsar_id>/refuse/',
         staff_compliance.dsar_refuse, name='staff_compliance_dsar_refuse'),
    path('staff/compliance/incidents/', staff_compliance.incident_list,
         name='staff_compliance_incidents'),
    path('staff/compliance/incidents/<uuid:incident_id>/',
         staff_compliance.incident_detail, name='staff_compliance_incident_detail'),
    path('staff/compliance/incidents/<uuid:incident_id>/action/',
         staff_compliance.incident_action, name='staff_compliance_incident_action'),
    path('staff/compliance/processors/', staff_compliance.processor_list,
         name='staff_compliance_processors'),
    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Mandates
    # ─────────────────────────────────────────────────────────────
    path('staff/mandates/', staff_mandates.mandate_review_list, name='staff_mandate_list'),
    path('staff/mandates/<uuid:mandate_id>/', staff_mandates.mandate_review_detail, name='staff_mandate_detail'),
    path('staff/mandates/<uuid:mandate_id>/approve/', staff_mandates.mandate_approve, name='staff_mandate_approve'),
    path('staff/mandates/<uuid:mandate_id>/reject/', staff_mandates.mandate_reject, name='staff_mandate_reject'),
    path('staff/mandates/<uuid:mandate_id>/download/', staff_mandates.mandate_download, name='staff_mandate_download'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Loans + collection controls
    # ─────────────────────────────────────────────────────────────
    path('staff/loans/', staff.loans_list, name='staff_loans_list'),
    path('staff/loans/<uuid:loan_id>/', staff.loan_detail, name='staff_loan_detail'),
    path('staff/loans/<uuid:loan_id>/set-collection-day/',
         staff.loan_set_collection_day,
         name='staff_loan_set_collection_day'),
    path('staff/loans/<uuid:loan_id>/collection-window/',
         staff_payments.loan_set_collection_window,
         name='staff_loan_set_collection_window'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Retry queue
    # ─────────────────────────────────────────────────────────────
    path('staff/payments/retry-queue/',
         staff_payments.retry_queue,
         name='staff_retry_queue'),
    path('staff/payments/<uuid:txn_id>/retry/',
         staff_payments.retry_schedule,
         name='staff_retry_schedule'),
    path('staff/payments/<uuid:txn_id>/retry/cancel/',
         staff_payments.retry_cancel,
         name='staff_retry_cancel'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Collections, reconciliation, fraud, audit
    # ─────────────────────────────────────────────────────────────
    path('staff/collections/', staff.collections, name='staff_collections'),
    path('staff/reconciliation/', staff.reconciliation, name='staff_reconciliation'),
    path('staff/fraud/', staff.fraud_list, name='staff_fraud_list'),
    path('staff/fraud/<uuid:alert_id>/', staff.fraud_detail, name='staff_fraud_detail'),
    path('staff/fraud/<uuid:alert_id>/action/', staff.fraud_action, name='staff_fraud_action'),
    path('staff/audit/', staff.audit_list, name='staff_audit_list'),

    # ─────────────────────────────────────────────────────────────
    # STAFF PORTAL — Support queue
    # ─────────────────────────────────────────────────────────────
    path('staff/support/', staff_support.ticket_queue, name='staff_support_list'),
    path('staff/support/<uuid:ticket_id>/', staff_support.ticket_detail, name='staff_support_detail'),
    path('staff/support/<uuid:ticket_id>/assign/', staff_support.ticket_assign_me, name='staff_support_assign'),
    path('staff/support/<uuid:ticket_id>/transition/', staff_support.ticket_transition, name='staff_support_transition'),
]



urlpatterns += [
    path('vendor/', vendors_views.vendor_dashboard, name='vendor_dashboard'),
]