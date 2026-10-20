"""Profile preview sampling must stay inside the measured interval."""

import math

from PySide6.QtWidgets import QApplication
import pytest

from wraplab.domain import Placement
from wraplab.geometry.surfaces import MeasuredProfile
from wraplab.ui.views import ProfileCanvas


@pytest.fixture
def profile():
    # Synthetic diameters; 8.5 inches exposes endpoint multiplication round-off.
    return MeasuredProfile([(0, 60), (40, 100), (8.5 * 25.4, 160)])


@pytest.mark.parametrize("region", ["no-artwork", "full-height", "centered-band"])
def test_inch_profile_outline_and_highlight_use_in_range_endpoints(profile, region):
    app = QApplication.instance() or QApplication([])
    view = ProfileCanvas()
    placement = Placement(height=profile.height, z=0)
    if region == "centered-band":
        placement.height = 2 * 25.4
        placement.z = 3.25 * 25.4
    try:
        view.set_surface(profile, profile.points, placement, show_artwork=region != "no-artwork")
        assert len(view.scene().items()) == (7 if region == "no-artwork" else 8)
        assert not view.scene().itemsBoundingRect().isEmpty()
    finally:
        view.close()
        app.processEvents()


@pytest.mark.parametrize("outside", ["above-top", "below-bottom"])
def test_profile_still_rejects_even_one_ulp_outside_measured_height(profile, outside):
    z = math.nextafter(0, -math.inf) if outside == "above-top" else math.nextafter(profile.height, math.inf)
    with pytest.raises(ValueError, match="outside the measured object height"):
        profile.radius(z)
