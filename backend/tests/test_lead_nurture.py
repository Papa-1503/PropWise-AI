"""
Lead nurture tests — real functional tests against the mock database
(no mocking of the nurture logic itself, only the outbound email send,
since real email delivery can't run in tests). What's under real
test: does the day 3/7/14 schedule fire at the right thresholds, does
it never re-send a stage already sent, does it correctly stop for
leads that have moved past "new" status, and does a failed send leave
nurtureStage unchanged so a retry is possible next cycle.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

async def _insert_lead(patch_db_with_mock, days_old, status="new", nurture_stage=0, **overrides):
    created_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    doc = {
        "name": "Jane Prospect", "email": "jane@example.com", "phone": None,
        "propertyId": None, "unitId": None, "message": "Interested in a 1BR",
        "status": status, "createdAt": created_at, "nurtureStage": nurture_stage,
    }
    doc.update(overrides)
    result = await patch_db_with_mock["leads"].insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_day3_touch_fires_for_a_3_day_old_new_lead(client, patch_db_with_mock):
    lead_id = await _insert_lead(patch_db_with_mock, days_old=3)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        result = await lead_nurture_service._do_lead_nurture_check()

    assert result["sent"] == 1
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "jane@example.com"
    assert "still something you're interested" in call_kwargs["body_text"].lower()

    from bson import ObjectId
    lead = await patch_db_with_mock["leads"].find_one({"_id": ObjectId(lead_id)})
    assert lead["nurtureStage"] == 1
    assert lead["lastNurturedAt"] is not None


@pytest.mark.asyncio
async def test_no_touch_fires_for_a_1_day_old_lead(client, patch_db_with_mock):
    await _insert_lead(patch_db_with_mock, days_old=1)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        result = await lead_nurture_service._do_lead_nurture_check()

    assert result["sent"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_stage_never_resent_once_already_sent(client, patch_db_with_mock):
    """A 3-day-old lead that already got its day-3 touch (nurtureStage=1)
    must not get sent again, even though it still qualifies by age."""
    await _insert_lead(patch_db_with_mock, days_old=3, nurture_stage=1)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        result = await lead_nurture_service._do_lead_nurture_check()

    assert result["sent"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_day7_touch_fires_and_skips_ahead_correctly(client, patch_db_with_mock):
    """A 7-day-old lead that already got day 3 (stage=1) should get the
    real day-7 template (stage 2), not a duplicate day-3 send."""
    lead_id = await _insert_lead(patch_db_with_mock, days_old=7, nurture_stage=1)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        await lead_nurture_service._do_lead_nurture_check()

    call_kwargs = mock_send.call_args.kwargs
    assert "following up" in call_kwargs["subject"].lower()

    from bson import ObjectId
    lead = await patch_db_with_mock["leads"].find_one({"_id": ObjectId(lead_id)})
    assert lead["nurtureStage"] == 2


@pytest.mark.asyncio
async def test_day14_touch_is_the_final_one(client, patch_db_with_mock):
    lead_id = await _insert_lead(patch_db_with_mock, days_old=20, nurture_stage=2)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        await lead_nurture_service._do_lead_nurture_check()

    call_kwargs = mock_send.call_args.kwargs
    assert "final" in call_kwargs["subject"].lower() or "final" in call_kwargs["body_text"].lower()

    from bson import ObjectId
    lead = await patch_db_with_mock["leads"].find_one({"_id": ObjectId(lead_id)})
    assert lead["nurtureStage"] == 3

    # Running the check again must not re-send - stage 3 is the real, final stage.
    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send_again:
        result_again = await lead_nurture_service._do_lead_nurture_check()
    assert result_again["sent"] == 0
    mock_send_again.assert_not_called()


@pytest.mark.asyncio
async def test_leads_past_new_status_are_never_nurtured(client, patch_db_with_mock):
    """The real stop condition - a lead marked toured/applied/signed/
    declined must never get a nurture email, no matter how old."""
    for status in ("toured", "applied", "signed", "declined"):
        await _insert_lead(patch_db_with_mock, days_old=30, status=status, email=f"{status}@example.com")

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        result = await lead_nurture_service._do_lead_nurture_check()

    assert result["sent"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_failed_send_leaves_stage_unchanged_for_retry(client, patch_db_with_mock):
    import email_service
    lead_id = await _insert_lead(patch_db_with_mock, days_old=3)

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = email_service.EmailSendError("simulated failure")
        result = await lead_nurture_service._do_lead_nurture_check()

    assert result["sent"] == 0
    assert result["failed"] == 1

    from bson import ObjectId
    lead = await patch_db_with_mock["leads"].find_one({"_id": ObjectId(lead_id)})
    assert lead["nurtureStage"] == 0  # unchanged - a real retry next cycle is still possible


@pytest.mark.asyncio
async def test_uses_real_property_and_unit_when_present(client, patch_db_with_mock):
    property_result = await patch_db_with_mock["properties"].insert_one({
        "name": "Maple Ridge", "orgId": "org1", "units": [],
    })
    property_id = str(property_result.inserted_id)
    await _insert_lead(patch_db_with_mock, days_old=3, propertyId=property_id, unitId="4B")

    import lead_nurture_service
    with patch("lead_nurture_service.send_email_async", new_callable=AsyncMock) as mock_send:
        await lead_nurture_service._do_lead_nurture_check()

    call_kwargs = mock_send.call_args.kwargs
    assert "Unit 4B" in call_kwargs["body_text"]
    assert "Maple Ridge" in call_kwargs["body_text"]
