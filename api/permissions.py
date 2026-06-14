from typing import Optional

from django.shortcuts import get_object_or_404
from rest_framework import permissions

from .models import Group, GroupMember


class IsGroupMember(permissions.BasePermission):
    message = 'User must be a member of this group.'

    def has_permission(self, request, view):
        group_id = view.kwargs.get('group_pk') or view.kwargs.get('pk')
        if not group_id:
            return True
        return self._user_in_group(request.user, group_id)

    def has_object_permission(self, request, view, obj):
        group = getattr(obj, 'group', None)
        if group is not None:
            return self._user_in_group(request.user, group.id)
        return True

    def _user_in_group(self, user, group_id: str) -> bool:
        return GroupMember.objects.filter(group_id=group_id, user=user).exists()
