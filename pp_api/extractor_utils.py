"""
Extractor-related utility functions.
"""

from collections import defaultdict


def ppextract2matches(matches, tag=None, overlaps=True):
    """
    Convert PP extractor API results to 4-tuples specifying annotations,
    usable for edit operations on the input file.

    Overlapping tuples may optionally be removed, since it is tricky to
    apply overlapping offset-based annotations to a string.

    :param matches: An array of dicts as returned by pp_api.PoolParty.get_cpts_from_response().
    :param tag:     A fixed tag or tag pattern to annotate with.
                    If None, annotate with the prefLabel of each matched concept.
                    Tag patterns must use Python string.format variables, e.g.
                    tag='<START:Beverage uri="{uri}">' for OpenNLP tag + url.
                    FOR NOW, the closing tag is always <END>. (OpenNLP style)
    :param overlaps: Whether to include overlapping annotations in the results.
    :return:        A list of tuples (start, end, tag, content).
                    `start` and `end` are the character offsets. `content` is
                    the text content of this span, e.g. for error checking.

    Note: We consume the following data structure, returned by
        pp_api.PoolParty.get_cpts_from_response().

    [
        {
            "prefLabel": "Something",
            "uri": "https:...",
            ...
            "matchings": [
                {
                    "text": "something",
                    "frequency": n,
                    "positions": [
                        [
                            start1,
                            end1
                        ],
                        [   start2,
                            end2
                        ]
                    ]
                },
                {                        <-- start of matching 2 of the first concept
                    "text": "something_else",
                    ...

    """
    if tag is None:
        tag = "{prefLabel}"

    edits = []
    for cpt_dict in matches:

        # We can't annotate shadow concepts:
        if "matchings" not in cpt_dict:
            continue

        for match in cpt_dict["matchings"]:
            for start, end in match["positions"]:
                # Support tag patterns with substitution
                thistag = tag.format(**cpt_dict, start=start, end=end)
                edits.append((start, end, thistag, match["text"]))

    if not overlaps:
        edits = remove_overlaps(edits)

    return edits


def remove_overlaps(matches):
    """
    Return a subset of the matches, so that
    they are unique, ordered and non-overlapping.

    :param matches: a list of 4-tuples (start, end, tag, content)
    :return: the cleaned list
    """

    # Example that must be handled: Three annotations data, security, "data security"
    #
    # [ [data] [security] ]

    # Remove repetitions (e.g., ambiguous concept labels matching the same text)
    matches = set(matches)

    # Group edits by start position
    groups = defaultdict(list)
    for edt in matches:
        start, end, tag, match = edt
        groups[start].append(edt)

    # If several spans start at the same point, we keep the longest one
    # (If we still have two prefLabels with the same span, keeps the one that sorts last)
    for k, members in groups.items():
        if len(members) > 1:
            members[:] = sorted(members, key=lambda x: x[1])[-1:]

    matches = sorted(v[0] for v in groups.values())

    # Now look for concepts that start before the last one ended
    offset = -1
    clean = []
    for edt in matches:
        start, end, tag, match = edt
        if start <= offset:
            continue
        clean.append(edt)
        offset = end

    return clean
