from functools import lru_cache

from app.core.dependencies import get_library_provider, get_storage_provider
from app.modules.editing.provider.edit_provider import EditProvider
from app.modules.editing.provider.plan_provider import PlanProvider
from app.modules.editing.provider.revision_provider import RevisionProvider
from app.modules.editing.provider.writer_provider import WriterProvider
from app.modules.review.api.dependencies import get_llm_backend


@lru_cache
def get_revision_provider() -> RevisionProvider:
    return RevisionProvider(
        storage=get_storage_provider(),
        library=get_library_provider(),
    )


@lru_cache
def get_edit_provider() -> EditProvider:
    llm = get_llm_backend()

    return EditProvider(
        revisions=get_revision_provider(),
        planner=PlanProvider(llm=llm),
        writer=WriterProvider(llm=llm),
    )


# Notes
#
# The LLM backend is borrowed from the review module rather than built again
# here. There is one model client per process, so editing and review share a
# cache and a rate limit budget instead of quietly competing for one.
#
# With no API key that borrowed backend is the stub, which means the edit
# routes stay reachable offline. A planner backed by the stub returns no
# operations, so a command produces an empty proposal that changes nothing,
# which is the correct offline behaviour rather than an error.
#
# RevisionProvider is separate and separately cached because the export route
# will need to read revisions without pulling a model client into its
# dependency graph.
