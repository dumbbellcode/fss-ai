PARSE_AMENDMENT = """
You are provided with a document that has a set of amendments across multiple sections and subsections, you have to extract the amedments in the JSON format:  

[
    date: '2025-01-12',
    changes: [
        {
            regulation: '1.1',
            subregulation: '1.1.1',
            amendment_text: '...',
        },
        {
            regulation: '1.1',
            subregulation: '1.1.2',
            amendment_text: '...',
        },
        {
            schedule: '1',
            annexure: '...',
            amendment_text: '...''
        },
        {
            form: '...',
            amendment_text: '...'
        }
    ]
]
The document will have a line like, 'New Delhi, 10 June 2026'.
You have to write that date in 'YYYY-MM-DD' format.

You will find all the changes in numbered bullet points.
Each array item should either be amendment for a subregulation or  a schedule or a form. Copy the amendment_text as it is from the text. 
amendment_text should contain full text: "For regulation ..., subregulation ..., ... should be substituted by"
"""