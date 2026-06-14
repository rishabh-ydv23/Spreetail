from rest_framework import mixins, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Group, GroupMember, ImportBatch, ImportIssue, ImportRow, Settlement
from .permissions import IsGroupMember
from .serializers import (
    ExpenseSerializer,
    GroupMemberSerializer,
    GroupSerializer,
    ImportBatchSerializer,
    ImportIssueSerializer,
    ImportRowSerializer,
    SettlementSerializer,
    UserSerializer,
)


class LoginView(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = response.data['token']
        user = self.user
        payload = {
            'token': token,
            'user': UserSerializer(user).data,
        }
        return Response(payload)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class GroupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

    def get_queryset(self):
        return self.queryset.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class GroupMemberViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsGroupMember]
    queryset = GroupMember.objects.all()
    serializer_class = GroupMemberSerializer

    def get_queryset(self):
        group_id = self.kwargs['group_pk']
        return self.queryset.filter(group_id=group_id)

    def perform_create(self, serializer):
        group_id = self.kwargs['group_pk']
        serializer.save(group_id=group_id)


class ExpenseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsGroupMember]
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        group_id = self.kwargs['group_pk']
        return self.queryset.filter(group_id=group_id)

    def perform_create(self, serializer):
        group_id = self.kwargs['group_pk']
        serializer.save(group_id=group_id, created_by=self.request.user)


class SettlementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsGroupMember]
    queryset = Settlement.objects.all()
    serializer_class = SettlementSerializer

    def get_queryset(self):
        group_id = self.kwargs['group_pk']
        return self.queryset.filter(group_id=group_id)

    def perform_create(self, serializer):
        group_id = self.kwargs['group_pk']
        serializer.save(group_id=group_id, created_by=self.request.user)


class ImportBatchViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsGroupMember]
    queryset = ImportBatch.objects.all()
    serializer_class = ImportBatchSerializer

    def get_queryset(self):
        group_id = self.kwargs['group_pk']
        return self.queryset.filter(group_id=group_id)

    def perform_create(self, serializer):
        group_id = self.kwargs['group_pk']
        serializer.save(imported_by=self.request.user, group_id=group_id)

    @action(detail=True, methods=['get'])
    def issues(self, request, pk=None):
        batch = self.get_object()
        issues = batch.issues.all()
        serializer = ImportIssueSerializer(issues, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        batch = self.get_object()
        report_data = {
            'id': str(batch.id),
            'status': batch.status,
            'total_rows': batch.total_rows,
            'valid_rows': batch.valid_rows,
            'issue_count': batch.issue_count,
        }
        return Response(report_data)


class ImportIssueViewSet(viewsets.ModelViewSet):
    queryset = ImportIssue.objects.all()
    serializer_class = ImportIssueSerializer

    def get_queryset(self):
        batch_id = self.kwargs['importbatch_pk']
        return self.queryset.filter(import_batch_id=batch_id)


class ImportRowViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ImportRow.objects.all()
    serializer_class = ImportRowSerializer

    def get_queryset(self):
        batch_id = self.kwargs['importbatch_pk']
        return self.queryset.filter(import_batch_id=batch_id)
