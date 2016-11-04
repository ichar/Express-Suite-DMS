"""
Additional DTML tags.

    'GetMsgTag' -- 'dtml-msg' tag implementation

    'GetMessageTag' -- 'dtml-msgtext' tag implementation

    'RevisionTag' -- 'dtml-revision' tag implementation

$Id: DTMLTags.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from cgi import escape
from types import ListType, StringType

from DocumentTemplate.DT_String import String
from DocumentTemplate.DT_Util import InstanceDict, Eval, ParseError, \
     parse_params, name_param, namespace, render_blocks

from Products.Localizer.GettextTag import GettextTag


_linesre = re.compile( r'\s*?\n\s*\n\s*?' )
_spacesre = re.compile( r'\s+' )
_tagre = re.compile( r'<[^>]*?>' )


class GetMsgTag:
    """
        Simple DTML tag for output of the internationalized text messages.

        This tag is a non-block tag usually having a single argument -
        message text to be translated to the user's currently selected language.
        Messages may accept additional parameters, which are inserted
        in the text using '%(name)s' syntax.

        Translation are being looked up in the message catalog, which is
        acquired by 'msg' name from DTML namespace.  Before that continuous
        whitespace in the text is replaced with a single space character,
        leading and trailing whitespace is removed.

        Special HTML characters in the translated message text are quoted
        using HTML character entities.  Values of the parameters are NOT quoted.

        Format::

            <dtml-msg "text" [expr=expression] [name=value ...]>

        Arguments:

            'text' -- default (not translated) message text, also used
                      as a key to lookup translation in the message catalog

            'expr' -- optional DTML or Python expression, used to obtain default
                      message text; if expression evaluates to None, 'text' is
                      used if present, otherwise empty string is returned

            'name=value' -- additional keyword arguments used as
                            the parameters for the message

        Result:

            Translated string.

        Examples::

            <dtml-msg "Thank you for choosing Express Suite DMS!">

            <dtml-msg expr=Title>

            <dtml-msg "Default text" expr="getProperty('text')">

            <dtml-msg "Path of %(id)s is %(path)s" id=getId path="'/'.join(getPhysicalPath())">
    """
    name = 'msg'

    catalog = 'msg'
    message = None
    expr = None
    escape = 1
    newlines = 1

    def __init__( self, args ):
        args = _parse_params( args, tag='msg', compile_values=1 )

        if args.has_key(''):
            text = args['']
            del args['']

            text = _linesre.sub( '\a', text.strip() )
            text = _spacesre.sub( ' ', text )
            text = text.replace( '\a', '\\n' )
            self.message = text

        if args.has_key('expr'):
            self.expr = args['expr']
            del args['expr']

        if self.message is None and self.expr is None:
            raise ParseError, ( 'Message or expression must be specified', tag )

        # TODO: id, catalog, add, lang, html_quote arguments
        self.data = args

    def render( self, md ):
        # translate message
        #
        expr = self.expr
        if expr:
            if callable( expr ):
                text = expr(md)
            else:
                text = md[expr]
            if text is None:
                text = self.message
        else:
            text = self.message

        if not text:
            return ''

        msgcat = md.getitem( self.catalog, 0 )
        text = msgcat.gettext( str(text) )

        if self.escape:
            text = escape( text )
            if self.newlines:
                text = text.replace( '\\n', '<br />\n' )

        if self.data:
            # substitute variables
            data = {}
            for name, expr in self.data.items():
                if callable( expr ):
                    data[ name ] = str( expr(md) )
                else:
                    data[ name ] = str( md[expr] )
            text = text % data

        return text

    __call__ = render


class GetMessageTag( GettextTag ):
    """
        Block DTML tag for output of the internationalized text messages.

        This tag is a block tag usually used without arguments.
        The contents of the tag, which may also include other DTML tags,
        form a message text to be translated to the user's currently
        selected language.  Messages may accept additional parameters,
        which are inserted in the text using '%(name)s' syntax.  These
        parameters may be specified with 'data' argument or using
        'dtml-msgparam' subtags.

        Translation are being looked up in the message catalog, which is
        acquired by 'msg' name from DTML namespace.  Before that continuous
        whitespace in the text is replaced with a single space character,
        leading and trailing whitespace is removed.  If the text contains
        HTML tags, they are replaces with '%(n)s' substrings, where 'n'
        is a sequential number.  These substrings are then replaced back
        in the translated text.

        Special HTML characters in the translated message text are quoted
        using HTML character entities.  Values of the parameters are NOT quoted.

        Format::

            <dtml-msgtext [data=expression] [catalog="msg"]>
            text
            <dtml-msgparam name>
            value
            </dtml-msgtext>

        Arguments:

            'text' -- default (not translated) message text, also used
                      as a key to lookup translation in the message catalog

            'data' -- optional DTML or Python expression, must evaluate
                      to a dictionary containing parameters for the message

            'catalog' -- optional identifier of the message catalog;
                         'msg' is the default

            'name' -- name of additional parameter for the message

            'value' -- value of additional parameter for the message

        Result:

            Translated string.

        Examples::

            <dtml-msgtext>
            Please specify global parameters in
            <a href="&dtml-portal_url;/reconfig_form">
            the portal configuration</a>.
            </dtml-msgtext>

            msgid "Please specify global parameters in %(1)s
            the portal configuration%(2)s."

            <dtml-msgtext data="{'baz':'value of baz'}">
            foo is %(foo)s, bar is %(bar)s, baz is %(baz)s
            <dtml-msgparam foo>
            value of foo
            <dtml-msgparam bar>
            value of bar
            </dtml-msgtext>
    """
    name = 'msgtext'
    blockContinuations = ['msgparam']

    escape = 1
    newlines = 1

    def __init__( self, blocks ):
        GettextTag.__init__( self, blocks )

        if self.catalog is None: self.catalog = 'msg'
        self.blocks = data = []

        # reset data to overcome Localizer's expansion
        self.mdata = self.data
        self.data  = None

        for tname, args, section in blocks[1:]:
            args = parse_params( args, name='' )
            name = name_param( args,'msgparam' )
            data.append( (name, section.blocks) )

    def render( self, md ):
        ns = namespace(md)[0]
        md._push( InstanceDict(ns, md) )
        text = render_blocks( self.section, md )
        md._pop(1)

        data = {}
        match = _tagre.search( text )
        while match:
            data[ str( len(data)+1 ) ] = match.group()
            text = text[ :match.start() ] + ( '%%(%d)s' % len(data) ) + text[ match.end(): ]
            match = _tagre.search( text, match.start() )

        text = _linesre.sub( '\a', text.strip() )
        text = _spacesre.sub( ' ', text )
        text = text.replace( '\a', '\\n' )

        msgcat = md.getitem( self.catalog, 0 )
        text = msgcat.gettext( text )

        if self.mdata is not None:
            # simple variables
            mdata = self.mdata.eval( md )
            try:
                data.update( mdata )
            except TypeError: # python < 2.2
                for key in mdata.keys():
                    data[ key ] = mdata[ key ]

        if self.escape:
            text = escape( text )
            if self.newlines:
                text = text.replace( '\\n', '<br />\n' )

        # block variables
        for name, section in self.blocks:
            data[ name ] = render_blocks( section, md ).strip()

        # substitute variables
        #print data
        text = text % data
        return text

    __call__ = render


class RevisionTag:
    """
        DTML revision tag is used to specify DTML file version
        using CVS keyword expansion.

        The contents if the tag is a single CVS Revision keyword.
        The tag must be placed near the beginning of the file.

        Example::

            <dtml-revision $Revision: 1.5.4.1 $>
    """
    name = 'revision'

    def __init__( self, args ):
        self.revision = args = args.strip()

        if args.startswith('$Revision:'):
            self.version = args[ 11:-2 ]
        else:
            self.version = args

    def __call__( self, md ):
        return ''


_unparmre = re.compile( r'([^\s="]+)\s*' )
_qunparmre = re.compile( r'"([^"]*)"\s*' )
_parmre = re.compile( r'([^\s="]+)=([^\s="]+)\s*' )
_qparmre = re.compile( r'([^\s="]+)="([^"]*)"\s*' )


def _parse_params( text, result=None, tag_name='', compile_values=0,
                   unparmre=_unparmre, qunparmre=_qunparmre,
                   parmre=_parmre, qparmre=_qparmre, **params ):

    text = text.strip()
    if result is None:
        result = {}

    while text:
        match = None

        while not match:
            match = parmre.match( text ) # name=expr
            if match:
                name = match.group(1)
                expr = match.group(2)
                break

            match = qparmre.match( text ) # name="expr"
            if match:
                name, expr = match.group(1), match.group(2)
                if compile_values:
                    expr = _compile_expr( expr, tag_name )
                break

            match = unparmre.match( text ) # name
            if match:
                name = match.group(1)
                if result:
                    expr = params.get( name )
                else:
                    name, expr = '', name
                break

            match = qunparmre.match( text ) # "text"
            if match:
                name, expr = '', match.group(1)
                if result:
                    raise ParseError, ( 'Invalid attribute value, "%s"' % expr, tag_name )
                break

            raise ParseError, ( 'Invalid parameter: "%s"' % text, tag_name )

        if result.has_key( name ):
            p = params[ name ]
            if type(p) is not ListType or p:
                raise ParseError, ( 'Duplicate values for attribute "%s"' % name, tag_name )

        result[ name ] = expr
        text = text[ match.end(): ]

    return result

def _compile_expr( text, tag ):
    try:
        return Eval( text ).eval
    except SyntaxError, exc:
        raise ParseError, ( 'Syntax error:\n%s\n' % exc[0], tag )


String.commands[ GetMsgTag.name ] = GetMsgTag
String.commands[ GetMessageTag.name ] = GetMessageTag
String.commands[ RevisionTag.name ] = RevisionTag
