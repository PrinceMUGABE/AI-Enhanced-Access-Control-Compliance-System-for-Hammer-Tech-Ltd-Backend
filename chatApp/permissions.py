# chatApp/permissions.py
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from .models import ChatRoom, ChatParticipant, Message
from userApp.models import CustomUser


class IsMentorshipParticipantOrAdmin(permissions.BasePermission):
    """Allow participants, admin, and HR to access"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Admin and HR can access everything
        if request.user.role in ['admin', 'hr']:
            return True
        
        # Mentors and mentees can access their own mentorships
        return request.user.role in ['mentor', 'mentee']
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Admin and HR have full access
        if user.role in ['admin', 'hr']:
            return True
        
        # For ChatRoom objects
        if isinstance(obj, ChatRoom):
            # Check if user is a participant
            return obj.participants.filter(id=user.id).exists()
        
        # For Mentorship objects (if passed)
        if hasattr(obj, 'mentor') and hasattr(obj, 'mentee'):
            # Mentor can access if they're the mentor
            if user.role == 'mentor':
                return obj.mentor == user
            
            # Mentee can access if they're the mentee
            if user.role == 'mentee':
                return obj.mentee == user
        
        return False


class IsChatParticipant(permissions.BasePermission):
    """Allow only participants to access chat room"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Admin and HR have full access
        if user.role in ['admin', 'hr']:
            return True
        
        # For ChatRoom objects
        if isinstance(obj, ChatRoom):
            return obj.participants.filter(id=user.id).exists()
        
        # For Message objects
        if isinstance(obj, Message):
            return obj.chat_room.participants.filter(id=user.id).exists()
        
        return False


class CanManageChatRoom(permissions.BasePermission):
    """Allow only admin/HR to manage chat rooms"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # For ChatRoom objects
        if isinstance(obj, ChatRoom):
            return obj.can_manage(user)
        
        return False


class CanSendMessages(permissions.BasePermission):
    """Allow only participants who can send messages"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Admin and HR can always send messages
        if user.role in ['admin', 'hr']:
            return True
        
        # For ChatRoom objects
        if isinstance(obj, ChatRoom):
            return obj.participants.filter(id=user.id).exists()
        
        # For Message objects
        if isinstance(obj, Message):
            return obj.chat_room.participants.filter(id=user.id).exists()
        
        return False


class CanDeleteMessage(permissions.BasePermission):
    """Allow message sender or admin to delete messages"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # For Message objects
        if isinstance(obj, Message):
            return obj.can_delete(user)
        
        return False


class CanAddParticipants(permissions.BasePermission):
    """Allow only admin/HR to add participants"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # For ChatRoom objects
        if isinstance(obj, ChatRoom):
            return obj.can_add_participants(user)
        
        return False


class CanRemoveParticipants(permissions.BasePermission):
    """Allow only admin to remove participants"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Only admin can remove participants
        return request.user.role == 'admin'
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Only admin can remove participants
        return user.role == 'admin'


class IsAdminOrHR(permissions.BasePermission):
    """Allow only admin or HR users"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['admin', 'hr']