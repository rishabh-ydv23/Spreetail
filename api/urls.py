from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CurrentUserView,
    ExpenseViewSet,
    GroupMemberViewSet,
    GroupViewSet,
    ImportBatchViewSet,
    ImportIssueViewSet,
    ImportRowViewSet,
    LoginView,
    SettlementViewSet,
)

router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'groups/(?P<group_pk>[^/.]+)/memberships', GroupMemberViewSet, basename='group-membership')
router.register(r'groups/(?P<group_pk>[^/.]+)/expenses', ExpenseViewSet, basename='group-expense')
router.register(r'groups/(?P<group_pk>[^/.]+)/settlements', SettlementViewSet, basename='group-settlement')
router.register(r'groups/(?P<group_pk>[^/.]+)/imports', ImportBatchViewSet, basename='group-import')
router.register(r'groups/(?P<group_pk>[^/.]+)/imports/(?P<importbatch_pk>[^/.]+)/issues', ImportIssueViewSet, basename='group-import-issue')
router.register(r'groups/(?P<group_pk>[^/.]+)/imports/(?P<importbatch_pk>[^/.]+)/rows', ImportRowViewSet, basename='group-import-row')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='api-login'),
    path('users/me/', CurrentUserView.as_view(), name='users-me'),
    path('', include(router.urls)),
]
