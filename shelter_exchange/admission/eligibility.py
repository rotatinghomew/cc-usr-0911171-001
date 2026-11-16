from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from ..contracts import ContractError, require_date, require_identifier, require_text

@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reasons: tuple[str, ...]
    approved_nights: int
    evidence_fingerprint: str

class EligibilityPolicy:
    def __init__(self, maximum_nights: int = 15, maximum_graduation_years: int = 10):
        self.maximum_nights = maximum_nights
        self.maximum_graduation_years = maximum_graduation_years

    def evaluate(self, application: Mapping[str, Any], prior_stays: Sequence[Mapping[str, Any]], today: dt.date) -> EligibilityDecision:
        applicant_id = require_identifier(application.get('applicant_id'), 'applicant_id')
        arrival = require_date(application.get('arrival'), 'arrival')
        departure = require_date(application.get('departure'), 'departure')
        reasons: list[str] = []
        requested = (departure - arrival).days
        if requested <= 0:
            reasons.append('departure_must_follow_arrival')
        if arrival < today:
            reasons.append('arrival_in_past')
        graduation_year = int(application.get('graduation_year', 0))
        if graduation_year < today.year - self.maximum_graduation_years or graduation_year > today.year + 1:
            reasons.append('graduation_year_outside_policy')
        invitation = str(application.get('interview_invitation', '')).strip()
        if len(invitation) < 8:
            reasons.append('interview_invitation_missing')
        diploma = str(application.get('diploma_reference', '')).strip()
        if len(diploma) < 6:
            reasons.append('diploma_reference_missing')
        consumed = 0
        for stay in prior_stays:
            if stay.get('applicant_id') != applicant_id or stay.get('status') not in {'completed','checked_in'}:
                continue
            consumed += (require_date(stay['departure'], 'departure') - require_date(stay['arrival'], 'arrival')).days
        remaining = max(0, self.maximum_nights - consumed)
        approved = min(max(0, requested), remaining)
        if approved < requested:
            reasons.append('free_night_limit_exceeded')
        if remaining == 0:
            reasons.append('free_night_limit_exhausted')
        evidence = '|'.join([applicant_id, str(graduation_year), invitation, diploma, str(consumed)])
        import hashlib
        return EligibilityDecision(not reasons, tuple(reasons), approved, hashlib.sha256(evidence.encode()).hexdigest())

    def validate_documents(self, documents: Sequence[Mapping[str, Any]], now: dt.datetime) -> tuple[str, ...]:
        problems: list[str] = []
        required = {'diploma','interview_invitation'}
        present = set()
        for document in documents:
            kind = require_text(document.get('kind'), 'kind', 2, 40)
            present.add(kind)
            expires = document.get('expires_at')
            if expires and dt.datetime.fromisoformat(str(expires).replace('Z','+00:00')) <= now:
                problems.append(f'expired:{kind}')
            if not str(document.get('checksum','')).isalnum():
                problems.append(f'invalid_checksum:{kind}')
        for kind in sorted(required - present):
            problems.append(f'missing:{kind}')
        return tuple(problems)
