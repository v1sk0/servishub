"""
SQLAlchemy modeli za ServisHub.

Ovaj modul exportuje sve modele kako bi bili dostupni
za import iz app.models.
"""

from .tenant import Tenant, ServiceLocation, TenantStatus
from .user import TenantUser, UserLocation, UserRole
# Alias za kompatibilnost
User = TenantUser
from .admin import PlatformAdmin, AdminRole
from .audit import AuditLog, AuditAction, calculate_changes
from .admin_activity import AdminActivityLog, AdminActionType
from .ticket import ServiceTicket, TicketStatus, TicketPriority, TicketNotificationLog, get_next_ticket_number
from .inventory import PhoneListing, SparePart, PhoneCondition, PartVisibility, PartCategory
from .supplier import Supplier, SupplierListing, SupplierUser, SupplierStatus
from .order import PartOrder, PartOrderItem, PartOrderMessage, OrderStatus, SellerType, generate_order_number
from .representative import ServiceRepresentative, RepresentativeStatus, SubscriptionPayment

__all__ = [
    # Tenant modeli
    'Tenant',
    'ServiceLocation',
    'TenantStatus',
    # User modeli
    'TenantUser',
    'User',
    'UserLocation',
    'UserRole',
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
]
