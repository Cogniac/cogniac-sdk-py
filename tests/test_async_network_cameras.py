"""
Async integration tests for AsyncCogniacNetworkCamera.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncNetworkCameraRead:

    @pytest.mark.asyncio
    async def test_get_all_cameras(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            cameras = await cogniac.AsyncCogniacNetworkCamera.get_all(cc)
            assert isinstance(cameras, list)
            if len(cameras) > 0:
                cam = cameras[0]
                assert cam.network_camera_id is not None

    @pytest.mark.asyncio
    async def test_get_camera(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            cameras = await cogniac.AsyncCogniacNetworkCamera.get_all(cc)
            if len(cameras) == 0:
                pytest.skip("No network cameras on test tenant")
            cam = cameras[0]
            fetched = await cogniac.AsyncCogniacNetworkCamera.get(cc, cam.network_camera_id)
            assert fetched.network_camera_id == cam.network_camera_id

    @pytest.mark.asyncio
    async def test_camera_immutable_raises(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            cameras = await cogniac.AsyncCogniacNetworkCamera.get_all(cc)
            if len(cameras) == 0:
                pytest.skip("No network cameras on test tenant")
            cam = cameras[0]
            with pytest.raises(AttributeError):
                cam.network_camera_id = "bad"

    @pytest.mark.asyncio
    async def test_camera_mutable_guard_raises(self):
        """Assigning to a mutable key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            cameras = await cogniac.AsyncCogniacNetworkCamera.get_all(cc)
            if len(cameras) == 0:
                pytest.skip("No network cameras on test tenant")
            cam = cameras[0]
            with pytest.raises(AttributeError, match="set"):
                cam.camera_name = "should-not-work"
