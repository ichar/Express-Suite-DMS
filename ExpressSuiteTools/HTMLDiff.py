"""
HTML diff generator.

Based on HTML Diff by Aaron Swartz <me@aaronsw.com>.
See http://www.aaronsw.com/2002/diff

$Id: HTMLDiff.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from difflib import SequenceMatcher

# Split text into sequence of words, tags, and whitespace.
# matches HTML tag or whitespace character
# (with optional trailing whitespace which is thrown away)
_sep_rec = re.compile( r'(<[^>]*>|\s)\s*' )

# Ignore non-significant substrings in SequenceMatcher.
# matches sequential whitespace or empty string
_spc_rec = re.compile( r'\A\s*\Z' )

# Skip deleted HTML tags.
# matches a single HTML tag
_tag_rec = re.compile( r'\A<[^>]*>\Z' )

_delete_tag = '<span class="diff_deleted">%s</span>'
_insert_tag = '<span class="diff_inserted">%s</span>'


def HTMLDiff( a, b, delete_tag=_delete_tag, insert_tag=_insert_tag ):
    """
        Takes in two strings and returns a human-readable HTML diff.

        Arguments:

            'a' -- original text

            'b' -- revised text

            'delete_tag', 'insert_tag' --

        Result:

            String containing HTML code.
    """
    # split texts into sequences
    a, b = _splitText(a), _splitText(b)

    # do match
    matcher = SequenceMatcher( _spc_rec.search, a, b )
    result  = ''

    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        # each element is a tuple (tag, a1, a2, b1, b2)
        # tag is either 'replace', 'delete', 'insert' or 'equal',
        # a1:a2 are indexes into a, b1:b2 are indexes into b

        if tag == 'replace':
            # for deleted substrings, leave just text
            result += _markWords( a[a1:a2], delete_tag, 1 )
            result += _markWords( b[b1:b2], insert_tag )

        elif tag == 'delete':
            result += _markWords( a[a1:a2], delete_tag )

        elif tag == 'insert':
            result += _markWords( b[b1:b2], insert_tag )

        elif tag == 'equal':
            result += ''.join( b[b1:b2] )

        else:
            raise ValueError, `tag`

    return result

def _splitText( text ):
    # split text into sequence of words, tags, and whitespace
    return filter( None, _sep_rec.split( text ) )

def _markWords( tokens, tag, skip_tags=None ):
    # joins tokens into a string, wrapping words into HTML tag
    result = words = ''

    for token in tokens:
        if not _tag_rec.search( token ):
            # word or whitespace
            words += token

        elif not skip_tags:
            if words:
                # append collected words
                result += tag % words
                words = ''
            # html tag
            result += token
    else:
        if words:
            result += tag % words

    return result

#
# for testing
#
def _testDiff( a, b ):
    f1, f2 = a.find('</head>'), a.find('</body>')
    ca = a[f1+len('</head>'):f2]

    f1, f2 = b.find('</head>'), b.find('</body>')
    cb = b[f1+len('</head>'):f2]

    r = HTMLDiff(a, b)
    hdr = '<style type="text/css"><!-- .diff_inserted {color: green} .diff_deleted {color:red}--></style></head>'
    return hdr + r # + b[f2:]

def _fopen( fname ):
    try:
        return open(fname, 'r')
    except IOError, detail:
        return fail("couldn't open " + fname + ": " + str(detail))

if __name__ == '__main__':
    import sys
    f1 = _fopen(sys.argv[1]);
    f2 = _fopen(sys.argv[2]);

    a = f1.read(); f1.close()
    b = f2.read(); f2.close()

    print _testDiff(a, b)
