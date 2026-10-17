PARSE_AMENDMENT = """
You are provided with a document that has a set of amendments across multiple sections and subsections, you have to extract the amedments in the JSON format:  

{
    "date": "2025-01-12",
    "changes": [
        {
            "regulation": "1.1",
            "subregulation": "1.1.1",
            "amendment_text": "..."
        },
        {
            "regulation": "1.1",
            "subregulation": "1.1.2",
            "amendment_text": "..."
        },
        {
            "schedule": "1",
            "annexure": "...",
            "amendment_text": "..."
        },
        {
            "form": "...",
            "amendment_text": "..."
        }
    ]
}
The document will have a line like, 'New Delhi, 10 June 2026'.
You have to write that date in 'YYYY-MM-DD' format.

You will find the changes in numbered clauses ("1.", "2."), lettered sub-items ("(A)", "(B)", "(a)", "(b)"),
and instructions such as "in regulation <X> ... shall be substituted", "after regulation <X> ... shall be
inserted", or "the following Schedule/Appendix shall be substituted". Treat an uppercase lettered sub-item
("(A)", "(B)") as a change even when its parent clause (for example "2. In the Food Safety and Standards
(...) regulations, 2011,-") is only a stem with no target of its own.
Each array item should either be amendment for a subregulation or  a schedule or a form. Copy the amendment_text as it is from the text. 
amendment_text must contain the complete amendment instruction verbatim, starting with its
original lead-in (for example, "in Schedule ..." or "in regulation ..."). Do not summarize,
rewrite, normalize, or remove the lead-in; copy the source wording through the substituted or
inserted text.

Rules to disambiguate the target of each change:
1. Check for "Schedule" FIRST. If the text mentions "Schedule <N>", set the schedule field to N and leave
   regulation and subregulation EMPTY. Never treat the schedule number as a regulation number.
2. A schedule target may also mention "Annexure <M>" or "Form <X>" — capture those in the annexure or form
   fields. Dotted numbers under a schedule, e.g. "5.2.5", are paragraph/entry numbers inside the schedule,
   NOT subregulations; keep subregulation empty.
3. Only set regulation and subregulation when the text explicitly says "in regulation <X.Y>,
   in sub-regulation <X.Y.Z>".
4. Each change must populate exactly one target: (regulation + subregulation), schedule (+ annexure/form), or form.
5. Every change object must include all six fields: regulation, subregulation, schedule, annexure, form, and amendment_text.
   Use null for target fields that do not apply; do not omit any field.
6. Whole-section insertion/substitution: when a clause inserts or substitutes a whole new section
   (e.g. "after regulation 3.3 ... the following shall be inserted, namely:-" followed by a new regulation
   numbered "3.4 ...") or a whole new Schedule/Appendix, add one change for it. Set regulation to the new
   section number (e.g. "3.4") when it is clearly stated, or annexure/schedule to the new appendix/schedule
   name (e.g. "Appendix C"); if the new target cannot be determined, leave the target fields null. Begin
   amendment_text with the lead-in instruction sentence and include the new heading.
7. Only when the inserted body is too large to reproduce within the output limit (for example a very long
   quoted table or appendix), it is acceptable to keep the lead-in instruction sentence and the new heading
   and stop early; do not summarize, invent, or renumber the omitted rows. Never return an empty "changes"
   list when the document contains at least one insert or substitute instruction. Do not create a change for
   "1. Short title and commencement".
8. Never abbreviate with an ellipsis. Do not write "..." or the "…" character anywhere in amendment_text. If
   a body cannot be copied in full, end the text cleanly at a complete heading or clause boundary instead of
   inserting "...". An amendment_text that contains "..." is treated as a failed extraction.
9. Do not turn surrounding boilerplate into changes. Ignore the opening preamble ("Now, therefore, in
   exercise of the powers conferred ... the Food Safety and Standards Authority of India hereby makes the
   following regulations ...") and ignore the closing note that lists earlier amending notifications
   ("Note. - The principal regulations were published ... vide notification numbers: - ... (I) F. No. ...;
   (II) F. No. ..."). Those sentences are not amendments and must not become change objects.

"""
