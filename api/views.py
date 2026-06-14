from rest_framework import mixins, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Expense, Group, GroupMember, ImportBatch, ImportIssue, ImportRow, Settlement
from .permissions import IsGroupMember
from .services import BalanceService, CSVImportService
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
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


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

    @action(detail=True, methods=['get'])
    def balances(self, request, pk=None):
        balances = BalanceService.compute_member_balances(pk)
        return Response({
            'group_id': pk,
            'currency': self.get_object().currency,
            'net_balances': [{
                'user_id': str(user_id),
                'net_balance': str(amount),
            } for user_id, amount in balances.items()],
        })

    @action(detail=True, methods=['get'], url_path='balances/simplified-settlements')
    def simplified_settlements(self, request, pk=None):
        balances = BalanceService.compute_member_balances(pk)
        suggested = BalanceService.simplified_settlements(balances)
        return Response({
            'group_id': pk,
            'currency': self.get_object().currency,
            'suggested_settlements': [
                {'from_user_id': str(item['from_user_id']), 'to_user_id': str(item['to_user_id']), 'amount': str(item['amount'])}
                for item in suggested
            ],
        })


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

    def create(self, request, *args, **kwargs):
        group_id = self.kwargs['group_pk']
        group = Group.objects.get(id=group_id)
        file = request.FILES.get('file')
        if file is None:
            return Response({'detail': 'CSV file is required.'}, status=400)

        raw_content = file.read()
        batch = CSVImportService.create_import_batch(
            group=group,
            imported_by=request.user,
            source_file_name=file.name,
            raw_content=raw_content,
        )
        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None, **kwargs):
        batch = self.get_object()
        approve_all = request.data.get('approve_all', False)
        try:
            CSVImportService.commit_batch(batch, approve_all=approve_all)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        serializer = self.get_serializer(batch)
        return Response(serializer.data)

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
