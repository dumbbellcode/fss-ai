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

You will find all the changes in numbered bullet points.
Each array item should either be amendment for a subregulation or  a schedule or a form. Copy the amendment_text as it is from the text. 
amendment_text should contain full text: "For regulation ..., subregulation ..., ... should be substituted by"

Rules to disambiguate the target of each change:
1. Check for "Schedule" FIRST. If the text mentions "Schedule <N>", set the schedule field to N and leave
   regulation and subregulation EMPTY. Never treat the schedule number as a regulation number.
2. A schedule target may also mention "Annexure <M>" or "Form <X>" — capture those in the annexure or form
   fields. Dotted numbers under a schedule, e.g. "5.2.5", are paragraph/entry numbers inside the schedule,
   NOT subregulations; keep subregulation empty.
3. Only set regulation and subregulation when the text explicitly says "in regulation <X.Y>,
   in sub-regulation <X.Y.Z>".
4. Each change must populate exactly one target: (regulation + subregulation), schedule (+ annexure/form), or form.
"""