"""Model package: import all modules so Base.metadata is complete."""
from app.models.identity import AuditLog, User, Workspace, WorkspaceMember
from app.models.research import (
    ChatMessage,
    CollectionJob,
    Comment,
    Conversation,
    QuotaUsage,
    ResearchKeyword,
    ResearchPlan,
    ResearchSession,
    TopicRecord,
    AspectSentiment,
    TrackedChannel,
    TrackedVideo,
    VideoStatsSnapshot,
)
from app.models.audience import AnomalyDetection, AudienceCluster, ClusterMember
from app.models.campaign import (
    AdsCampaign,
    AdsCampaignPerformance,
    BudgetAllocation,
    BudgetRun,
    CampaignBrief,
    Finding,
    GeneratedReport,
    GoogleConnection,
)

__all__ = [n for n in dir() if not n.startswith("_")]
