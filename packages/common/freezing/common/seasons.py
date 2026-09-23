"""When the seasons turn.

The competition is bounded by them: it starts on the first of January and runs
to the end of winter, and the home page changes what it says as spring and
summer pass. A day either side is close enough for any of that, and the
arithmetic here lands within a minute of the observatory's own figures, so none
of it needs an ephemeris or a dependency.

From Meeus, *Astronomical Algorithms*, chapter 27.
"""

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from math import cos, radians

from freezing.common.times import parse_instant

MARCH_EQUINOX = "march"
JUNE_SOLSTICE = "june"
SEPTEMBER_EQUINOX = "september"
DECEMBER_SOLSTICE = "december"

#: Mean instants as Julian Ephemeris Days, for the years 1000 to 3000.
_MEAN = {
    MARCH_EQUINOX: (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
    JUNE_SOLSTICE: (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
    SEPTEMBER_EQUINOX: (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
    DECEMBER_SOLSTICE: (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032),
}

#: Periodic terms: an amplitude, and the phase and rate of an angle in degrees.
_TERMS = (
    (485, 324.96, 1934.136),
    (203, 337.23, 32964.467),
    (199, 342.08, 20.186),
    (182, 27.85, 445267.112),
    (156, 73.14, 45036.886),
    (136, 171.52, 22518.443),
    (77, 222.54, 65928.934),
    (74, 296.72, 3034.906),
    (70, 243.58, 9037.513),
    (58, 119.81, 33718.147),
    (52, 297.17, 150.678),
    (50, 21.02, 2281.226),
    (45, 247.54, 29929.562),
    (44, 325.15, 31555.956),
    (29, 60.93, 4443.417),
    (18, 155.12, 67555.328),
    (17, 288.79, 4562.452),
    (16, 198.04, 62894.029),
    (14, 199.76, 31436.921),
    (12, 95.39, 14577.848),
    (12, 287.11, 31931.756),
    (12, 320.81, 34777.259),
    (9, 227.73, 1222.114),
    (8, 15.45, 16859.074),
)

_J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)


def _dynamical_lead(year: int) -> timedelta:
    """How far ahead of the clock the dynamical time scale runs.

    Meeus works in dynamical time, which is a little over a minute ahead of
    what a clock says, because the Earth's rotation is not the metronome the
    calendar pretends it is. Left uncorrected the answers here came out about
    a hundred seconds late. The polynomial is Espenak and Meeus, for 2005-2050,
    and drifts outside that.
    """
    since_2000 = year - 2000
    return timedelta(seconds=62.92 + 0.32217 * since_2000 + 0.005589 * since_2000**2)


def season(year: int, which: str) -> datetime:
    """Return when a season turns, in UTC.

    :param year: The calendar year the turn falls in.
    :param which: One of the four constants in this module.
    """
    a, b, c, d, e = _MEAN[which]
    y = (year - 2000) / 1000
    julian = a + b * y + c * y**2 + d * y**3 + e * y**4

    centuries = (julian - 2451545.0) / 36525
    sun = radians(35999.373 * centuries - 2.47)
    spread = 1 + 0.0334 * cos(sun) + 0.0007 * cos(2 * sun)
    periodic = sum(
        amplitude * cos(radians(phase + rate * centuries))
        for amplitude, phase, rate in _TERMS
    )
    julian += 0.00001 * periodic / spread

    return _J2000 + timedelta(days=julian - 2451545.0) - _dynamical_lead(year)


def last_full_day_of_winter(year: int, where: tzinfo) -> date:
    """Return the last day that is winter from one midnight to the next.

    Spring arrives partway through the day of the March equinox, so the last
    day that is winter the whole way through is the day before it.
    """
    equinox = season(year, MARCH_EQUINOX).astimezone(where).date()
    return equinox - timedelta(days=1)


def end_of_winter(year: int, where: tzinfo) -> datetime:
    """Return the last instant of the last full day of winter."""
    return datetime.combine(
        last_full_day_of_winter(year, where), time(23, 59, 59), tzinfo=where
    )


def competition_end(configured: str | None, start: datetime, where: tzinfo) -> datetime:
    """Return when the competition closes, given what the configuration says.

    A season that ends on an ordinary date says so. One that does not ends
    with winter, which moves by a day or two from year to year and is not
    worth writing down again each time.
    """
    if configured:
        return parse_instant(configured)
    return end_of_winter(start.astimezone(where).year, where)
