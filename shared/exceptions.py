# -*- coding: utf-8 -*-
"""Custom exception hierarchy for the research text-analysis toolkit."""


class PipelineError(Exception):
    """Base exception for pipeline failures."""


class InputFileNotFoundError(PipelineError):
    """Input file does not exist."""


class CorruptInputError(PipelineError):
    """Input file exists but is malformed or unreadable."""


class MissingPreconditionError(PipelineError):
    """A previous pipeline step has not produced required output."""


class AnalysisError(PipelineError):
    """Non-fatal error during text analysis (e.g. a single TXT file could not be read)."""


class NetworkError(PipelineError):
    """External API or SPARQL endpoint unreachable."""


class CorpusSanityError(PipelineError):
    """Corpus failed the pre-analysis sanity check (e.g. metadata-marker pollution)."""
