"""
HTMLCleanup class
$Id: HTMLCleanup.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
import string
from sys import version_info

def HTMLCleaner( dirt_html, update_str=None, char_references_mode=0, leave_str='', remove_str='' ):
    """
        Clean 'dirty' html text - remove some tags, some attributes.

            dirt_html -- string with HTML text we want to cleanup

            update_str -- string in format: TAG1 [attr1 [attr2 [...]]] TAG2 [attr1 [...]]
                 leave only these tags and their attributes

            char_references_mode -- processing character references mode
                0 -- leave all character references,
                1 -- cut all character references
                2 -- reduce character references (for example '&nbsp;&nbsp;&nbsp;' becomes '&nbsp;')

            leave_str -- tagnames (in uppercase) separated by spaces those will not be cleaned
                (all their attributes will be leaved)

            remove_str -- tagnames (in uppercase) separated by spaces those will be completely
                removed (with any data in it)
    """
    if update_str is None:
        update_str = """
                HTML HEAD TITLE
                BODY
                P class id width align height
                DIV align
                SPAN
                A class id href name target
                STRONG BR B U I EM PRE STRIKE SUB SUP
                H1 align class id
                H2 align class id
                H3 align class id
                H4 align class id
                UL class id
                OL class id start
                LI class id
                TABLE align class id bgcolor width border cellspacing cellpadding bordercolor bordercolordark
                TH class id bgcolor
                TBODY class id
                TR class id bgcolor valign align
                TD class id nowrap rowspan width bgcolor colspan valign align
                IMG style class id src width align height border hspace vspace alt
                FONT size color class id face
                BLOCKQUOTE style
                """
    #if we cannot parse text, return it as-is
    try:
        #parse update_str
        update_tags = {}
        if update_str:
            tags_and_attrs = re.split( '\s+', update_str )
            tagname = ''
            for tag_attr in tags_and_attrs:
                if tag_attr.upper() == tag_attr:
                    # tag_attr is tag name
                    update_tags[ tag_attr ] = []
                    tagname = tag_attr
                elif tagname != '':
                    #tag_attr is attribute name
                    update_tags[ tagname ].append( tag_attr )
            del (tags_and_attrs)

        #remove_tags_content - tags we want comletely remove
        if len(remove_str) > 0:
            remove_tags_content = re.split( '\s+', remove_str )
        else:
            remove_tags_content = []

        #leave_original - tags we do not want to change
        if len(leave_str) > 0:
            leave_original = re.split( '\s+', leave_str )
        else:
            leave_original = []

        # remove all comments first
        #dirt_html = re.sub(r"<!--.*?-->(?ms)", '', dirt_html)

        #remove all remove_tags_content tags
        for tagname in remove_tags_content:
            tagname = re.escape(tagname)
            pattern = r'<\s*' + tagname + r'[\s>]+.*?<[\s]*\/' + tagname + r'(>|\s+.*?>)(?si)'
            dirt_html = re.sub( pattern, '', dirt_html )

        tags_list = re.findall( r"<\s*\/?(\??[\w\!\:]+).*?>(?si)", dirt_html )

        # this may be usefull when create association with attach in htmldocument
        #tags_list = re.findall( r"<\s*\/?([\w\!]+)[^\"\']*?>(?si)", dirt_html )

        #compress it
        tmp = {}
        for tagname in tags_list:
            tmp[tagname] = 1
        tags_list = tmp.keys()
        del(tmp)

        #tags we want to remove (only start tag or/and end tag with all properties, but leave text inside)
        tags_to_remove =[]

        if update_tags:
            for tagname in tags_list:
                if tagname.upper() not in ( update_tags.keys() + leave_original ):
                    tags_to_remove.append( tagname )

        #remove tags in tags_to_remove
        for tagname in tags_to_remove:
            pattern = r"<\s*\/?" + re.escape(tagname) + r"(?:>|[\W]+?.*?>)(?msi)"
            dirt_html = re.sub( pattern, '', dirt_html )
        del (tags_to_remove)

        #process character references
        if char_references_mode == 0:
            pass
        elif char_references_mode == 1:
            pattern = r"&#?\w+?;(?ms)"
            dirt_html = re.sub( pattern, '', dirt_html )
        elif char_references_mode == 2:
            pattern = r"(&#?\w+?;)\1+(?ms)"
            dirt_html = re.sub( pattern, r"\1", dirt_html )

        clean_html = dirt_html

        #process attributes
        for tagname in update_tags.keys():
            pattern = r"(<\s*)(\/?)(" + tagname + r")(\s+.*?)>(?si)"
            tag_tuple_list = re.findall( pattern, dirt_html)
            for tag_tuple in tag_tuple_list:
                tag_str = ''.join(tag_tuple)+">"
                tag_replace_str = "<" + tag_tuple[1] + tag_tuple[2]

                #string with attribute=value pairs
                attr_str = tag_tuple[3]+ " "

                #split attributes and values
                attrs_and_vals = re.findall(r"([a-zA-Z\-]+)\s*=\s*(?:([\"\'])(.*?)\2|([\w\-\.\%\#]+))(?si)", attr_str)

                attrs_hash = {}
                for prop in attrs_and_vals:
                    if prop[1]:
                        attrs_hash[prop[0].lower()] = prop[1] + prop[2] + prop[1]
                    else:
                        attrs_hash[prop[0].lower()] = prop[3]

                # selected / checked flags
                bool_attrs = re.findall(r"(?:(?<=^)|(?<=[^=]))\s+([a-zA-Z\-]+)(?=\s+(?:[^=]|$))(?si)", attr_str)
                #  BUG!!!
                #error: ('unrecognized character after (?', 5)
                #pattern='(?:(?<=^)|(?<=[^=]))\\s+([a-zA-Z\\-]+)(?=\\s+(?:[^=]|$))(?si)'
                #string=' ALIGN="LEFT" VALIGN="TOP" WIDTH="0" HEIGHT="0" '

                for prop in bool_attrs:
                    attrs_hash[prop.lower()] = ''

                for attr_name in update_tags[ tagname ]:
                    if attrs_hash.has_key(attr_name):
                        tag_replace_str += " " + attr_name
                        if attrs_hash[attr_name] != '':
                            tag_replace_str += "=" + attrs_hash[attr_name]
                tag_replace_str += ">"

                clean_html = clean_html.replace( tag_str, tag_replace_str )

        # empty strings cleanup
        clean_html = re.sub( r"^\s*[\r\n]+(?msi)", '', clean_html )

        return clean_html
    except:
        return dirt_html
