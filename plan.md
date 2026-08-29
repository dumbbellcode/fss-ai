Given a markdown document, we need to detect the start of these
document items:
1. Chapter
2. Section 
3. Subsection
4. Schedule
5. Annexure
6. Form

How to detect document items: 
1. Chapter: Line only contains text <CHAPTER X> or <CHAPTER-X> where X is the chapter number. 
2. Section: Line starts with text "N.M " or "N.M: " or "N. M ", where N and M are both numbers. N is chapter number.
3. Subsection: Line starts with "N.M.P", where N,M,P are numbers
4. Schedule: Line only contains text <SCHEDULE-X> or <SCHEDULE X> where X is schedule number in integer or roman numberal
5. Annexure: Line only contains text <Annexure-X> or <Annexure X>
6. Form: Line only contains text <FORM-X> or <FORM X>. "FORM-X" or X
might be enclosed in single quotes 

We need to write a regulation parser that accepts a md file and outputs a JSON like this:
{
chapters: [
    {
        no: 1
        title: ...
        sections: [
            {
                no: 1.1
                text: <..>
                sub_sections: [
                    {
                        no: 1.1.1
                        text: <...> 
                    },
                    {
                        no: 1.1.2
                        text: <...>
                    }
                ]
            }
        ],
        forms:  [
            {
                name: 'Form A',
                text: <..>
            }
        ]
    }
],
schedules: {
    name: 'Schedule 1',
    forms: [
        {
            name: 'Form B',
            text: <..>
        }
    ]
    annexures: [
        name: 'Annexure-2',
        text": <..>
    ]
}
}

Please create corresponding DTOs also using pydantic. 

Parse the markdown file like this:

1. If a document item is detected, all the text starting from that line
will be under that item until another document item is detected
2. Keep track of the current chapter, section or schedule at any point
3. A section will fall under current chapter
4. A subsection will fall under current section
5. If a schedule is detected, set chapter, section to null as schedules lie outside chapters.
6. If a form is detected, put it under chapter if chapter is going on,
put it under schedule if schedule is going on.

Please write the regulation_parser.py, with clean code,
under pre_processing 
