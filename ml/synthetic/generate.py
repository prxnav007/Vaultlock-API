"""Generate a synthetic payment history into the canonical schema.

The generator is the most load-bearing piece of the ML half, because an
unrealistically easy world makes a meaningless model look excellent. So
behaviour is produced from hidden merchant characteristics -- a baseline rate,
an amount distribution, a failure propensity, a disengagement trajectory --
and never by writing the feature values we hope to see. Those latent variables
are saved for debugging and are forbidden as model inputs: the model has to
infer risk from observable payment behaviour, which is the whole claim.

Difficulty is deliberate. Churners decline at different speeds, some stop
abruptly, some keep paying the occasional stray amount, roughly half see no
rise in failures at all, and healthy merchants have temporary dips and
elevated-failure spells that look the same from inside a 90-day window.

Usage:
    python -m ml.synthetic.generate --truncate
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime, timedelta

import numpy as np

from ml import config

INDUSTRIES = (
    "retail",
    "food_delivery",
    "travel",
    "education",
    "healthcare",
    "saas",
    "logistics",
    "entertainment",
)
FAILURE_CODES = (
    "insufficient_funds",
    "card_declined",
    "network_timeout",
    "issuer_unavailable",
    "do_not_honor",
)
CURRENCY = "INR"

CHURN_MODES = ("gradual", "abrupt", "straggler")
CHURN_MODE_WEIGHTS = (0.50, 0.30, 0.20)


@dataclass(frozen=True, slots=True)
class Episode:
    """A temporary behavioural spell: a quiet patch, or a bad-luck patch."""

    start_day: int
    end_day: int
    multiplier: float


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    n_merchants: int = 2_000
    months: int = 24
    end_date: date | None = None
    seed: int = config.RANDOM_SEED
    churn_fraction: float = 0.15
    # Merchant size follows a heavy tail: a few high-volume accounts and many
    # sporadic ones that invoice monthly or seasonally. The spread matters more
    # than the median -- if every active merchant pays weekly, then any silence
    # is already proof of departure and recency alone solves the problem.
    rate_log_mu: float = -1.20
    rate_log_sigma: float = 1.50
    amount_log_mu: float = 8.60
    amount_log_sigma: float = 1.10
    failure_beta_a: float = 2.0
    failure_beta_b: float = 48.0
    activity_cv: float = 0.60

    @property
    def resolved_end(self) -> date:
        return self.end_date or datetime.now(UTC).date()

    @property
    def start(self) -> date:
        return self.resolved_end - timedelta(days=round(self.months * 30.4375))

    @property
    def n_days(self) -> int:
        return (self.resolved_end - self.start).days


@dataclass(frozen=True, slots=True)
class MerchantProfile:
    """Hidden merchant characteristics. Never a model feature.

    Everything here is generator-internal truth. Feeding any of it to XGBoost
    would be asking the model to read the answer key instead of inferring risk
    from the ledger, so a test asserts no training or serving module can even
    reach this module.
    """

    merchant_id: uuid.UUID
    industry: str
    join_day: int
    base_rate_per_day: float
    amount_log_mu: float
    amount_log_sigma: float
    amount_trend: float
    base_failure_p: float
    activity_cv: float
    weekday_weights: np.ndarray
    seasonal_amp: float
    seasonal_phase: float
    is_churner: bool
    churn_start_day: int | None
    churn_mode: str | None
    churn_halflife_days: float | None
    departure_day: int | None
    friction_rises_before_churn: bool
    dips: tuple[Episode, ...] = field(default=())
    friction_spells: tuple[Episode, ...] = field(default=())


def seeded_uuids(rng: np.random.Generator, n: int) -> list[uuid.UUID]:
    """Version-4 UUIDs drawn from the seeded stream.

    Primary keys are assigned client-side rather than by the table's
    `gen_random_uuid()` default, because reproducibility has to cover the ids
    too: the same seed must rebuild the same dataset row for row, and
    `uuid.uuid4()` or a server default would both draw from entropy this
    generator does not control.
    """
    return [uuid.UUID(bytes=rng.bytes(16), version=4) for _ in range(n)]


def merchant_rng(seed: int, index: int) -> np.random.Generator:
    """An independent stream per merchant.

    Keyed on the merchant's index rather than drawn in sequence, so merchant
    i's history does not change when `--n-merchants` changes or when the loop
    order changes.
    """
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(index,)))


def sample_profile(cfg: GeneratorConfig, index: int) -> MerchantProfile:
    """Draw one merchant's latent characteristics.

    Every draw comes from that merchant's own stream, keyed on its index, so a
    profile depends on the seed and the index alone. Running with 200
    merchants therefore produces exactly the first 200 of a 2,000-merchant
    run, which makes iterating on a small dataset meaningful rather than a
    different world each time.
    """
    rng = merchant_rng(cfg.seed, index)
    n_days = cfg.n_days

    # Half the platform is present from the start; the rest trickles in over
    # the first months, so tenure varies and a young merchant is never
    # mistaken for a lapsed one.
    latest_join = max(31, min(n_days - 180, 450))
    join_day = int(
        rng.integers(0, 30) if rng.random() < 0.5 else rng.integers(30, latest_join)
    )

    churner = bool(rng.random() < cfg.churn_fraction)
    mode = str(rng.choice(CHURN_MODES, p=CHURN_MODE_WEIGHTS))
    # Disengagement can begin any time from 120 days in to shortly before the
    # window closes, so the positive class spreads across the timeline instead
    # of bunching at one date.
    halflife = float(rng.uniform(20.0, 90.0))
    friction_first = bool(rng.random() < 0.55) and churner
    straggler_tail = int(rng.integers(120, 240))

    # The departure date is sampled first and the decline is worked backwards
    # from it, rather than the reverse. A merchant only yields a positive row
    # in the 60 days following its final attempt, so a departure sampled too
    # near the end of history lands outside the observable window and teaches
    # nothing. Bounding the departure directly is what keeps the positive class
    # usable; deriving it from churn_start left it uncontrolled.
    departure_day: int | None = None
    churn_day: int | None = None
    if churner:
        decline = {
            "abrupt": 0,
            "gradual": int(round(3 * halflife)),
            "straggler": straggler_tail,
        }[mode]
        # Spread across the whole range a label can still be observed in. The
        # last usable snapshot is 60 days before history ends, and a departure
        # on day L produces positives from L onwards, so bounding departures
        # much earlier than that leaves the final months with no positives at
        # all and makes the test split a different problem from training.
        departure_day = max(
            join_day + 150, int(rng.integers(150, max(151, n_days - 70)))
        )
        # At least 90 days of healthy history before the decline begins.
        churn_day = max(join_day + 90, departure_day - decline)

    weights = rng.uniform(0.6, 1.4, size=7)
    weights[5:] *= 0.75  # a mild, universal weekend lull
    weights /= weights.mean()

    # Healthy merchants dip and recover; that is what stops "quiet lately"
    # from being a perfect churn rule.
    dip_limit = churn_day if churner else n_days
    return MerchantProfile(
        merchant_id=seeded_uuids(rng, 1)[0],
        # Sampled independently of every behaviour knob, so industry can never
        # become a shortcut to the label.
        industry=str(rng.choice(INDUSTRIES)),
        join_day=join_day,
        base_rate_per_day=float(
            np.exp(rng.normal(cfg.rate_log_mu, cfg.rate_log_sigma))
        ),
        amount_log_mu=float(rng.normal(cfg.amount_log_mu, 0.45)),
        amount_log_sigma=float(rng.uniform(0.7, 1.4)),
        # Drawn independently of is_churner, so plenty of churners keep their
        # payment values steady or even rising to the end.
        amount_trend=float(rng.normal(0.0, 0.00035)),
        base_failure_p=float(rng.beta(cfg.failure_beta_a, cfg.failure_beta_b)),
        activity_cv=float(rng.uniform(0.4, 1.0) * (cfg.activity_cv / 0.6)),
        weekday_weights=weights,
        seasonal_amp=float(rng.uniform(0.0, 0.25)),
        seasonal_phase=float(rng.uniform(0.0, 2 * np.pi)),
        is_churner=churner,
        churn_start_day=churn_day,
        churn_mode=mode if churner else None,
        churn_halflife_days=halflife if churner else None,
        departure_day=departure_day,
        friction_rises_before_churn=friction_first,
        # Healthy merchants go quiet for weeks at a time and come back. These
        # recoveries are the main confounder standing between "quiet lately"
        # and "gone", and without them the label is trivially observable.
        dips=sample_episodes(rng, join_day, dip_limit, (0, 3), (21, 84), (0.05, 0.40)),
        friction_spells=sample_episodes(
            rng, join_day, dip_limit, (0, 1), (14, 42), (2.0, 4.0)
        ),
    )


def sample_profiles(cfg: GeneratorConfig) -> list[MerchantProfile]:
    """Draw the latent world. Deterministic in `cfg.seed`."""
    return [sample_profile(cfg, i) for i in range(cfg.n_merchants)]


def sample_episodes(
    rng: np.random.Generator,
    first_day: int,
    last_day: int,
    count_range: tuple[int, int],
    length_range: tuple[int, int],
    multiplier_range: tuple[float, float],
) -> tuple[Episode, ...]:
    span = last_day - first_day
    if span <= length_range[1] + 1:
        return ()
    n = int(rng.integers(count_range[0], count_range[1] + 1))
    episodes = []
    for _ in range(n):
        length = int(rng.integers(*length_range))
        start = int(rng.integers(first_day, last_day - length))
        episodes.append(
            Episode(start, start + length, float(rng.uniform(*multiplier_range)))
        )
    return tuple(episodes)


def episode_multiplier(
    episodes: tuple[Episode, ...], days: np.ndarray, baseline: float = 1.0
) -> np.ndarray:
    out = np.full(days.size, baseline, dtype=np.float64)
    for spell in episodes:
        inside = (days >= spell.start_day) & (days < spell.end_day)
        out[inside] *= spell.multiplier
    return out


def churn_multiplier(profile: MerchantProfile, days: np.ndarray) -> np.ndarray:
    """How a disengaging merchant's activity rate falls away over time.

    Each mode ends in an actual departure, after which the rate is exactly
    zero. An asymptotic decay would be the more elegant curve but the wrong
    model of the world: a merchant who has left stops paying, rather than
    paying ever more rarely forever.
    """
    out = np.ones(days.size, dtype=np.float64)
    if not profile.is_churner or profile.churn_start_day is None:
        return out
    elapsed = days - profile.churn_start_day
    after = elapsed >= 0
    if profile.churn_mode == "gradual":
        out[after] = np.exp(-elapsed[after] / profile.churn_halflife_days)
    elif profile.churn_mode == "abrupt":
        out[after] = 0.0
    else:
        # A straggler keeps making the rare attempt for months before going
        # quiet, which is what keeps the label genuinely noisy instead of a
        # clean step function.
        out[after] = 0.03
    if profile.departure_day is not None:
        out[days >= profile.departure_day] = 0.0
    return out


def daily_rates(profile: MerchantProfile, days: np.ndarray) -> np.ndarray:
    """Expected attempts per day: habit, seasonality, decay and bad patches."""
    weekday = profile.weekday_weights[days % 7]
    seasonal = 1.0 + profile.seasonal_amp * np.sin(
        2 * np.pi * days / 365.0 + profile.seasonal_phase
    )
    return (
        profile.base_rate_per_day
        * weekday
        * seasonal
        * churn_multiplier(profile, days)
        * episode_multiplier(profile.dips, days)
    )


def daily_failure_probability(
    profile: MerchantProfile, days: np.ndarray
) -> np.ndarray:
    """Per-day failure probability, with friction that is not a churn giveaway.

    Friction rises before churn for only about half of churners, and rises the
    same way during healthy merchants' bad spells, so reliability carries real
    signal without revealing the label.
    """
    multiplier = episode_multiplier(profile.friction_spells, days)
    if profile.friction_rises_before_churn and profile.departure_day is not None:
        # Friction builds over the final weeks of activity, anchored to the
        # departure rather than to the start of the decline. Anchoring it to
        # churn_start put the signal up to 270 days before the merchant
        # actually left, where no 30-day feature window can see it -- the
        # world contained the information but the model could not observe it.
        ramp_start = profile.departure_day - 45
        ramp = np.clip((days - ramp_start) / 45.0, 0.0, 1.0)
        multiplier = multiplier * (1.0 + 2.5 * ramp)
    return np.clip(profile.base_failure_p * multiplier, 0.0, 0.60)


@dataclass(slots=True)
class PaymentBatch:
    payment_id: list[uuid.UUID]
    created_at: np.ndarray
    amount_minor: np.ndarray
    status: np.ndarray
    failure_code: np.ndarray

    def __len__(self) -> int:
        return int(self.created_at.size)


def simulate_merchant(
    profile: MerchantProfile, cfg: GeneratorConfig, start: datetime
) -> PaymentBatch:
    """One merchant's payment attempts over the whole window."""
    rng = merchant_rng(cfg.seed + 1, hash_index(profile))
    days = np.arange(profile.join_day, cfg.n_days, dtype=np.int64)
    if days.size == 0:
        return empty_batch()

    rates = daily_rates(profile, days)
    # Gamma-mixed Poisson, i.e. negative binomial: real merchants are burstier
    # than a plain Poisson process allows.
    shape = 1.0 / profile.activity_cv**2
    overdispersion = rng.gamma(shape=shape, scale=1.0 / shape, size=days.size)
    counts = rng.poisson(np.clip(rates * overdispersion, 0.0, 50.0))
    total = int(counts.sum())
    if total == 0:
        return empty_batch()

    day_of = np.repeat(days, counts)
    # Business hours with a thin overnight tail.
    hour = np.where(
        rng.random(total) < 0.07,
        rng.uniform(0.0, 8.0, size=total),
        rng.uniform(8.0, 22.0, size=total),
    )
    offsets = day_of.astype(np.float64) * 86_400.0 + hour * 3_600.0
    offsets = np.sort(offsets)

    log_amount = rng.normal(
        profile.amount_log_mu + profile.amount_trend * day_of,
        profile.amount_log_sigma,
    )
    amounts = np.clip(np.exp(log_amount).round(), 1.0, None).astype(np.int64)

    failure_p = daily_failure_probability(profile, day_of)
    failed = rng.random(total) < failure_p
    status = np.where(failed, "FAILED", "SUCCESS")
    codes = np.where(failed, rng.choice(FAILURE_CODES, size=total), None)

    created = np.datetime64(start.replace(tzinfo=None), "s") + offsets.astype(
        "timedelta64[s]"
    )
    return PaymentBatch(
        payment_id=seeded_uuids(rng, total),
        created_at=created.astype("datetime64[us]"),
        amount_minor=amounts,
        status=status,
        failure_code=codes,
    )


