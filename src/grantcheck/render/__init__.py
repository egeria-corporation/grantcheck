"""Renderers. A renderer turns a :class:`~grantcheck.models.Report` into text.

Renderers never compute anything. If a renderer needs to decide what a fact means, the
decision belongs in a check instead — otherwise the terminal output, the Markdown, the JSON,
and the hosted site can drift apart, and the whole point is that they cannot.
"""
