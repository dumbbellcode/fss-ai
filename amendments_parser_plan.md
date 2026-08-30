Similar to regulation parser we need a parser that extracts 
amendment texts out of markdown files,
we need to split amendments at sub-regulation level 

1. First look for 2 line text like this :

"
NOTIFICATION
New Delhi, the 10th March, 2026
"

2. Post that, start looking for lines that start with numbered points i.e 1., 2., 3. .... 
3. A point N does not end until the next point N+1 starts 

[
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

Each array item should either be amendment for a subregulation or 
a schedule or a form. Copy the amendment_text as it is from the text.

file: assets/regulations/01_Licensing_and_Registration_of_Food_Businesses/amendments/01_273797.cleaned.md

You are provided with a document that has a set of amendments across multiple sections and subsections, you have to extract the amedments in the JSON format:  

[
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
You will find all the changes in numbered bullet points.
Each array item should either be amendment for a subregulation or  a schedule or a form. Copy the amendment_text as it is from the text.



===

in cleanup_markdown, we need to segrategate cleanup_regulation and cleanup_amendment, because both have different patterns to be cleaned up:
 cleanup_regulation is already there.

for cleanup_amendment, cleanup like this:

1. Using pattern matching, search for lines like this:

"
NOTIFICATION

New Delhi, the 10th July, 2025
"

or 

"
NOTIFICATION
New Delhi, the 10th July, 2025
"

once matched, remove all the lines above "NOTIFICATION" line 

2. Remove all lines that match one of these patterns:

1. "N THE GAZETTE OF INDIA : EXTRAORDINARY [T]"
2. "[T] THE GAZETTE OF INDIA : EXTRAORDINARY [N]"
3. 
"
N

THE GAZETTE OF INDIA : EXTRAORDINARY

[T]
"
4. "
T

THE GAZETTE OF INDIA : EXTRAORDINARY

[N]
"
5. "THE GAZETTE OF INDIA : EXTRAORDINARY"
6. "[T] भारत का रािपत्र : असाधारण N"
7. "N भारत का रािपत्र : असाधारण [T]"
8. "
[T]

भारत का रािपत्र : असाधारण

N
"
9. "
N

भारत का रािपत्र : असाधारण

[T]
"
10. "भारत का रािपत्र : असाधारण"

