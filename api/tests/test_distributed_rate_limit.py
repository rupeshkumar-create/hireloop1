from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from hireloop_api.services.distributed_rate_limit import check_distributed_rate_limit


@pytest.mark.asyncio
async def test_distributed_limit_allows_then_rejects() -> None:
    db = AsyncMock()
    db.fetchval.side_effect = [2, 3]

    await check_distributed_rate_limit(
        db,
        identity_hash="digest",
        bucket="public-chat",
        max_per_hour=2,
    )
    with pytest.raises(HTTPException) as exc:
        await check_distributed_rate_limit(
            db,
            identity_hash="digest",
            bucket="public-chat",
            max_per_hour=2,
        )

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0
