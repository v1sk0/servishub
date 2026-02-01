"""
SQLAlchemy modeli za ServisHub.

Ovaj modul exportuje sve modele kako bi bili dostupni
za import iz app.models.
"""

from .tenant import Tenant, ServiceLocation, TenantStatus, LocationStatus
from .user import TenantUser, UserLocation, UserRole, TipUgovora, TipPlate
from .feature_flag import FeatureFlag, is_feature_enabled, seed_feature_flags
# Alias za kompatibilnost
User = TenantUser
from .admin import PlatformAdmin, AdminRole
from .audit import AuditLog, AuditAction, calculate_changes
from .admin_activity import AdminActivityLog, AdminActionType
from .ticket import ServiceTicket, TicketStatus, TicketPriority, TicketNotificationLog, get_next_ticket_number
from .inventory import PhoneListing, SparePart, PhoneCondition, PartVisibility, PartCategory, SparePartUsage, SparePartLog, StockActionType
from .supplier import Supplier, SupplierListing, SupplierUser, SupplierStatus
from .order import PartOrder, PartOrderItem, PartOrderMessage, OrderStatus, SellerType, generate_order_number
from .representative import ServiceRepresentative, RepresentativeStatus, SubscriptionPayment, PaymentStatus
from .email_verification import PendingEmailVerification
from .security_event import SecurityEvent, SecurityEventType, SecurityEventSeverity
from .platform_settings import PlatformSettings
from .tenant_message import TenantMessage, MessageType, MessagePriority, MessageCategory
from .service import ServiceItem, DEFAULT_CATEGORIES
from .tenant_public_profile import TenantPublicProfile
from .package_change_history import PackageChangeHistory, PackageChangeDelivery, DeliveryStatus
from .message_thread import (
    MessageThread, ThreadParticipant, Message,
    ThreadType, ThreadStatus, ThreadTag, HiddenByType
)
from .tenant_connection import Invite, TenantConnection, ConnectionStatus
from .supplier_reveal import SupplierReveal
from .public_user import PublicUser, PublicUserStatus
from .service_request import (
    ServiceRequest, ServiceBid,
    ServiceRequestStatus, ServiceRequestCategory, ServiceBidStatus
)
from .rating import Rating, RatingType
from .content_report import ContentReport, ReportReason, ReportStatus
from .pos import (
    CashRegisterSession, Receipt, ReceiptItem, DailyReport,
    PaymentMethod, ReceiptStatus, ReceiptType, CashRegisterStatus, SaleItemType
)
from .credits import (
    CreditBalance, CreditTransaction, CreditPurchase, PromoCode,
    OwnerType, CreditTransactionType, DiscountType, CreditPaymentStatus
)
from .goods import (
    GoodsItem, PurchaseInvoice, PurchaseInvoiceItem,
    StockAdjustment, PosAuditLog,
    InvoiceStatus, StockAdjustmentType,
    suggest_selling_price
)
from .financial_audit import FinancialAuditLog, FinancialCategory
from .bank_import import (
    BankStatementImport, BankTransaction,
    ImportStatus, BankCode, MatchStatus, TransactionType
)
from .tenant_google_integration import TenantGoogleIntegration, TenantGoogleReview
from .notification import (
    AdminNotificationSettings, NotificationLog,
    NotificationType, NotificationChannel, NotificationStatus, RATE_LIMITS
)
from .sms_management import (
    TenantSmsConfig, TenantSmsUsage,
    get_sms_stats_for_tenant, get_platform_sms_stats
)

