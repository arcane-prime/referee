import re
import unicodedata
from difflib import SequenceMatcher

from app.domain.csl import CSLItem
from app.domain.library import MatchCandidate, MatchScore, RawReference, SourceRecord

RESOLVED_THRESHOLD = 0.82
AMBIGUOUS_THRESHOLD = 0.55
MIN_MARGIN_OVER_RUNNER_UP = 0.04

TITLE_WEIGHT = 0.60
AUTHOR_WEIGHT = 0.25
YEAR_WEIGHT = 0.15

SAME_WORK_TITLE_THRESHOLD = 0.93
SAME_WORK_MAX_YEAR_GAP = 1
PREPRINT_DOI_PREFIXES = ("10.48550",)

YEAR_SCORES = {0: 1.0, 1: 0.85, 2: 0.5}

PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
WHITESPACE = re.compile(r"\s+")


def normalise_text(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    without_punctuation = PUNCTUATION.sub(" ", stripped.lower())
    return WHITESPACE.sub(" ", without_punctuation).strip()


def surname_of(name: str | None) -> str:
    normalised = normalise_text(name)
    if not normalised:
        return ""
    return normalised.rsplit(" ", 1)[-1]


def title_similarity(left: str | None, right: str | None) -> float:
    a = normalise_text(left)
    b = normalise_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    tokens_a = set(a.split())
    tokens_b = set(b.split())
    overlap = len(tokens_a & tokens_b)
    jaccard = overlap / len(tokens_a | tokens_b) if tokens_a | tokens_b else 0.0
    containment = overlap / min(len(tokens_a), len(tokens_b))
    sequence = SequenceMatcher(None, a, b).ratio()

    return round(max(sequence, (jaccard + containment) / 2), 4)


def author_similarity(left: CSLItem | None, right: CSLItem | None) -> float | None:
    ours = {surname_of(name.surname) for name in (left.author if left else [])}
    theirs = {surname_of(name.surname) for name in (right.author if right else [])}
    ours.discard("")
    theirs.discard("")

    if not ours or not theirs:
        return None
    return round(len(ours & theirs) / len(ours), 4)


def year_similarity(left: CSLItem | None, right: CSLItem | None) -> float | None:
    ours = left.year if left else None
    theirs = right.year if right else None
    if ours is None or theirs is None:
        return None
    return YEAR_SCORES.get(abs(ours - theirs), 0.0)


def describe_the_same_work(left: SourceRecord, right: SourceRecord) -> bool:
    left_doi = left.external_ids.doi
    right_doi = right.external_ids.doi
    if left_doi and right_doi and left_doi == right_doi:
        return True

    if title_similarity(left.csl.title, right.csl.title) < SAME_WORK_TITLE_THRESHOLD:
        return False

    left_year = left.csl.year
    right_year = right.csl.year
    if left_year is None or right_year is None:
        return True
    return abs(left_year - right_year) <= SAME_WORK_MAX_YEAR_GAP


def is_preprint_doi(doi: str | None) -> bool:
    return bool(doi) and doi.startswith(PREPRINT_DOI_PREFIXES)


def better_record_of(left: MatchCandidate, right: MatchCandidate) -> MatchCandidate:
    def rank(candidate: MatchCandidate) -> tuple:
        doi = candidate.record.external_ids.doi
        return (
            bool(candidate.record.abstract),
            not is_preprint_doi(doi),
            bool(doi),
            candidate.score.total,
        )

    return right if rank(right) > rank(left) else left


class MatcherProvider:
    def score(self, reference: RawReference, record: SourceRecord) -> MatchScore:
        parsed = reference.parsed

        title = title_similarity(
            parsed.title if parsed else reference.raw,
            record.csl.title,
        )
        authors = author_similarity(parsed, record.csl)
        year = year_similarity(parsed, record.csl)

        weighted = TITLE_WEIGHT * title
        total_weight = TITLE_WEIGHT

        if authors is not None:
            weighted += AUTHOR_WEIGHT * authors
            total_weight += AUTHOR_WEIGHT
        if year is not None:
            weighted += YEAR_WEIGHT * year
            total_weight += YEAR_WEIGHT

        return MatchScore(
            total=round(weighted / total_weight, 4),
            title=title,
            authors=authors,
            year=year,
        )

    def rank(
        self,
        reference: RawReference,
        records: list[SourceRecord],
    ) -> list[MatchCandidate]:
        candidates = [
            MatchCandidate(record=record, score=self.score(reference, record))
            for record in records
        ]
        ordered = sorted(
            candidates, key=lambda candidate: candidate.score.total, reverse=True
        )
        return self.collapse_duplicates(ordered)

    def collapse_duplicates(self, candidates: list[MatchCandidate]) -> list[MatchCandidate]:
        collapsed: list[MatchCandidate] = []

        for candidate in candidates:
            for index, kept in enumerate(collapsed):
                if describe_the_same_work(kept.record, candidate.record):
                    collapsed[index] = better_record_of(kept, candidate)
                    break
            else:
                collapsed.append(candidate)

        return collapsed

    def decide(
        self,
        candidates: list[MatchCandidate],
    ) -> tuple[str, MatchCandidate | None, str]:
        if not candidates:
            return "unresolved", None, "No candidate records were returned."

        best = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None

        if best.score.total < AMBIGUOUS_THRESHOLD:
            return (
                "unresolved",
                None,
                f"Best candidate scored {best.score.total:.2f}, below the "
                f"{AMBIGUOUS_THRESHOLD:.2f} threshold.",
            )

        if best.score.total < RESOLVED_THRESHOLD:
            return (
                "ambiguous",
                best,
                f"Best candidate scored {best.score.total:.2f}, short of the "
                f"{RESOLVED_THRESHOLD:.2f} needed to accept it.",
            )

        if runner_up is not None:
            margin = best.score.total - runner_up.score.total
            if margin < MIN_MARGIN_OVER_RUNNER_UP:
                return (
                    "ambiguous",
                    best,
                    f"Top two candidates scored {best.score.total:.2f} and "
                    f"{runner_up.score.total:.2f}; too close to choose between them.",
                )

        return "resolved", best, "Matched with high confidence."


# Notes
#
# This is where stage 2 lives or dies, and it is deliberately pure: it takes a
# reference and a list of records and returns numbers. No HTTP, no disk. That
# is what lets it be tested against hand-written records in milliseconds, and
# what lets the thresholds be tuned against real data without waiting on an
# API.
#
# Every reference in the sample paper had to be matched by title, because not
# one of its forty entries carried a DOI. Preprint-era bibliographies are like
# that. So title similarity is the dominant signal by necessity, and authors
# and year exist to stop it being the only one.
#
# Title similarity combines two views because each fails differently. A
# sequence ratio handles small edits and typos but punishes reordered words; a
# token measure handles reordering but ignores order entirely and so rates
# "attention is all you need" against "you need all attention" as identical.
# Taking the better of the two lets a genuine match win on whichever view suits
# it, and neither view alone rescues a bad candidate.
#
# Author similarity is containment rather than a symmetric overlap: what
# fraction of *our* authors appear in theirs. Bibliographies truncate with "et
# al", so our list is routinely a prefix of the real one. Penalising a record
# for listing the authors the printed reference omitted would punish the
# correct answer.
#
# A one-year gap scores 0.85 rather than being treated as a mismatch. The
# single most common shape in this literature is an arXiv preprint in one year
# and the conference version the next. They are the same work, and a scorer
# that insists on an exact year rejects correct matches constantly.
#
# Missing signals are skipped and the weights renormalised over what remains,
# rather than scored as zero. A reference with no parsed authors is not
# evidence of a bad match; it is an absence of evidence, and scoring it as a
# failure would push every degraded reference to unresolved regardless of how
# good the title match was.
#
# When a reference has no parsed title at all, the raw printed string is scored
# against the candidate title instead. It is noisier, but it is exactly the
# case where GROBID failed and the reference most needs rescuing, and the raw
# string is always populated for this reason.
#
# The margin rule is the part that is easy to leave out and matters most.
# A high score alone is not confidence: searching "Long short-term memory"
# returns the 1997 Hochreiter paper and a 2012 book chapter with the identical
# title. Both score near the top on title alone. If the top two are within a
# few points of each other, the honest answer is ambiguous, and the candidates
# are handed to the user rather than a coin flip being recorded as fact.
#
# Duplicates are collapsed before the margin rule runs, and skipping that step
# breaks the margin rule outright. Live output made this obvious: searching for
# the RNN encoder-decoder paper returns the EMNLP version and the arXiv
# preprint as two records, identical in title, year and authors, scoring 1.00
# each. They are one work indexed twice, not two candidates competing, and the
# margin rule read the tie as uncertainty and refused a perfect match.
#
# Preprint plus published version is the most common shape in this literature,
# so without this the matcher would mark a large share of its best matches
# ambiguous and push them at the user for a decision that is not theirs to
# make.
#
# Two records count as the same work if they share a DOI, or if their titles
# are near identical and their years are within one. That last tolerance is the
# same preprint-versus-conference gap the year scoring already allows for.
#
# When collapsing, the surviving record is the more useful one rather than the
# higher scoring one, since by construction the scores are near identical: an
# abstract first, because stage 3 cannot work without it, then the published
# DOI over the arXiv one, because that is what a reader should be cited to.
#
# The thresholds are starting points chosen to be tuned against real output,
# not derived from anything. They are constants at the top of the file so that
# tuning is a one-line change with tests to check it against.