def hash_index(profile: MerchantProfile) -> int:
    """A stable per-merchant simulation key derived from its own id."""
    return int.from_bytes(profile.merchant_id.bytes[:4], "big")


def empty_batch() -> PaymentBatch:
    return PaymentBatch(
        payment_id=[],
        created_at=np.empty(0, dtype="datetime64[us]"),
        amount_minor=np.empty(0, dtype=np.int64),
        status=np.empty(0, dtype=object),
        failure_code=np.empty(0, dtype=object),
    )


def write_profiles_parquet(
    profiles: list[MerchantProfile], cfg: GeneratorConfig
) -> None:
    """Save the latent truth for debugging. Diagnostics only, never a feature."""
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                k: v
                for k, v in asdict(replace(p, weekday_weights=np.empty(0))).items()
                if k not in {"weekday_weights", "dips", "friction_spells"}
            }
            | {"n_dips": len(p.dips), "n_friction_spells": len(p.friction_spells)}
            for p in profiles
        ]
    )
    frame["merchant_id"] = frame["merchant_id"].astype(str)
    config.ensure_dirs()
    frame.to_parquet(config.PROFILES_PARQUET, index=False)


def summarize(
    cfg: GeneratorConfig,
    profiles: list[MerchantProfile],
    batches: list[PaymentBatch],
) -> dict:
    total = sum(len(b) for b in batches)
    failed = sum(int((b.status == "FAILED").sum()) for b in batches)
    churners = sum(1 for p in profiles if p.is_churner)
    return {
        "seed": cfg.seed,
        "n_merchants": len(profiles),
        "history_start": cfg.start.isoformat(),
        "history_end": cfg.resolved_end.isoformat(),
        "months": cfg.months,
        "merchant_churn_count": churners,
        "merchant_churn_rate": churners / len(profiles),
        "payments_total": total,
        "failures_total": failed,
        "failure_rate_overall": failed / total if total else 0.0,
        "snapshot_cadence_days": config.SNAPSHOT_CADENCE_DAYS,
        "observation_window_days": config.OBSERVATION_WINDOW_DAYS,
        "prediction_horizon_days": config.PREDICTION_HORIZON_DAYS,
        "churn_mode_counts": {
            mode: sum(1 for p in profiles if p.churn_mode == mode)
            for mode in CHURN_MODES
        },
        "config": {
            k: v for k, v in asdict(cfg).items() if k != "end_date"
        },
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merchants", type=int, default=2_000)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument(
        "--end-date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="last day of history; defaults to today and is recorded in the summary",
    )
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--churn-fraction", type=float, default=0.15)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument(
        "--no-db", action="store_true", help="simulate and summarize without loading"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = GeneratorConfig(
        n_merchants=args.merchants,
        months=args.months,
        end_date=args.end_date,
        seed=args.seed,
        churn_fraction=args.churn_fraction,
    )
    start = datetime.combine(cfg.start, datetime.min.time(), tzinfo=UTC)
    print(
        f"generating {cfg.n_merchants:,} merchants over {cfg.n_days} days "
        f"({cfg.start} to {cfg.resolved_end}), seed {cfg.seed}",
        file=sys.stderr,
    )

    profiles = sample_profiles(cfg)
    batches = [simulate_merchant(p, cfg, start) for p in profiles]
    summary = summarize(cfg, profiles, batches)
    print(f"simulated {summary['payments_total']:,} payments", file=sys.stderr)

    if not args.no_db:
        # Imported here, not at module scope: generation itself must stay
        # importable -- and testable -- without a database.
        from ml.synthetic import load

        if args.truncate:
            load.truncate_tables()
        load.write_merchants(profiles, start)
        load.copy_payments(profiles, batches)
        load.analyze()

    write_profiles_parquet(profiles, cfg)
    config.ensure_dirs()
    config.GENERATION_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