__all__ = [
    # Tenant modeli
    'Tenant',
    'ServiceLocation',
    'TenantStatus',
    'LocationStatus',
    # Feature Flag modeli
    'FeatureFlag',
    'is_feature_enabled',
    'seed_feature_flags',
    # User modeli
    'TenantUser',
    'User',
    'UserLocation',
    'UserRole',
    'TipUgovora',
    'TipPlate',
    # Admin modeli
    'PlatformAdmin',
    'AdminRole',
    # Audit modeli
    'AuditLog',
    'AuditAction',
    'calculate_changes',
    # Admin Activity modeli
    'AdminActivityLog',
    'AdminActionType',
    # Ticket modeli
    'ServiceTicket',
    'TicketStatus',
    'TicketPriority',
    'TicketNotificationLog',
    'get_next_ticket_number',
    # Inventory modeli
    'PhoneListing',
    'SparePart',
    'PhoneCondition',
    'PartVisibility',
    'PartCategory',
    # Supplier modeli
    'Supplier',
    'SupplierListing',
    'SupplierUser',
    'SupplierStatus',
    # Order modeli
    'PartOrder',
    'PartOrderItem',
    'PartOrderMessage',
    'OrderStatus',
    'SellerType',
    'generate_order_number',
    # Representative modeli
    'ServiceRepresentative',
    'RepresentativeStatus',
    'SubscriptionPayment',
    'PaymentStatus',
    # Email Verification modeli
    'PendingEmailVerification',
    # Security Event modeli
    'SecurityEvent',
    'SecurityEventType',
    'SecurityEventSeverity',
    # Platform Settings
    'PlatformSettings',
    # Tenant Message modeli
    'TenantMessage',
    'MessageType',
    'MessagePriority',
    'MessageCategory',
    # Service modeli (Cenovnik)
    'ServiceItem',
    'DEFAULT_CATEGORIES',
    # Public Profile (Javna stranica)
    'TenantPublicProfile',
    # Package Change History (Verzioniranje promena cena)
    'PackageChangeHistory',
    'PackageChangeDelivery',
    'DeliveryStatus',
    # Message Thread (Threaded Messaging)
    'MessageThread',
    'ThreadParticipant',
    'Message',
    'ThreadType',
    'ThreadStatus',
    'ThreadTag',
    'HiddenByType',
    # Tenant Connection (T2T Networking)
    'Invite',
    'TenantConnection',
    'ConnectionStatus',
    # Supplier Reveal
    'SupplierReveal',
    # B2C Marketplace modeli
    'PublicUser',
    'PublicUserStatus',
    'ServiceRequest',
    'ServiceBid',
    'ServiceRequestStatus',
    'ServiceRequestCategory',
    'ServiceBidStatus',
    'Rating',
    'RatingType',
    'ContentReport',
    'ReportReason',
    'ReportStatus',
    # POS/Kasa modeli
    'CashRegisterSession',
    'Receipt',
    'ReceiptItem',
    'DailyReport',
    'PaymentMethod',
    'ReceiptStatus',
    'ReceiptType',
    'CashRegisterStatus',
    'SaleItemType',
    # Credit System modeli
    'CreditBalance',
    'CreditTransaction',
    'CreditPurchase',
    'PromoCode',
    'OwnerType',
    'CreditTransactionType',
    'DiscountType',
    'CreditPaymentStatus',
    # Inventory dopune (task-014)
    'SparePartUsage',
    'SparePartLog',
    'StockActionType',
    # Goods & Warehouse
    'GoodsItem',
    'PurchaseInvoice',
    'PurchaseInvoiceItem',
    'StockAdjustment',
    'PosAuditLog',
    'InvoiceStatus',
    'StockAdjustmentType',
    'suggest_selling_price',
    # Financial Audit
    'FinancialAuditLog',
    'FinancialCategory',
    # Bank Import (v303 Billing Enhancement)
    'BankStatementImport',
    'BankTransaction',
    'ImportStatus',
    'BankCode',
    'MatchStatus',
    'TransactionType',
    # Google Integration (Public Site)
    'TenantGoogleIntegration',
    'TenantGoogleReview',
    # Notification System
    'AdminNotificationSettings',
    'NotificationLog',
    'NotificationType',
    'NotificationChannel',
    'NotificationStatus',
    'RATE_LIMITS',
    # SMS Management
    'TenantSmsConfig',
    'TenantSmsUsage',
    'get_sms_stats_for_tenant',
    'get_platform_sms_stats',
]
